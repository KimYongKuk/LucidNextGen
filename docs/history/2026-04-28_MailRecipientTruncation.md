# 2026-04-28 메일 수신자 리스트 압축 (수백 명 케이스 토큰 폭증 차단)

## 개요
부서 전체 공지 메일처럼 to/cc 필드에 수백 명의 임직원이 들어 있는 경우, MCP `search_mail` / `get_inbox_mail` 결과가 메일 한 통당 약 2KB(20건이면 약 40KB)에 달해 LLM 컨텍스트가 폭증하고 Bedrock 일일 토큰 한도(`ThrottlingException: Too many tokens per day`)를 일찍 소진해 메일 리스트 응답이 누락되는 증상이 발생했다. 사용자(A2304013) 테스트에서 재현됨. `_format_mail_list` / `_format_mail_detail`에서 발신/수신/참조 필드를 N명 + "외 M명" 형태로 축약해 토큰 사용량을 약 95% 절감했다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/mcp_servers/mail_server/server.py | 수정 | `_truncate_recipients()` 추가, 목록/상세 포맷터에서 from/to/cc 축약 적용 |

## 상세 내용

### 추가된 상수
```python
RECIPIENT_LIST_MAX_NAMES = 5            # 목록 조회 시 표시할 수신자 수
RECIPIENT_DETAIL_MAX_NAMES = 30         # 상세 조회 시 표시할 수신자 수
RECIPIENT_FIELD_MAX_CHARS = 800         # 콤마 분리 실패 케이스 컷오프
```

### `_truncate_recipients(value, max_names)`
- JSP가 반환하는 `to`/`cc`/`from` 형식: `이름/직급/부서 <email>, ...` 콤마 구분 문자열
- 콤마로 분할 후 N명까지만 보여주고 나머지는 `... 외 M명`으로 치환
- 콤마 분리 실패 시 `RECIPIENT_FIELD_MAX_CHARS`로 단순 컷오프 폴백

### 적용 지점
- `_format_mail_list`: `발신:`, `수신:` 라인에 `RECIPIENT_LIST_MAX_NAMES=5` 적용
- `_format_mail_detail`: `발신자:`, `수신자:`, `참조(CC):` 라인에 `RECIPIENT_DETAIL_MAX_NAMES=30` 적용 (답장 초안 작성 시 더 많은 수신자 정보 필요)

### 검증
200명 수신자 입력(7,468자):
- `RECIPIENT_LIST_MAX_NAMES=5` → 170자 (약 44배 압축)
- `RECIPIENT_DETAIL_MAX_NAMES=30` → 1,055자 (약 7배 압축)

## 결정 사항 및 주의점
- **목록 조회는 5명 + 외 N명**만 보여줌 — 발신자/제목/날짜/미리보기가 핵심이고, 누구에게 갔는지는 보통 컨텍스트 결정에 불필요
- **상세 조회는 30명까지** 보여줌 — 답장 작성 시 적정 수의 수신자 정보가 필요할 수 있음
- 폴백 컷오프 800자는 JSP 응답이 비정상 포맷이거나 콤마가 없는 경우 안전망
- 원본 to 필드가 필요한 케이스(법적 증거 등)는 본 도구의 영역이 아니므로 의도적으로 누락
- 본 변경은 MCP server 레벨이라 운영 반영 시 MCP 서버 프로세스 재기동 필요(BlueGreen 배포로 자동 처리됨)
- 관련 근본 원인(누적 일일 토큰 폭증)은 본 패치로 메일 워커 측 기여분만 줄어듦. 다른 워커도 비슷한 패턴이 있다면 별도 점검 필요
