"""Planner — 사용자 요청을 Task DAG로 분해하는 LLM 계획자

Planner-Executor 아키텍처의 첫 단계. IntentClassifier를 대체하여
단순 요청은 단일 task로, 복합 요청은 의존성 있는 task 목록으로 분해한다.

설계 문서: docs/history/2026-04-20_Planner-Executor-design.md
"""

import json
import os
import re
import asyncio
from typing import Optional, List

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.model_config import get_orchestrator_config, get_worker_config
from app.core.region_fallback import get_region_fallback_manager
from app.agents.workers.base_worker import CachedChatBedrockConverse
from app.agents.state import (
    Intent,
    Task,
    Plan,
    TaskStatus,
    RequestContext,
    WORKER_CAPABILITIES,
    INTENT_TO_WORKER,
)


PLANNER_SYSTEM = """You are a task planner for 루시드AI (LF그룹 사내 AI 어시스턴트).

Your job: decompose user's request into a JSON Task DAG that can be executed by specialized workers.

## CORE RULES

1. **Single task for simple requests**: If the request can be fully handled by ONE worker without needing other workers' data, return `is_trivial: true` with a single task.
2. **Decompose complex requests**: If the request involves multiple workers OR needs sequential dependencies (worker B needs worker A's output), return `is_trivial: false` with multiple tasks.
3. **Parallel independence**: Tasks with no shared data dependency should have `depends: []` so Executor runs them in parallel.
4. **Explicit dependencies**: If task B's goal references task A's output, set `depends: ["<A's id>"]`.
5. **Write operations need confirmation**: Set `needs_confirm: true` for tasks that WRITE data (일정 등록, 회의실 예약, 결재 상신, 메일 발송, 위키 등록, 파일 업로드). Read/search tasks do NOT need confirmation.
6. **Goal is one concrete sentence**: Korean, one line, immediately actionable by the worker. Not vague like "처리해줘".
7. **Task IDs are t1, t2, t3, ...** in declaration order.
8. **첨부파일은 분석 중간 단계 끼우지 말 것**: 사용자가 "등록해줘/업로드해줘/첨부해줘" 등 **쓰기 작업 + 파일 첨부**를 요청했을 때, 파일 내용 분석(user_files)을 **사전 태스크로 넣지 마세요**. 해당 쓰기 워커(it_support, mail 등)가 파일을 직접 첨부 파라미터로 전달합니다. 예외: 사용자가 명시적으로 "내 파일 내용 읽고 요약해줘/본문에 반영해줘"라고 요청한 경우만 user_files 사전 태스크 추가.
9. **엑셀 파일 수정·편집 요청은 `xlsx` 단일 태스크(trivial=true)로 처리**: "업로드한 엑셀/기존 파일에 **시트 추가·복사·삭제·이름변경·값변경·서식·수식·병합·행열 삽입/삭제·차트·피벗**" 등 모든 xlsx 편집 요청은 **user_files 사전 태스크를 넣지 마세요**. XlsxWorker가 `get_workbook_metadata + read_data_from_excel + modify_xlsx`를 이미 보유하여 자체적으로 메타→읽기→수정을 처리합니다. **예외**: 사용자가 엑셀을 "요약해줘/분석해줘/요점만 알려줘" 등 **read-only 요약**을 요청한 경우에만 `user_files` 사용.

## AVAILABLE WORKERS (use the `worker` field value)

{worker_catalog}

## OUTPUT FORMAT

Return ONLY a JSON object matching this schema:

```
{{
  "is_trivial": bool,
  "rationale": "한 줄 한국어 — 왜 이렇게 쪼갰는지",
  "tasks": [
    {{
      "id": "t1",
      "worker": "<worker_value>",
      "goal": "<한 줄 구체적 목표>",
      "depends": [],
      "needs_confirm": false
    }},
    ...
  ]
}}
```

No explanations outside JSON. No code fences.

## FEW-SHOT EXAMPLES

### Example 1 — Trivial (단일 워커, 단순 질문)

User: "오늘 일정 보여줘"

Output:
{{
  "is_trivial": true,
  "rationale": "단일 캘린더 조회 요청",
  "tasks": [
    {{"id":"t1","worker":"calendar","goal":"내 오늘(2026-04-20) 일정 조회","depends":[],"needs_confirm":false}}
  ]
}}

### Example 2 — Trivial (일반 대화)

User: "파이썬에서 리스트 정렬하는 법 알려줘"

Output:
{{
  "is_trivial": true,
  "rationale": "일반 프로그래밍 질문 — direct 응답",
  "tasks": [
    {{"id":"t1","worker":"direct","goal":"Python 리스트 정렬 방법 설명","depends":[],"needs_confirm":false}}
  ]
}}

### Example 3 — 2-task 병렬 (독립적 조회)

User: "받은 메일 5개랑 내일 일정 같이 보여줘"

Output:
{{
  "is_trivial": false,
  "rationale": "메일과 캘린더는 독립 조회 → 병렬 실행",
  "tasks": [
    {{"id":"t1","worker":"mail","goal":"받은편지함 최근 5개 조회","depends":[],"needs_confirm":false}},
    {{"id":"t2","worker":"calendar","goal":"내일 내 일정 조회","depends":[],"needs_confirm":false}}
  ]
}}

### Example 4 — 복합 DAG (병렬 + 순차 + 승인 필요)

User: "'PR파트' 메일 건 관련 다음 주 수요일 14시에 최지원,장욱진과 본사 회의실 예약하고 캘린더 등록해줘. 아젠다 초안 메일도 작성해줘."

Output:
{{
  "is_trivial": false,
  "rationale": "메일 조회/조직도/회의실은 독립 병렬. 일정 충돌 확인 후 예약+등록(쓰기), 메일 본문 기반 아젠다 작성.",
  "tasks": [
    {{"id":"t1","worker":"mail","goal":"'PR파트' 관련 최근 메일 본문 조회","depends":[],"needs_confirm":false}},
    {{"id":"t2","worker":"corp_rag","goal":"최지원, 장욱진 사번/근무지 조회","depends":[],"needs_confirm":false}},
    {{"id":"t3","worker":"reservation","goal":"본사 2026-04-29(수) 14:00~15:00 빈 회의실 조회","depends":[],"needs_confirm":false}},
    {{"id":"t4","worker":"calendar","goal":"최지원·장욱진의 2026-04-29 14:00~15:00 일정 충돌 확인","depends":["t2"],"needs_confirm":false}},
    {{"id":"t5","worker":"calendar","goal":"내 캘린더에 'PR파트 회의' 일정 등록 (14:00~15:00)","depends":["t3","t4"],"needs_confirm":true}},
    {{"id":"t6","worker":"reservation","goal":"t3에서 고른 회의실 예약","depends":["t3","t4"],"needs_confirm":true}},
    {{"id":"t7","worker":"mail","goal":"t1 본문 기반 회의 아젠다 초안 작성 (비즈니스 톤)","depends":["t1"],"needs_confirm":false}}
  ]
}}

### Example 5 — 순차 의존 (A의 결과를 B에 전달)

User: "받은 메일 중에 '정기 점검' 관련 메일 찾아서 요약해줘"

Output:
{{
  "is_trivial": false,
  "rationale": "메일 검색 후 본문 조회해 요약",
  "tasks": [
    {{"id":"t1","worker":"mail","goal":"'정기 점검' 키워드로 받은메일 검색","depends":[],"needs_confirm":false}},
    {{"id":"t2","worker":"mail","goal":"t1에서 찾은 메일 본문 조회 후 요약","depends":["t1"],"needs_confirm":false}}
  ]
}}

### Example 6 — IT VOC 등록 + 첨부파일 (분석 태스크 생략)

User: "LFON 로그인 에러야. 첨부한 스크린샷 함께 IT VOC에 등록해줘"
Context: has_files=true

Output:
{{
  "is_trivial": true,
  "rationale": "IT VOC 등록(쓰기) + 첨부파일. 파일 분석 불필요 — it_support가 attachments 파라미터로 직접 첨부.",
  "tasks": [
    {{"id":"t1","worker":"it_support","goal":"LFON 로그인 에러 관련 IT VOC 등록 (업로드된 스크린샷 첨부 포함)","depends":[],"needs_confirm":true}}
  ]
}}

**주의**: 여기서 user_files 태스크를 추가하지 마세요. register_works_voc 도구가 attachments 파라미터를 지원하며, ITSupportWorker가 업로드된 파일 목록을 직접 인식해 자동으로 첨부합니다. user_files의 search_user_files는 ChromaDB 기반 텍스트 검색이라 이미지에는 동작하지 않습니다.

### Example 7 — 이전 턴 승인 요청에 대한 "응/ㅇㅇ" 수락 (멀티턴 resume)

Conversation history:
- User: "다음 주 화요일 23시에 성서 C/R3 예약하고 캘린더 등록해줘"
- Assistant: "아래 내용으로 진행할까요? 📅 2026-04-28 23:00~24:00, 🏢 성서 C/R3. 진행 원하시면 '응'이라고 답해주세요"

Current user message: "응" (또는 "ㅇㅇ", "네", "진행해")

Output:
{{
  "is_trivial": false,
  "rationale": "이전 턴 승인 요청 수락 → 대기 중이던 쓰기 작업 실행. 이미 확인된 사항이므로 needs_confirm 불필요.",
  "tasks": [
    {{"id":"t1","worker":"reservation","goal":"성서 C/R3 2026-04-28 23:00~24:00 회의실 예약 등록","depends":[],"needs_confirm":false}},
    {{"id":"t2","worker":"calendar","goal":"내 캘린더에 '성서 회의' 일정 2026-04-28 23:00~24:00 등록","depends":[],"needs_confirm":false}}
  ]
}}

**중요**: 짧은 수락 응답("응", "ㅇㅇ", "네", "좋아", "진행")일 때는 **conversation history를 참고하여 이전 요청의 쓰기 작업을 복원**하세요. 이 경우 needs_confirm=false (사용자가 이미 승인함).

반대로 짧은 거부 응답("아니", "노", "취소")일 때는:
{{"is_trivial": true, "rationale": "이전 요청 취소 수락", "tasks": [{{"id":"t1","worker":"direct","goal":"취소 확인 응답","depends":[]}}]}}

### Example 8 — 업로드한 엑셀 편집 (xlsx 단일 태스크)

User: "업로드한 엑셀에 Summary 시트 추가하고 C열 합계 수식 넣어줘"
Context: has_files=true (xlsx 파일 업로드됨)

Output:
{{
  "is_trivial": true,
  "rationale": "엑셀 편집(시트 추가 + 수식)은 xlsx worker 단독 처리. XlsxWorker가 get_workbook_metadata → read_data_from_excel → modify_xlsx 를 자체적으로 수행.",
  "tasks": [
    {{"id":"t1","worker":"xlsx","goal":"업로드 엑셀에 'Summary' 시트 추가 + C열 합계 수식(=SUM(C2:C9)) 입력","depends":[],"needs_confirm":false}}
  ]
}}

**주의**: 엑셀 수정·편집 요청 시 `user_files` 사전 태스크(파일 내용 분석)를 넣지 마세요. XlsxWorker가 직접 읽고 수정합니다. 단, "엑셀 요약해줘/요점만 알려줘" 같은 read-only 요청은 `user_files` 사용이 맞습니다.

"""


# 가변 부분(요청마다 바뀜) — HumanMessage에 담음 (캐시 밖)
PLANNER_USER_TEMPLATE = """## CONTEXT

- Today: {today}
- User uploaded files present: {has_files}
- Workspace mode: {has_workspace}
- Workspace name: {workspace_name}
- Workspace instructions (운영자 지정 — 존재 시 DAG 계획에 반영):
{workspace_instructions}

{conversation_history}

## USER REQUEST

{message}"""


# 영구 에러 (fallback 해도 동일 에러)
class PlannerFallback(Exception):
    """Planner 실패 시 orchestrator가 기존 intent_classifier 경로로 폴백"""
    pass


class Planner:
    """사용자 요청을 Task DAG로 분해하는 LLM 계획자"""

    def __init__(self):
        self._region_mgr = get_region_fallback_manager()
        self._was_fallback = self._region_mgr.is_fallback_active
        self.llm = self._create_llm()
        # 시스템 프롬프트는 프로세스 수명 동안 고정 → cachePoint 대상
        self._system_prompt: Optional[str] = None

    def _create_llm(self) -> CachedChatBedrockConverse:
        """Sonnet + Prompt Caching. 고정 system 프롬프트(~2K 토큰)를 캐시해서 cache_read 할인."""
        config = get_worker_config(use_sonnet=True)
        effective_model_id = self._region_mgr.get_model_id(config.model_id)
        return CachedChatBedrockConverse(
            model=effective_model_id,
            temperature=0.0,
            max_tokens=2048,
        )

    def _ensure_correct_region(self):
        """리전 상태 변경 시 LLM 재생성"""
        current_fallback = self._region_mgr.is_fallback_active
        if current_fallback != self._was_fallback:
            self._was_fallback = current_fallback
            self.llm = self._create_llm()
            print(f"[Planner] LLM recreated for region change (fallback={current_fallback})")

    @staticmethod
    def _format_history(message_history: Optional[List[dict]]) -> str:
        """최근 대화 이력을 Planner 프롬프트용 텍스트로 포맷.

        짧은 수락 응답("응") 같은 맥락 의존 요청을 정확히 분해하기 위해 최근 4턴만 전달.
        각 assistant 응답은 앞 600자만 (토큰 절약).
        """
        if not message_history:
            return "## CONVERSATION HISTORY\n(없음 — 첫 메시지)"

        recent = message_history[-4:]  # 최근 4턴
        lines = ["## CONVERSATION HISTORY (최근 대화 — 'ㅇㅇ/응' 등 맥락 의존 해석에 사용)"]
        for msg in recent:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if not isinstance(content, str):
                # list-of-dict 형식 처리
                if isinstance(content, list):
                    content = " ".join(
                        it.get("text", "") if isinstance(it, dict) else str(it)
                        for it in content
                    )
                else:
                    content = str(content)
            # assistant는 600자, user는 400자로 잘라 토큰 절약
            limit = 600 if role == "assistant" else 400
            if len(content) > limit:
                content = content[:limit] + f"...[{len(content)-limit}자 생략]"
            lines.append(f"### {role}\n{content}")
        return "\n\n".join(lines)

    @staticmethod
    def _build_worker_catalog() -> str:
        """환경변수로 비활성화된 워커는 제외하고 카탈로그 생성"""
        enabled_intents = []
        for intent in Intent:
            # intent_classifier와 동일한 env flag 체크
            env_flag = f"{intent.value.upper()}_WORKER_ENABLED"
            if intent in (Intent.DIRECT, Intent.CLARIFY):
                enabled_intents.append(intent)
                continue
            # 일부 워커는 flag 이름이 다름 — 안전하게 default True
            if os.environ.get(env_flag, "true").lower() == "true":
                enabled_intents.append(intent)

        lines = []
        for intent in enabled_intents:
            cap = WORKER_CAPABILITIES.get(intent, "")
            if cap:
                lines.append(f'- `{intent.value}`: {cap}')
            elif intent == Intent.DIRECT:
                lines.append(f'- `direct`: 일반 대화, 코딩, 번역, 설명 (외부 데이터 불필요)')
            elif intent == Intent.CLARIFY:
                lines.append(f'- `clarify`: 요청이 모호하여 사용자에게 확인이 필요한 경우')
        return "\n".join(lines)

    async def plan(
        self,
        message: str,
        context: RequestContext,
        message_history: Optional[List[dict]] = None,
    ) -> Plan:
        """사용자 요청을 Plan으로 분해

        Args:
            message: 현재 사용자 메시지
            context: 요청 컨텍스트
            message_history: 이전 대화 이력 (최근 N턴). 짧은 수락("응") 등 맥락 복원용.

        Raises:
            PlannerFallback: LLM 실패/JSON 파싱 실패/DAG 검증 실패 시. 호출자는 기존 경로로 폴백.
        """
        self._ensure_correct_region()

        # 시스템 프롬프트 — 프로세스 수명 동안 고정 (cachePoint 대상)
        if self._system_prompt is None:
            self._system_prompt = PLANNER_SYSTEM.format(
                worker_catalog=self._build_worker_catalog(),
            )

        # 사용자 메시지 — 매 요청마다 바뀌는 부분만 (cachePoint 밖)
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d (%a)")
        ws_instructions = context.get("workspace_instructions") or ""
        user_content = PLANNER_USER_TEMPLATE.format(
            today=today,
            has_files=context.get("has_files", False),
            has_workspace=bool(context.get("workspace_id") or context.get("workspace_uuid")),
            workspace_name=context.get("workspace_name") or "N/A",
            workspace_instructions=ws_instructions.strip() if ws_instructions else "N/A",
            conversation_history=self._format_history(message_history),
            message=message,
        )

        try:
            response = await self.llm.ainvoke([
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=user_content),
            ])
        except Exception as e:
            print(f"[Planner] LLM call failed: {type(e).__name__}: {e}")
            raise PlannerFallback(f"LLM error: {e}") from e

        # 토큰 사용량 로깅 (intent_classifier와 동일 패턴)
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            try:
                from app.services.token_usage_service import get_token_usage_service
                um = response.usage_metadata
                asyncio.create_task(get_token_usage_service().log(
                    caller="planner",
                    model_id=self.llm.model_id if hasattr(self.llm, "model_id") else "sonnet",
                    input_tokens=um.get("input_tokens", 0),
                    output_tokens=um.get("output_tokens", 0),
                    session_id=context.get("session_id"),
                    user_id=context.get("user_id"),
                ))
            except Exception:
                pass

        raw = (response.content or "").strip()

        # 코드 펜스 제거 (```json ... ```)
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()

        # JSON 파싱
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"[Planner] JSON parse failed: {e}\nRaw response: {raw[:500]}")
            raise PlannerFallback(f"JSON parse error: {e}")

        # Plan 객체 구성
        try:
            plan = self._dict_to_plan(data)
        except (KeyError, TypeError, ValueError) as e:
            print(f"[Planner] Plan build failed: {type(e).__name__}: {e}")
            raise PlannerFallback(f"Plan structure error: {e}")

        # DAG 유효성 검증
        err = plan.validate()
        if err:
            print(f"[Planner] Plan validation failed: {err}")
            raise PlannerFallback(f"Plan invalid: {err}")

        # 워커 이름 검증 (INTENT_TO_WORKER에 매핑 가능해야 함)
        valid_intents = {i.value for i in Intent}
        for t in plan.tasks:
            if t.worker not in valid_intents:
                print(f"[Planner] Unknown worker '{t.worker}' in task '{t.id}'")
                raise PlannerFallback(f"Unknown worker: {t.worker}")

        print(f"[Planner] Plan: {len(plan.tasks)} tasks, is_trivial={plan.is_trivial}")
        for t in plan.tasks:
            deps = f" ← {t.depends}" if t.depends else ""
            confirm = " [CONFIRM]" if t.needs_confirm else ""
            print(f"[Planner]   {t.id} [{t.worker}] {t.goal}{deps}{confirm}")

        return plan

    @staticmethod
    def _dict_to_plan(data: dict) -> Plan:
        """LLM JSON 출력을 Plan dataclass로 변환"""
        if not isinstance(data, dict):
            raise TypeError(f"expected dict, got {type(data).__name__}")

        tasks_raw = data.get("tasks", [])
        if not isinstance(tasks_raw, list) or not tasks_raw:
            raise ValueError("'tasks' must be a non-empty list")

        tasks: List[Task] = []
        for i, tr in enumerate(tasks_raw):
            if not isinstance(tr, dict):
                raise TypeError(f"task[{i}] must be dict")
            tasks.append(Task(
                id=str(tr.get("id", f"t{i+1}")),
                worker=str(tr["worker"]),  # KeyError if missing
                goal=str(tr["goal"]),
                depends=list(tr.get("depends", [])),
                needs_confirm=bool(tr.get("needs_confirm", False)),
                status=TaskStatus.PENDING,
            ))

        return Plan(
            tasks=tasks,
            rationale=str(data.get("rationale", "")),
            is_trivial=bool(data.get("is_trivial", False)),
        )


# ============================================================
# Singleton factory
# ============================================================

_planner_instance: Optional[Planner] = None


def get_planner() -> Planner:
    """Planner 싱글톤 반환 (intent_classifier와 동일 패턴)"""
    global _planner_instance
    if _planner_instance is None:
        _planner_instance = Planner()
    return _planner_instance


def is_planner_enabled() -> bool:
    """PLANNER_ENABLED 환경변수 체크 (기본 false)"""
    return os.environ.get("PLANNER_ENABLED", "false").lower() == "true"
