# 2026-04-28 글로벌 MCP 도구 캐시 race condition 수정 — 사용자별 사본 패턴 도입

## 개요
A1602018 사용자가 자기 그룹웨어 위젯에서 "오늘 받은 메일 정리해줘" 요청 시 응답에 **다른 사용자 A2310009의 받은편지함 16건이 그대로 노출**되는 사건이 발생했다. 인증·IP·토큰 모두 정상이었고 변조 흔적도 없었다. 원인 추적 결과 9개 워커가 공통적으로 사용하는 `prepare_tools()`/`_wrap_tools_for_archive()` 패턴이 글로벌 캐시되는 MCP `BaseTool` 객체에 사용자별 wrapper를 직접 덮어쓰는 방식이라, 동시 요청 시 마지막 wrapper의 closure(사번 등)가 다른 사용자의 도구 호출에 섞이는 race condition이 있었다. 본 PR은 모든 워커의 wrapping 패턴을 **사용자별 shallow copy 사본의 `ainvoke`만 교체**하는 방식으로 통일한다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/workers/base_worker.py` | 수정 | `_wrap_tools_for_archive()`를 사본 패턴으로 변경, `_archive_wrapped` 가드 제거 |
| `backend/app/agents/workers/mail_worker.py` | 수정 | `prepare_tools()` 사본 패턴 |
| `backend/app/agents/workers/approval_worker.py` | 수정 | 동일 |
| `backend/app/agents/workers/it_support_worker.py` | 수정 | 동일 (SECURED_TOOLS 외 도구도 prepared에 그대로 append) |
| `backend/app/agents/workers/calendar_worker.py` | 수정 | 동일 (gosso_cookie 주입 wrapper 포함) |
| `backend/app/agents/workers/reservation_worker.py` | 수정 | 동일 |
| `backend/app/agents/workers/nas_worker.py` | 수정 | `_nas_wrapped` 가드 제거 (사본 패턴에서 무의미) |
| `backend/app/agents/workers/xlsx_worker.py` | 수정 | 동일 (filepath 검증 + circuit breaker closure 모두 사본 단위) |
| `backend/app/agents/workers/outline_worker.py` | 수정 | 4가지 wrapper 분기 모두 사본 패턴, 접근 제어 closure도 사본 단위 |

## 상세 내용

### 사건 타임라인 (server.log.1)
```
14:42:01  A1602018 인증, IP 10.10.71.41 (정상), session=181ef3c5...
          Message: "오늘 받은 메일 정리해줘"
          UserMemory: row=None (메모리 비어있음)
14:42:02  A2310009 인증, IP 10.10.25.185 (정상)
          Message: "너 지금 다른 사람걸 가져온거야? 다시 내꺼 줘"
14:42:04  [MailWorker] 보안 래핑 완료: employee_number → A1602018
14:42:06  [MailWorker] 보안 래핑 완료: employee_number → A2310009  ← 같은 tool 객체 ainvoke를 덮어씀
14:42:07  [TOOL_STATUS_DEBUG] tool_name=get_inbox_mail,
          tool_input={'employee_number': 'A2310009', 'limit': 20}  ← A1602018의 LLM 호출인데 A2310009로 들어감
14:42:08  [TOOL_OUTPUT] get_inbox_mail: (full, 6784 chars)
          [MAIL_DEBUG] action=inbox employee=A2310009 → A2310009 메일 20건 노출
```

### 결함이 있던 패턴 (수정 전)
```python
def prepare_tools(self, tools, context):
    user_id = context.get("user_id")
    for tool in tools:                              # tools는 글로벌 캐시 (TTL 1hr)
        original_ainvoke = (
            getattr(tool, '_unwrapped_ainvoke', None)
            or tool.ainvoke
        )
        object.__setattr__(tool, '_unwrapped_ainvoke', original_ainvoke)
        async def secured_ainvoke(input_data, ..., _uid=user_id, ...):
            input_data["args"]["employee_number"] = _uid
            ...
        object.__setattr__(tool, "ainvoke", secured_ainvoke)  # ← 같은 객체에 덮어쓰기
    return tools
```

같은 `tool` 객체를 모든 요청이 공유하므로 두 사용자가 1~2초 차이로 워커를 호출하면 **마지막 prepare_tools 호출의 wrapper가 이긴다**. 그 사이에 첫 사용자의 LLM이 도구를 호출하면 두 번째 사용자의 사번이 강제 주입된다.

### 수정 후 패턴
```python
import copy

def prepare_tools(self, tools, context):
    user_id = context.get("user_id")
    prepared = []
    for tool in tools:
        user_tool = copy.copy(tool)              # 사용자별 shallow copy
        original_ainvoke = tool.ainvoke          # 글로벌 객체의 현재 ainvoke
        async def secured_ainvoke(input_data, ..., _uid=user_id, ...):
            input_data["args"]["employee_number"] = _uid
            ...
        object.__setattr__(user_tool, "ainvoke", secured_ainvoke)  # 사본만 교체
        prepared.append(user_tool)
    return prepared                              # 글로벌 캐시는 그대로
```

핵심:
- `copy.copy(tool)`은 `BaseTool` 인스턴스의 얕은 사본 — 내부 schema/속성은 공유, 새 객체 식별성만 다름
- `object.__setattr__(user_tool, "ainvoke", ...)`은 사본에만 적용 → 글로벌 객체 영향 없음
- 동시 요청이 와도 각자 자기 사본 리스트를 LangGraph에 넘기므로 race 자체가 성립 안 함
- 사본은 LangGraph agent와 함께 단명 — GC 수거됨

### 가드 제거 (의미 잃은 코드)

기존 패턴의 가드들은 사본 패턴에서 모두 의미 잃어 제거:
- `_unwrapped_ainvoke` (래핑 체인 방지) — 사본을 매번 만드므로 chain 자체가 형성 안 됨
- `_archive_wrapped` (중복 래핑 방지) — 동일
- `_nas_wrapped` (동일)

### Worker별 특이사항
- **xlsx_worker**: `redirected_files`/`created_workbook`/`creation_done` closure 모두 사본 단위로 격리. 세션 간 파일 상태 누설 차단.
- **outline_worker**: 4가지 wrapper(publish/write/search/read) 모두 같은 사본을 공유. `_get_collection_access(user_id)` 결과 closure도 사본 단위.
- **calendar_worker**: `gosso_cookie` closure도 사본 단위로 격리 — 다른 사용자의 GOSSOcookie가 새 wrapper로 덮어써지는 race 차단.
- **base_worker**: `archive_file(filepath, _user_id)` closure가 첫 사용자 user_id로 박혀 모든 사용자 산출물이 첫 사용자 폴더로 흘러가던 잠재 결함도 같이 해소.

## 결정 사항 및 주의점

### 왜 deepcopy가 아닌 shallow copy인가
`BaseTool`의 schema·name·description은 공유해도 race가 안 일어난다. race를 일으키는 건 `ainvoke` 속성 하나뿐이고, 그건 `object.__setattr__`로 사본에만 새로 박는다. deepcopy는 schema 객체까지 복제하므로 메모리/CPU 비용이 더 들고 의미가 없다.

### Pydantic 호환
`BaseTool`은 langchain의 Pydantic v1 모델 호환 객체. `copy.copy`는 Python 표준 `__copy__`를 호출하며 langchain은 이를 지원한다. 운영 검증 필요 항목:
- 두 계정으로 동시에 메일 도구 호출 → 각자 본인 메일만 받는지
- xlsx 동시 생성 → 파일 경로 누설 안 되는지
- outline 검색 동시 → 권한 필터 결과 섞이지 않는지

### 영향 범위
- 패치된 워커가 다루는 모든 도구의 동시 호출 시 데이터 누설 차단
- 패치 안 된 워커(direct/web_search/youtube/url_fetch/board/ppt/visualization/web/user_files/corp_rag/acct_support 등)는 애초에 ainvoke 덮어쓰기를 안 하므로 영향 없음
- archive 래핑은 base_worker에서 처리되므로 상속 워커는 자동 적용

### 후속 과제 (별개 작업)
- A2310009/A1602018 user_memory 정리 (앞서 분석 완료, SQL 준비됨)
- 보안기술팀 변조 시도자(A2310009)의 14:36~14:41 시간대 chat_sessions/chat_log_new 흔적 정리
- AES-ECB → CBC/GCM 전환, 위젯 토큰 일회성화 (jti+nonce), 유효시간 단축
- acct_support_worker 등 employee_number 주입을 안 하는 워커의 보안 정책 재검토

### 운영 적용
- 운영 재시작 후 즉시 적용
- 글로벌 캐시 객체는 패치 직후엔 이전 wrapper 잔재가 남아있을 수 있어 **재시작이 필수** (잔재가 남아있어도 새 사본은 깨끗한 ainvoke를 사용하므로 보안상 문제 없음, 단 깨끗한 시작이 검증 용이)
