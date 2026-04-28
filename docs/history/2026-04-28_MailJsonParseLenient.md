# 2026-04-28 메일 MCP JSON 파싱 관용화 (strict=False + 부분 복구 salvage)

## 개요
그룹웨어 임베드 UI에서 "안 읽은 메일 확인해줘" 요청 시 JSON 파싱 오류로 메일이 한 통도 안 나오던 이슈를 3-단계 fallback으로 해결. 1차 strict 시도, 실패 시 strict=False, 그래도 실패하면 메일 객체 단위로 raw_decode를 돌려 깨진 메일은 스킵하고 성공한 것만 모아 정상 응답 형태로 재구성. **풀 로깅으로 실제 깨진 위치를 확보한 결과 control char가 아닌 JSP 직렬화 자체의 구조 손상**(`"flag":96` 다음에 콤마 없이 다음 메일 subject가 그대로 이어붙는 패턴)으로 확인되어 salvage 단계가 실질적인 해결책. 라이브 검증으로 19건 중 18건 복구, 1건만 스킵 확인.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/mcp_servers/mail_server/server.py | 수정 | `_call_mail_api`에 strict → strict=False → salvage 3단계 폴백 적용. `_salvage_mail_response()` 신설: data 배열을 메일 객체 단위로 raw_decode, 깨진 객체는 balanced-brace 스캔으로 스킵, `_salvaged=True`/`_skipped=N` 메타 부착. `_format_mail_list`가 부분 복구 사실을 LLM에 안내. |
| backend/app/agents/a2a_streaming.py | 수정 | `[TOOL_OUTPUT]` 풀 로깅 화이트리스트에 6개 메일 도구 추가 (300자 truncate 제거) |

## 상세 내용

### 증상 (운영 로그 기반)
- 사번 A2304013, 메시지 "안 읽은 메일 확인해줘"
- `get_unread_mail` → 약 1.2초 만에 종료, 그러나 LLM은 #2 호출에서 다시 `get_inbox_mail` 시도
- `get_inbox_mail` 역시 결과를 활용하지 못하고 LLM이 다음과 같이 응답:
  > 현재 메일 서버에서 특수 문자 포함된 메일로 인해 JSON 파싱 오류가 반복 발생하고 있습니다. 😥
  > 📭 안 읽은 메일 수 **181건** / ⚠️ 목록 조회: 메일 본문의 특수 문자로 인해 파싱 오류 발생
- ToolMessage 본문이 LLM에게 `메일 조회 실패: JSON파싱실패 (action=...) | err=Invalid control character at: ...` 형태로 전달된 것으로 추정 (운영 로그의 `[TOOL_OUTPUT]`은 300자에서 잘려서 디버그 헤더만 남고 실제 에러 텍스트는 로그에 안 찍힘)

### 원인 분석
- JSP가 메일 제목/미리보기/본문을 JSON 문자열로 직렬화할 때, 본문에 포함된 raw newline/tab/기타 control char(0x00–0x1F)를 escape하지 않고 그대로 출력
- Python `json.loads`는 기본적으로 strict=True이며 string 내부의 unescaped control char를 거부 → `Invalid control character at` 에러
- 메일 한 통이라도 문제 있는 본문이 포함되면 전체 JSON이 파싱 실패 → 목록 조회 자체가 동작 안 함

### 수정 방식
1. **strict=False 폴백** (`_call_mail_api`)
   - 1차: `json.loads(stripped)` 시도 (기존 동작 유지)
   - 1차 실패 시: stderr에 위치/메시지 기록 후 `json.loads(stripped, strict=False)` 재시도
   - 2차도 실패 시: head/tail 200자를 stderr에 기록한 뒤 원래 strict 에러를 다시 던져 외부 RuntimeError로 변환

   `strict=False`는 string value 안에 0x00–0x1F 제어 문자를 그대로 허용한다. JSP가 이런 문자를 넣은 경우에 대해 가장 직접적인 해결책이며, 응답 구조 자체는 그대로 유지되므로 `_format_mail_list` 등 후속 포맷팅에는 영향 없음.

2. **mail 도구 풀 로깅** (`a2a_streaming.py`)
   - 기존: `get_daily_reservations`, `get_calendar_events`만 `(full, N chars)` 형태로 풀 로깅
   - 변경: 메일 6개 도구(inbox/sent/unread/search/folders/detail)를 화이트리스트에 추가
   - 향후 파싱 이슈가 재발해도 ToolMessage 전체 텍스트가 로그에 남아 즉시 진단 가능

## 결정 사항 및 주의점
- **3단계 폴백 채택 이유**: 1차 풀 로깅 후 실제 깨짐 패턴이 unescaped control char가 아니라 **JSP 측 직렬화의 구조 손상**(콤마 누락, escape 안 된 quote)임이 드러남. strict=False는 무력하므로 salvage 단계 추가가 실질적 해결책.
- **객체 단위 복구 vs 전체 거부**: 한 통이 깨졌다고 181건 unread를 한 통도 못 보여주는 건 사용자 가치를 0으로 만듬. 깨진 1건만 스킵하고 18건 보여주는 게 명백히 낫다. 부분 결과임은 `_salvaged`/`_skipped` 메타 + `[참고]` 안내 라인으로 LLM/사용자에게 전달.
- **balanced-brace 스캔 안전장치**: salvage 루프에서 `i <= pos`면 진전 없는 것으로 간주해 break — 무한 루프 방지. depth 추적은 string 내부의 `{`/`}`를 무시하기 위해 in_str/esc 상태 유지.
- **검증 방법**: 운영 JSP에 직접 호출해 실제 깨진 응답으로 1차 strict→2차 strict=False→3차 salvage 순으로 확인. A2304013 unread 19건 중 18건 복구, 1건 스킵.
- **JSP 측 정공법은 별건**: 그룹웨어 lucid_mail.jsp의 직렬화 로직(특히 preview/subject escape)을 고치면 근본 해결되나 협의 필요. 클라이언트 salvage는 그 사이의 임시 우회 + 영구 안전망으로 남음.
- **풀 로깅 부담**: 메일 본문 detail은 최대 8,000자까지 로그에 찍히게 됨. 파싱 이슈 진단이 안정화되면 다시 300자 트렁케이션으로 되돌리는 것을 검토할 것.
- **재발 시 다음 단계**: stderr에 `[Mail MCP] JSON 재시도도 실패 (salvage도 실패)` 로그가 남으면 head/tail로 정확한 원인 식별 → JSP 측 직렬화 수정 또는 추가 sanitization 도입.
