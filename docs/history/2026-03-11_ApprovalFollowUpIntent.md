# 2026-03-11 결재 Follow-up 인텐트 오분류 수정

## 개요
결재 문서 목록 조회 후 "WA전표품의 3건 상세 내용 확인" 같은 follow-up 요청이 `acct_support`로 잘못 분류되어 결재 본문 조회가 실패하는 문제를 수정. 결재 양식명 키워드 추가 + 이전 턴 intent 전달로 follow-up 판단력을 강화.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/intent_classifier.py | 수정 | quick_classify에 결재 양식명 추가, CLASSIFIER_PROMPT에 양식명 명시 + previous_intent 컨텍스트 추가, classify()에 previous_intent 파라미터 추가 |
| backend/app/agents/orchestrator.py | 수정 | context에서 previous_intent를 추출하여 classifier.classify()에 전달 |
| backend/app/agents/a2a_streaming.py | 수정 | DB에서 세션의 마지막 intent를 조회하여 req_context에 주입 |
| backend/app/services/chat_log_service.py | 수정 | get_last_intent() 메서드 추가 |

## 상세 내용

### 원인 분석
1. "WA전표품의 3건 상세 내용 확인" 메시지에 결재 키워드(결재, 기안, 상신 등)가 없음
2. quick_classify에서 매칭 실패 → LLM 분류로 위임
3. CLASSIFIER_PROMPT의 acct_support 설명에 "WA"가 포함되어 있어 LLM이 `acct_support`로 분류
4. AcctSupportWorker는 결재 도구가 없어 → "불가합니다" 응답

### 수정 내용

**1. quick_classify 결재 양식명 추가**
```python
# Before
approval_keywords = r'(결재|기안|상신|전자결재|...)'
# After
approval_keywords = r'(결재|기안|상신|전자결재|...|전표품의|품의서|사전지출\s?승인|예외처리\s?신청)'
```

**2. CLASSIFIER_PROMPT 수정**
- acct_support에서 "WA" 제거 → "WA전표품의는 approval" NOTE 추가
- approval에 양식명 목록 명시 (WA전표품의, 품의서, 보고, 사전지출승인서 등)

**3. previous_intent 전달 체인**
```
chat_log_new.intent (DB) → a2a_streaming → req_context → orchestrator → classifier.classify()
→ CLASSIFIER_PROMPT의 "Previous turn intent: {previous_intent}" 필드
```

**4. Rule 10 (FOLLOW-UP) 강화**
이전: 대화 히스토리 텍스트만으로 follow-up 판단 (불안정)
이후: `previous_intent` 명시적 전달 → "previous_intent=approval + 양식명 참조 → approval"

### get_last_intent() 쿼리
```sql
SELECT intent FROM chat_log_new
WHERE session = %s AND intent IS NOT NULL
ORDER BY createDate DESC LIMIT 1
```

## 결정 사항 및 주의점
- `get_last_intent()`는 동기 DB 호출이지만, 단일 row LIMIT 1 조회로 성능 영향 미미 (< 1ms)
- quick_classify의 양식명 매칭으로 대부분의 follow-up은 LLM 호출 없이 즉시 분류됨
- "WA전표" (회계 전표) vs "WA전표품의" (결재 양식) 구분: "품의"가 있으면 approval
