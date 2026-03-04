# 2026-03-04 메일 전체 본문 조회/요약/답장 초안

## 개요
기존 메일 시스템이 미리보기(100자)만 지원했던 한계를 해결하여, 전체 본문 조회, LLM 기반 메일 요약, 답장 초안 생성 기능을 추가.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `lucid_mail.jsp` (그룹웨어 서버) | 수정 | `detail` action 추가, 기존 action에 `folder_no` 필드 추가 |
| `backend/app/mcp_servers/mail_server/server.py` | 수정 | `get_mail_detail` MCP 도구 추가, `_format_mail_detail` 포맷터, 목록에 uid/folder 노출 |
| `backend/app/agents/workers/mail_worker.py` | 수정 | tool_names에 `get_mail_detail` 추가, system_prompt 대폭 갱신, max_agent_steps=30 |
| `backend/app/agents/intent_classifier.py` | 수정 | 메일 액션 패턴에 요약/답장/회신 추가, CLASSIFIER_PROMPT 업데이트 |
| `backend/app/agents/a2a_streaming.py` | 수정 | `get_mail_detail` 도구 상태 메시지 추가 |
| `backend/app/agents/workers/base_worker.py` | 수정 | MailWorker follow-up capabilities 업데이트 |
| `backend/data/jsp/lucid_mail.jsp` | 추가 | 배포용 JSP 참조 파일 (로컬 보관) |

## 상세 내용

### JSP `detail` action
- **입력**: `uid_no`, `folder_no`, `message_store`, `api_key`
- **동작**: SQLite에서 `full_path` 조회 → `.eml` 파일 읽기 → MIME 파싱 → HTML→텍스트 변환
- **MIME 지원**: quoted-printable, base64, multipart/alternative, 중첩 multipart
- **보안**: `full_path`는 `/mdata`로 시작해야 함, `..` 차단, 5MB 파일 제한
- **본문 제한**: JSP 50,000자, MCP 8,000자 (2단계 잘라내기)

### 메일 저장 구조 (확인된 사실)
```
SQLite (_mcache.db)
├── mail_message.full_path → /mdata/10/369/1390/YYYYMMDD/filename.eml
├── mail_body (FTS3) → 검색용 인덱스만, 전체 본문 아님
└── uid_no + folder_no = 복합 키
```
- Tomcat이 `mailadm` 사용자로 실행 → `.eml` 파일(640 권한) 읽기 가능
- `.eml` 파일: 표준 MIME 포맷, HTML 본문이 일반적

### MCP 도구 `get_mail_detail`
- **파라미터**: `employee_number`, `uid_no: int`, `folder_no: int`
- 메일 목록의 `[메일ID: uid=N, folder=M]` 정보를 사용하여 상세 조회
- HTTP timeout 기존 15초 → detail은 `_call_mail_api` 공용 (15초, .eml 파싱 시간 포함)
- `_format_mail_detail`: 제목/발신자/수신자/CC/날짜 + 본문 텍스트 (8,000자 제한)

### Worker 프롬프트 변경
- "미리보기만 가능" 제한 제거
- 3가지 멀티스텝 워크플로우 추가:
  1. **메일 요약**: 핵심 내용 / 요청 사항 / 액션 아이템
  2. **답장 초안**: 비즈니스 톤, `[플레이스홀더]`, 복사 안내
  3. **다수 메일 요약**: 최대 5건, 1-2문장씩 정리
- `max_agent_steps = 30` (기존 20) — 목록+상세N건+응답 워크플로우 대응

### Intent Classifier 변경
- `mail_action_pattern`: `요약|답장|답신|회신|응답` 추가
- `mail_keywords`: `메일\s?요약|메일\s?답장|메일\s?회신` 추가
- CLASSIFIER_PROMPT: 본문 조회/요약/답장 키워드 추가

### 검색 전략 개선 (같은 날 추가)

**문제**: `search_mail`로 특정 메일을 못 찾는 케이스 발생
- 원인 1: SQLite 캐시 타이밍 — 최신 메일이 `msg_subject`에 아직 인덱싱되지 않음
- 원인 2: LLM이 제목 전체를 키워드로 사용 → LIKE 매칭 실패율 증가
- Tomcat 8.5.72: raw 한글 URL은 RFC 7230 위반으로 거부하나, httpx의 percent-encoding은 정상 작동 확인

**수정 내용**:
| 파일 | 변경 |
|------|------|
| `mail_worker.py` | SEARCH STRATEGY 섹션 추가: inbox 우선 → search 폴백, 짧은 키워드 권장 |
| `mail_server/server.py` | `_query_mail` 첫 로그에 kwargs(keyword 등) 포함하도록 개선 |

**변경 전 전략** (LLM 자율):
```
search_mail(keyword="긴 제목") → 실패 → 재시도 → 재시도 → 포기
```

**변경 후 전략** (프롬프트 지시):
```
get_inbox_mail(limit=50) → 목록에서 발견 → get_mail_detail
                         → 미발견 → search_mail(keyword="짧은 핵심어")
```

## 결정 사항 및 주의점
- **답장은 초안만**: 실제 발송 기능은 미구현 (보안상 사용자가 그룹웨어에서 직접 발송)
- **배치 조회 없음**: 다수 메일 요약 시 LLM이 개별 `get_mail_detail` 반복 호출 (max 5건 권장)
- **mail_body FTS3 테이블**: 검색용 인덱스로 440-530자 추출본만 저장, docid와 uid_no 매핑 불일치 → 사용 불가
- **JSP 배포**: 그룹웨어 서버에 직접 배포 필요, 로컬 참조본은 `backend/data/jsp/lucid_mail.jsp`
- **검색 한글 인코딩**: Tomcat 8.5는 raw 한글 URL 거부, httpx percent-encoding은 정상 → 검색 자체는 작동하나 SQLite 캐시 미반영 가능
