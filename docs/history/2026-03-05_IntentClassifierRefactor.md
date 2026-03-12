# 2026-03-05 Intent Classifier 구조 개선 + 프롬프트 슬림화

## 개요
`quick_classify`의 pairwise 충돌 체크 구조를 scan-all 패턴으로 리팩토링하고, `CLASSIFIER_PROMPT`에서 quick_classify가 이미 처리하는 뻔한 예시를 제거하여 ~180줄→~100줄로 슬림화.

## 변경 파일 요약
| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/intent_classifier.py | 전면 리팩토링 | quick_classify 구조 개선, CLASSIFIER_PROMPT 슬림화 |

## 상세 내용

### 배경 문제
1. **Pairwise 충돌 체크**: mail+approval, board+approval 등 인텐트 쌍별 예외 처리 → 인텐트 추가 시 N² 확장
2. **CLASSIFIER_PROMPT 비대화**: ~180줄, quick_classify가 이미 처리하는 뻔한 예시가 LLM에 불필요하게 전달
3. **원인 사건**: "전자결재 관련 게시글 찾아줘" → approval로 오분류 (board+approval 충돌 미처리)

### quick_classify 구조 변경

**이전 (first-match-wins + pairwise 예외):**
```
mail 체크 → workspace deferral
approval 체크 → mail 충돌? board 충돌? workspace deferral?
board 체크 → workspace deferral
xlsx 체크 → workspace deferral
web_search 체크
```

**이후 (scan-all + defer-if-2+):**
```
Step 1: 100% 확실 (YouTube URL, 일반 URL, 명시적 메일 액션)
Step 2: 도메인 인텐트 키워드 스캔 → matched_intents 수집
        (mail, approval, board, xlsx)
Step 3: 판정
        - 2개 이상 매칭 → return None (LLM 위임)
        - 1개 + workspace_has_files → return None (LLM 위임)
        - 1개 → 즉시 반환
Step 4: Web search fallback (도메인에 안 걸렸을 때만)
Step 5: return None (LLM 위임)
```

**핵심 설계 결정:**
- Web search를 Step 4(fallback)로 분리: "이번 달 결재 현황"에서 time+info 키워드("이번 달"+"현황")와 approval 키워드("결재")가 동시 매칭되는 false overlap 방지
- 도메인 인텐트가 먼저 잡으므로 web_search는 "아무 도메인에도 안 걸린" 메시지만 처리

### CLASSIFIER_PROMPT 슬림화

**제거된 항목 (~60줄):**
- 단순 메일 예시 5개 ("최근 메일 보여줘" 등) — quick_classify에서 처리
- 단순 결재 예시 8개 ("결재 대기 건 있어?" 등) — quick_classify에서 처리
- 단순 게시판 예시 5개 ("전사 공지 최신글" 등) — quick_classify에서 처리
- 단순 web_search 예시 6개 ("삼성전자 주가" 등) — quick_classify에서 처리
- 단순 xlsx 예시 3개 ("엑셀 파일 만들어줘" 등) — quick_classify에서 처리

**통합된 규칙:**
- Rule 3 (mail vs approval) + Rule 6.5 (board vs approval)
  → Rule 4 "DISAMBIGUATION: ACTION 동사/대상이 인텐트를 결정" 하나로 통합

**유지된 항목 (~20줄):**
- PPT/visualization 예시 (quick_classify 없음)
- corp_rag/it_support/acct_support 예시 (quick_classify 없음)
- Disambiguation 예시 (LLM이 판단해야 하는 충돌 케이스)
- xlsx + has_session_xlsx 예시 (컨텍스트 의존)
- direct/user_files 예시

### 동작 비교

| 메시지 | 이전 | 이후 | 비고 |
|--------|------|------|------|
| "결재 대기 건 있어?" | Quick→APPROVAL | Quick→APPROVAL | 동일 |
| "최근 메일 보여줘" | Quick→MAIL | Quick→MAIL | 동일 |
| "전자결재 관련 게시글 찾아줘" | Quick→APPROVAL (오분류) | Quick→LLM→BOARD | 수정됨 |
| "전자결재 메일 확인해줘" | Quick→MAIL (Step1 액션) | Quick→MAIL (Step1 액션) | 동일 |
| "이번달 2차전지 동향" | Quick→WEB_SEARCH | Quick→WEB_SEARCH | 동일 |
| "이번 달 결재 현황" | Quick→APPROVAL | Quick→APPROVAL | 동일 (Step4 미도달) |
| "PPT 만들어줘" | LLM→PPT | LLM→PPT | 동일 |

## 결정 사항 및 주의점
- Web search를 scan-all에 포함하지 않은 이유: "현황", "최근" 등 시간/정보 키워드가 사내 시스템 조회에서도 흔히 사용되어 false multi-match 발생
- 새 인텐트 추가 시: Step 2에 키워드 스캔만 추가하면 됨 (pairwise 예외 불필요)
- CLASSIFIER_PROMPT 예시 추가 기준: quick_classify에서 처리 불가능한 케이스만 (LLM 전용 인텐트, disambiguation, 컨텍스트 의존)
