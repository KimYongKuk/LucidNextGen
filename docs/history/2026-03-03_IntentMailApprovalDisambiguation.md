# 2026-03-03 인텐트 분류 메일/전자결재 혼동 수정

## 개요
메일 제목에 "전자결재" 키워드가 포함된 경우, 사용자의 실제 의도(메일 확인)와 다르게 전자결재(APPROVAL) 인텐트로 오분류되는 문제를 수정.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| `backend/app/agents/intent_classifier.py` | 수정 | quick_classify에 메일 액션 우선 패턴 추가, approval 키워드에 메일 동시 존재 시 LLM 위임, LLM 프롬프트에 disambiguation 규칙/예시 추가 |

## 상세 내용

### 문제 상황
사용자 메시지: `'Re: Re: [엘앤에프] JHC 전자결재 수정 확인 요청 件' 메일 내용 확인해줘`

- "메일" (mail 키워드)과 "전자결재"/"결재" (approval 키워드) 모두 포함
- `MAIL_WORKER_ENABLED=false`이거나, 워크스페이스에 파일이 있는 경우:
  - mail 체크 스킵/LLM 위임 → "전자결재"가 approval로 매칭 → ApprovalWorker가 처리
  - ApprovalWorker는 메일 조회 불가 → "메일 조회가 활성화되어 있지 않습니다" 응답

### 수정 내용

#### 1. `_quick_classify` - 메일 액션 패턴 우선 감지
```python
mail_action_pattern = r'메일\s*(내용|내역|본문)?\s*(확인|보여|검색|찾아|조회|알려|읽어)'
```
- "메일 내용 확인해줘", "메일 검색해줘" 등 명시적 메일 액션은 다른 키워드(전자결재 등) 존재와 무관하게 즉시 MAIL로 분류
- 워크스페이스 파일 유무에도 영향받지 않음 (사용자가 메일 조회를 명시적으로 요청)

#### 2. `_quick_classify` - approval 키워드에 메일 동시 존재 시 LLM 위임
```python
has_mail_keyword = bool(re.search(r'(메일|이메일|e-?mail)', message, re.IGNORECASE))
if has_mail_keyword:
    return None  # LLM에 위임하여 맥락 기반 판단
```
- approval 키워드가 매칭되더라도 "메일" 키워드가 함께 있으면 quick_classify에서 단정하지 않고 LLM에 위임

#### 3. LLM 분류기 프롬프트 - disambiguation 규칙 및 예시 추가
- PRIORITY RULES에 "3. DISAMBIGUATION - mail vs approval" 규칙 추가
- 메일 제목에 포함된 키워드는 사용자의 의도가 아니라 메일의 내용일 뿐임을 명시
- EXAMPLES에 3개 엣지 케이스 추가

## 결정 사항 및 주의점
- 메일 액션 패턴(`mail_action_pattern`)은 `MAIL_WORKER_ENABLED=true`일 때만 동작
- 메일이 비활성화된 환경에서는 여전히 LLM 또는 approval로 분류될 수 있음 (의도적 설계)
- 향후 유사한 키워드 충돌 케이스 발견 시 같은 패턴으로 확장 가능
