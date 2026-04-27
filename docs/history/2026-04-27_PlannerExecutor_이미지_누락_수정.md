# 2026-04-27 Planner-Executor 첨부 이미지 누락 버그 수정

## 개요

운영에서 A2304013 사용자가 이미지를 첨부하고 "이전 포맷에 맞춰 정리해줘"라고 요청하면 AI가 "첨부된 이미지를 감지할 수 없습니다"로 응답하는 증상이 N회차 반복 관측됨. 같은 세션 내에서도 단순 follow-up("포맷 여기있잖니")은 이미지를 인식했지만, 다단계 추론이 필요한 요청은 항상 실패. Planner-Executor 경로에서 sub-task 호출 시 첨부 이미지가 워커에 전달되지 않는 구조적 버그를 수정함.

## 변경 파일 요약

| 파일 | 변경 유형 | 설명 |
|------|-----------|------|
| backend/app/agents/state.py | 수정 | `RequestContext`에 `images: Optional[List[Dict]]`, `has_images: bool` 필드 추가 |
| backend/app/agents/a2a_streaming.py | 수정 | req_context 빌드 시 `images`/`has_images` 주입 |
| backend/app/agents/executor.py | 수정 | `_run_task`에서 `depends=[]`인 첫 task에 첨부 이미지를 multimodal HumanMessage로 동봉 |
| backend/app/agents/planner.py | 수정 | 룰 10 추가(이미지 첨부 시 user_files 금지), PLANNER_USER_TEMPLATE에 `has_images` 필드, Few-shot Example 9/10 추가 |

## 상세 내용

### 1. 증상과 원인 진단

**관측 사례** (운영 green 로그, 2026-04-27 16:17:31):
- 사용자: "지금 첨부한 이미지는 파워젠의 ai hub 솔루션이거든. 이것도 포맷에 맞춰서 작성"
- Planner: `is_trivial=False`, 2 tasks
  - t1[user_files] "첨부된 파워젠 AI Hub 솔루션 이미지 파일 내용 분석 및 텍스트 추출"
  - t2[direct] "t1에서 추출한 내용을 이전 대화 포맷에 맞춰 요약 작성"
- t1 실행: UserFilesWorker가 `search_user_files`만 4회 호출 (모두 0건) → "업로드된 파일을 찾을 수 없습니다"
- 최종 응답: "현재 세션에서 업로드된 파일을 찾을 수 없습니다"

**근본 원인** ([executor.py:278-280](../../backend/app/agents/executor.py)):
```python
# Worker 메시지 — task goal만 담은 단일 HumanMessage
# (원본 사용자 메시지를 넣으면 워커가 scope를 오해할 수 있음)
messages: List[BaseMessage] = [HumanMessage(content=task.goal)]
```
Executor가 sub-task 호출 시 `task.goal` 텍스트 한 줄만 워커에 넘기고, 사용자가 첨부한 이미지(multimodal content blocks)는 완전히 누락됨. `RequestContext`에도 images 필드가 없어 워커가 꺼낼 방법이 없었음.

**Trivial 경로와의 차이**:
- Trivial: `orchestrator._build_messages(message, history, images)` → 이미지가 multimodal HumanMessage로 워커에 전달 ✅
- Planner-Executor: `Executor._run_task` → 텍스트만 ❌

같은 세션의 16:01:03 "포맷 여기있잖니" 요청은 Planner가 `is_trivial=True`로 분류해서 trivial 경로를 탔기 때문에 우연히 동작했음.

### 2. 수정 설계 — Goal Isolation 유지하면서 입력 자료 별첨

**핵심 결정**: `depends=[]`인 task(첫 단계, 원본 입력에 직접 접근해야 하는 task)에만 이미지 동봉. 후속 task는 blackboard에서 선행 결과 텍스트를 받으므로 이미지를 다시 보낼 필요 없음.

장점:
- Goal isolation 원칙 유지 (task.goal 텍스트는 그대로 한 줄, 이미지는 입력 자료로만 별첨)
- 토큰 비용 최소화 (이미지는 첫 task에만 1회 전송)
- 다중 이미지·다중 첫 task 모두 자연스럽게 지원

### 3. 데이터 흐름 (변경 후)

```
chat.py (request.images)
  ↓
a2a_streaming.py
  ├─ orchestrator(message, context, ..., images=images)  ← 기존 trivial 경로 그대로
  └─ req_context["images"] = images           ← NEW: Executor가 꺼낼 수 있게
     req_context["has_images"] = bool(images) ← NEW: Planner 라우팅 힌트
  ↓
Planner (has_images=True 보고 user_files 회피, direct/visualization 우선)
  ↓
Executor._run_task:
  if context["images"] and not task.depends:
      multimodal HumanMessage 구성 (image blocks + task.goal text)
  else:
      기존: HumanMessage(content=task.goal)
```

### 4. Planner 프롬프트 보강

기존에 룰 8, 9에서 첨부파일/엑셀 처리 가이드가 있었지만 **이미지 vs 텍스트 문서를 구분하는 시그널이 없었음**. `has_files`만으로는 워커 라우팅이 모호.

**룰 10 추가**:
> 이미지 첨부 시(`has_images=true`) 분석/요약/변환 태스크는 절대 `user_files`로 보내지 마세요. `search_user_files`는 ChromaDB 텍스트 검색이라 이미지 픽셀을 못 봅니다. 사용자가 첨부한 이미지를 "보고/요약/포맷에 맞춰 작성/표로 정리" 해달라고 하면 **`direct` 워커**(또는 차트/PDF 생성이 필요하면 `visualization`)를 사용하세요.

**Few-shot Example 9** (이미지 단순 분석 → direct trivial):
```json
{
  "is_trivial": true,
  "tasks": [{"id":"t1","worker":"direct","goal":"첨부 이미지를 보고 이전 대화 포맷에 맞춰 정리","depends":[]}]
}
```

**Few-shot Example 10** (이미지 → 후속 가공 → direct + visualization):
```json
{
  "is_trivial": false,
  "tasks": [
    {"id":"t1","worker":"direct","goal":"첨부 차트 이미지에서 카테고리·값 쌍 추출","depends":[]},
    {"id":"t2","worker":"visualization","goal":"t1 결과로 막대그래프 생성","depends":["t1"]}
  ]
}
```

## 결정 사항 및 주의점

### 왜 모든 task에 이미지를 동봉하지 않는가
- 후속 task는 blackboard에서 선행 task의 텍스트 결과를 받으므로 이미지 재처리 불필요.
- 이미지 한 장당 입력 토큰 약 1,000~2,000개. 매 task에 동봉 시 토큰 N배 낭비.
- 비전 처리 시간도 task마다 누적되어 응답 지연.

### 트리비얼 경로는 변경 없음
`orchestrator._build_messages()`는 이전 그대로 동작. RequestContext.images는 Executor에서만 사용되며 트리비얼 경로 워커는 `_build_messages`로 이미 multimodal 메시지를 받고 있어 중복 영향 없음 (`grep context["images"]` 결과: executor.py 한 곳).

### Planner 라우팅 실패 시의 안전망
Planner가 룰을 무시하고 t1=user_files로 라우팅하더라도 Executor는 여전히 이미지를 동봉함 (worker 종류와 무관하게 `depends=[]`이면 동봉). 이 경우 UserFilesWorker의 Sonnet 모델이 이미지 픽셀을 직접 보면서도 `search_user_files`도 호출 가능 → 최악의 경우에도 모델이 이미지 자체는 인식.

### 메시지 히스토리의 이미지는 별도 이슈
이전 turn에 첨부된 이미지를 다음 turn에서 follow-up하는 케이스(예: "그 그림에서 X 부분 다시 봐줘")는 이번 수정 범위 밖. 현재 구조에서는 message_history가 Planner에는 텍스트 요약으로만 전달되고, Executor의 sub-task에는 아예 안 들어감. 필요 시 후속 작업으로 분리.

### 검증 방법
1. A2304013의 16:17:31 시나리오 재현: 이미지 첨부 + "포맷에 맞춰 작성" → t1=direct로 라우팅되는지, multimodal HumanMessage가 구성되는지 로그(`[EXECUTOR] t1 (direct): multimodal goal with N image(s)`) 확인.
2. 트리비얼 경로 회귀: 이미지 + "포맷 여기있잖니" 단순 follow-up이 그대로 동작하는지.
3. 이미지 없는 multi-step 회귀: 결재 → 메일 답장처럼 이미지 무관 케이스의 토큰/응답 동일성 확인.
