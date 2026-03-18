# 2026-03-17 MailWorker / ApprovalWorker 토큰 폭증 해결

## 개요
MailWorker와 ApprovalWorker의 ReAct agent loop에서 이전 tool result가 압축 없이 매 LLM 호출마다 전부 재전송되어 토큰을 과도하게 소비하던 문제를 해결. 동시에 도구별 차등 truncation과 워커별 keep_recent_pairs로 응답 품질 보호.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/workers/base_worker.py | 수정 | compact_keep_recent_pairs 프로퍼티 추가, stream_response에서 워커별 값 사용 |
| backend/app/agents/workers/mail_worker.py | 수정 | compact + 도구별 차등 truncation (목록 16K / 상세 6K) |
| backend/app/agents/workers/approval_worker.py | 수정 | compact + HTML 태그 제거 후 truncation (10K) |

## 상세 내용

### 1단계: compact_previous_results + keep_recent_pairs
- BaseWorker에 `compact_keep_recent_pairs` 프로퍼티 추가 (기본값 1)
- MailWorker: keep=6 (inbox + detail x5 = 6쌍 전부 원본 유지)
- ApprovalWorker: keep=4 (목록 + doc_body x3 = 4쌍 전부 원본 유지)
- XlsxWorker: keep=1 유지 (순차 빌드 패턴, 이전 결과 불필요)

### 2단계: 도구별 차등 truncation (품질 보호)
초기 일괄 truncation에서 발견된 품질 이슈:

**문제 1: inbox(limit=50)이 일괄 6K에서 잘림**
- 50건 목록 ≈ 15,000자 → 6K truncation시 ~18건만 LLM에 전달
- "OOO 메일 찾아줘" → 잘린 부분에 있으면 "없습니다" 오답

**해결: 목록/상세 차등 한도**
- 목록 도구 (inbox/sent/unread/search/folders): `MAIL_LIST_RESULT_MAX_CHARS = 16,000`
- 상세 도구 (detail): `MAIL_DETAIL_RESULT_MAX_CHARS = 6,000`

**문제 2: 결재 doc_body HTML에서 태그가 3~5K 소비**
- 76KB HTML에서 CSS/style/태그가 대부분 → 8K truncation 시 실제 내용 3~5K만 전달
- HTML 태그 중간 절단 → LLM 파싱 곤란

**해결: HTML 태그 제거 후 truncation**
- `_strip_html_tags()`: style/script 블록 제거, HTML 태그 제거, 엔티티 변환
- 76KB HTML → ~20K 순수 텍스트 → 10K truncation
- 태그 제거로 동일 글자수 예산에서 유효 콘텐츠 2~3배 증가

### 3단계: 최종 토큰 예산 정리

| 워커 | 도구 | 한도 | 근거 |
|------|------|------|------|
| MailWorker | inbox/sent/unread/search | 16K | 50건 목록 커버 |
| MailWorker | detail | 6K | 요약/답장에 충분 |
| ApprovalWorker | execute_approval_query | 10K | HTML 태그 제거 후 적용 |

## 결정 사항 및 주의점
- 목록 도구는 truncation을 넉넉하게 (검색 정확도 우선)
- 상세 도구는 타이트하게 (토큰 효율 우선, compact가 추가 방어)
- HTML 태그 제거는 단순 regex 기반 — 복잡한 중첩 구조에서 불완전할 수 있으나 LLM 요약 용도로는 충분
- compact keep_recent_pairs가 있으므로 목록 16K도 오래된 결과는 200자로 압축됨
