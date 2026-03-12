# 2026-03-11 BaseWorker Haiku 대화 요약 기본화

## 개요
멀티턴 대화 시 토큰 누적을 방지하기 위해, 기존 3개 워커(XlsxWorker, PPTWorker, VisualizationWorker)에 개별 구현되어 있던 Haiku 대화 요약 파이프라인을 BaseWorker로 이동하여 **모든 워커**에 기본 적용. 약 300줄의 중복 코드 제거.

## 배경
- WebSearchWorker, MailWorker, DirectWorker 등은 대화 요약 없이 전체 히스토리를 그대로 전송
- 프론트엔드 15턴 제한(30메시지)이 있지만, 후반부 호출이 비대해지는 구조적 문제
- 기존 3개 워커에서 동일한 코드가 각각 ~100줄씩 중복 구현

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/workers/base_worker.py` | 수정 | 요약 상수/프롬프트 추가, `_summarize_history_if_needed()`, `_format_messages_for_summary()` 메서드 추가, `stream_response()` 시작부에 요약 Phase 0 삽입, `summarization_prompt`/`skip_summarization` 프로퍼티 추가 |
| `backend/app/agents/workers/ppt_worker.py` | 수정 | 중복 요약 코드 ~90줄 제거, `compact_previous_results=True` 추가, `summarization_prompt` 오버라이드 |
| `backend/app/agents/workers/visualization_worker.py` | 수정 | 중복 요약 코드 ~110줄 제거, `summarization_prompt` 오버라이드 |
| `backend/app/agents/workers/xlsx_worker.py` | 수정 | 중복 요약 코드 ~70줄 제거, `summarization_prompt` 오버라이드 (compact_previous_results는 기존 유지) |
| `backend/app/agents/workers/direct_worker.py` | 수정 | `stream_response()`에 Haiku 요약 Phase 0 추가 (직접 LLM 호출이므로 별도 구현) |

## 상세 내용

### BaseWorker에 추가된 요소

**상수:**
| 상수 | 값 | 설명 |
|------|-----|------|
| `SUMMARIZATION_MESSAGE_THRESHOLD` | 6 | 요약 트리거 최소 메시지 수 |
| `SUMMARIZATION_CHAR_THRESHOLD` | 5000 | 요약 트리거 최소 총 문자 수 |
| `DEFAULT_SUMMARIZATION_PROMPT` | (범용) | 기본 요약 프롬프트 |

**프로퍼티:**
| 프로퍼티 | 기본값 | 설명 |
|----------|--------|------|
| `summarization_prompt` | `DEFAULT_SUMMARIZATION_PROMPT` | Worker별 도메인 특화 요약 프롬프트 오버라이드 |
| `skip_summarization` | `False` | 요약 건너뛰기 (예약용, 현재 모든 워커 False) |

**메서드:**
- `_summarize_history_if_needed(messages)`: 임계값 초과 시 Haiku로 요약 → `[이전 대화 요약] + 현재 메시지` 2개로 압축
- `_format_messages_for_summary(messages)`: 메시지를 `User:/Assistant:` 텍스트로 변환 (2000자/메시지 제한)

### 요약 트리거 조건 (AND)
1. 메시지 6개 이상
2. 총 문자 수 5,000자 이상

짧은 대화는 절대 요약하지 않음 — 사용자 경험에 영향 없음.

### Worker별 구성

| Worker | 요약 | compact | 요약 프롬프트 |
|--------|------|---------|---------------|
| DirectWorker | ✅ | - | 기본 (범용) |
| WebSearchWorker | ✅ (NEW) | - | 기본 (범용) |
| MailWorker | ✅ (NEW) | - | 기본 (범용) |
| CorpRAGWorker | ✅ (NEW) | - | 기본 (범용) |
| UserFilesWorker | ✅ (NEW) | - | 기본 (범용) |
| YouTubeWorker | ✅ (NEW) | - | 기본 (범용) |
| URLFetchWorker | ✅ (NEW) | - | 기본 (범용) |
| ITSupportWorker | ✅ (NEW) | - | 기본 (범용) |
| AcctSupportWorker | ✅ (NEW) | - | 기본 (범용) |
| PPTWorker | ✅ | ✅ (NEW) | PPT 특화 |
| VisualizationWorker | ✅ | - | PDF/문서 특화 |
| XlsxWorker | ✅ | ✅ | Excel 특화 |

### PPTWorker compact_previous_results 추가
PPTWorker도 다단계 도구 호출(create_presentation, chart 도구 등)이 많아 ReAct loop 토큰 누적 문제가 있었음. `compact_previous_results=True` 추가로 XlsxWorker와 동일한 압축 적용.

## 결정 사항 및 주의점
- **임계값이 보수적**: 6메시지 AND 5,000자 — 짧은 대화는 건드리지 않음
- **요약 실패 시 원본 사용**: try/except로 감싸서 Haiku 호출 실패 시 원본 메시지 그대로 전달
- **DirectWorker 별도 구현**: `create_react_agent`를 사용하지 않는 직접 LLM 호출 구조이므로 BaseWorker.stream_response()를 호출하지 않음 → 직접 `_summarize_history_if_needed()` 호출
- **summarization_prompt 오버라이드**: PPT/Visualization/Xlsx는 도메인 특화 프롬프트로 오버라이드하여 파일명, 구조 등 중요 정보 보존
- **기존 동작 100% 호환**: 이전에 요약이 있던 3개 워커는 동일 로직, 나머지 워커는 새로 요약 추가
