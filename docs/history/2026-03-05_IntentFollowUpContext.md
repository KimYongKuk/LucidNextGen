# 2026-03-05 인텐트 분류기 후속 질문 맥락 지원

## 개요
짧은 후속 질문(예: `"근무지"는?`)이 이전 대화 맥락을 무시하고 엉뚱한 인텐트로 분류되는 버그를 수정. LLM 분류 시 대화 히스토리를 전달하여 맥락 기반 분류를 지원한다.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/intent_classifier.py | 수정 | `classify()`에 `message_history` 파라미터 추가, LLM 프롬프트에 대화 맥락 섹션 및 FOLLOW-UP 룰 추가 |
| backend/app/agents/orchestrator.py | 수정 | `classify()` 호출 시 `message_history` 전달 |

## 상세 내용

### 문제 상황
1. 사용자가 "메모" 키워드로 메일 검색 → `mail` 인텐트로 정상 분류
2. 후속으로 `"근무지"는?` 전송 → `corp_rag`로 오분류 (CorpRAGWorker가 메일 도구 없어서 실패)
3. 원인: `classify()`가 현재 메시지만 받고 대화 히스토리를 전혀 참고하지 않음

### 수정 내용
- `classify()` 메서드에 `message_history: Optional[List[Dict]]` 파라미터 추가
- 최근 4개 메시지를 `CONVERSATION HISTORY` 섹션으로 LLM 프롬프트에 주입
- 각 메시지는 150자로 truncate (프롬프트 크기 제한)
- RULES에 **FOLLOW-UP 룰(#10)** 추가: 짧은 후속 질문은 이전 턴의 인텐트를 유지

### 프롬프트 변경 (발췌)
```
CONVERSATION HISTORY (last few messages for context):
  user: "메모" 키워드가 포함된 발신/수신함 메일 있는지 찾아봐줄 수 있어?
  assistant: "메모" 키워드로 검색한 결과, 받은편지함과 보낸편지함 모두에서 해당 메일을 찾을 수 없었습니다.

RULES:
...
10. FOLLOW-UP: If the current message is a short follow-up ... MAINTAIN the same intent as the previous turn.
```

## 결정 사항 및 주의점
- **quick_classify는 변경하지 않음**: 규칙 기반은 키워드 매칭이라 맥락 판단이 어려움. LLM fallback에서 처리
- **최근 4개 메시지**: 너무 많으면 Haiku 프롬프트 비용 증가, 4개면 직전 2턴(user+assistant×2) 커버
- **150자 truncate**: 긴 응답(차트 데이터 등)이 프롬프트를 과도하게 차지하지 않도록 제한
