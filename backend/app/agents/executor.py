"""Executor — Plan의 Task DAG를 병렬/순차로 실행하고 결과를 Blackboard에 저장

Planner-Executor 아키텍처의 실행 엔진.
위상정렬로 의존성 만족된 task부터 asyncio.gather로 병렬 실행.
needs_confirm=True task는 사용자 승인 대기 상태로 중단 (다음 턴에서 재개).

설계 문서: docs/history/2026-04-20_Planner-Executor-design.md
"""

import asyncio
import time
from typing import Dict, Any, AsyncIterator, List, Optional

from langchain_core.messages import HumanMessage, BaseMessage
from langchain_core.tools import BaseTool

from app.agents.state import (
    Task,
    Plan,
    TaskStatus,
    RequestContext,
    INTENT_TO_WORKER,
)
from app.agents.blackboard import Blackboard
from app.agents.workers import get_worker


# Phase 3 설정값 (HITL 승인: 2026-04-20)
MAX_PARALLEL_TASKS: int = 10      # 동시 실행 task 상한
TASK_TIMEOUT_SECONDS: int = 300   # 개별 task 최대 실행 시간 (5분)


class _StreamTagFilter:
    """워커 LLM 스트림에서 HTML 주석/도구 호출 태그를 청크 경계 안전하게 제거.

    a2a_streaming.py의 메인 본문 필터와 동일한 태그 집합을 task_thinking 스트림에도
    적용하기 위한 task-scoped 필터. 청크가 태그 중간에서 잘려도 다음 청크에서 이어
    매칭한다.
    """

    OPEN_TAGS = ("<!--", "<tool_call>", "<tool_response>", "<function_calls>", "<function_result>")
    CLOSE_TAGS = ("-->", "</tool_call>", "</tool_response>", "</function_calls>", "</function_result>")
    MAX_TAG_LEN = max(len(t) for t in OPEN_TAGS + CLOSE_TAGS)

    def __init__(self) -> None:
        self._inside_tag = False
        self._buffer = ""

    def feed(self, text: str) -> str:
        """청크 텍스트를 받아 필터링된 안전 텍스트만 반환. 태그 내부 텍스트는 폐기."""
        out = ""
        for ch in text:
            self._buffer += ch
            if self._inside_tag:
                if any(self._buffer.endswith(t) for t in self.CLOSE_TAGS):
                    self._inside_tag = False
                    self._buffer = ""
                elif len(self._buffer) > 50000:
                    # 안전장치: 종료 태그 없이 너무 길면 버림
                    self._buffer = ""
            else:
                matched = None
                for t in self.OPEN_TAGS:
                    if self._buffer.endswith(t):
                        matched = t
                        break
                if matched:
                    pre_tag = self._buffer[: -len(matched)]
                    out += pre_tag
                    self._inside_tag = True
                    self._buffer = ""
                elif len(self._buffer) > self.MAX_TAG_LEN:
                    out += self._buffer
                    self._buffer = ""
                elif "<" not in self._buffer:
                    out += self._buffer
                    self._buffer = ""
        # 태그 내부 아니고 `<` 후보 없으면 flush
        if not self._inside_tag and self._buffer and "<" not in self._buffer:
            out += self._buffer
            self._buffer = ""
        return out

    def flush(self) -> str:
        """스트림 종료 시 남은 안전 텍스트 반환. 태그 내부였으면 빈 문자열."""
        if self._inside_tag:
            self._buffer = ""
            return ""
        out = self._buffer
        self._buffer = ""
        return out


class Executor:
    """Plan의 Task DAG를 실행하고 Blackboard에 결과 축적"""

    def __init__(
        self,
        max_parallel: int = MAX_PARALLEL_TASKS,
        task_timeout: int = TASK_TIMEOUT_SECONDS,
    ):
        self.max_parallel = max_parallel
        self.task_timeout = task_timeout

    async def execute(
        self,
        plan: Plan,
        context: RequestContext,
        all_tools: List[BaseTool],
        blackboard: Blackboard,
        memory_context: Optional[Dict] = None,
        user_memory_context: Optional[Dict] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Plan을 실행하며 이벤트 스트림 반환

        Yields:
            SSE 이벤트 — task_started/task_completed/task_failed/task_skipped/task_awaiting_confirm
            + 워커 내부 스트리밍 이벤트 (on_chat_model_stream 등)
        """
        print(f"[EXECUTOR] Start — {len(plan.tasks)} tasks (max_parallel={self.max_parallel})")

        completed_ids: set = set()            # status=DONE 인 task id
        terminal_ids: set = set()              # DONE/FAILED/SKIPPED — is_ready 판정용
        awaiting_confirm: List[Task] = []     # 승인 대기 task (본 턴 종료 후 Synthesizer가 안내)
        executor_start = time.time()

        # task_id별 스트림 태그 필터 — task_thinking 출력에서 <!--FOLLOW_UP/HANDOFF/NO_RESULTS-->,
        # <tool_call> 등 LLM이 텍스트로 흘리는 마커를 청크 경계 안전하게 제거한다.
        # 메인 본문은 a2a_streaming.py가 동일 태그를 필터링하지만 task_thinking 경로에는
        # 적용되지 않아 CoT 타임라인에 마커가 노출되던 문제를 해결.
        tag_filters: Dict[str, _StreamTagFilter] = {}

        # 메인 루프 — 모든 task가 종결 상태가 될 때까지
        iteration = 0
        while True:
            iteration += 1
            if iteration > 100:  # safety — 무한 루프 방지
                print("[EXECUTOR] WARNING: iteration limit reached")
                break

            # 실행 준비된 PENDING task 탐색 (의존성은 terminal이면 만족으로 간주)
            ready = [
                t for t in plan.tasks
                if t.status == TaskStatus.PENDING
                and all(dep in terminal_ids for dep in t.depends)
            ]

            if not ready:
                # 더 이상 진행 가능한 task 없음 → 종료
                break

            # 의존 중 실패/SKIPPED가 있으면 해당 task를 SKIPPED로 처리
            for t in list(ready):
                failed_deps = [d for d in t.depends if d not in completed_ids and d in terminal_ids]
                if failed_deps:
                    t.status = TaskStatus.SKIPPED
                    t.error = f"skipped: dependency(ies) {failed_deps} not completed"
                    terminal_ids.add(t.id)
                    ready.remove(t)
                    print(f"[EXECUTOR] {t.id} SKIPPED (deps not done: {failed_deps})")
                    yield {
                        "type": "task_skipped",
                        "task_id": t.id,
                        "worker": t.worker,
                        "goal": t.goal,
                        "reason": t.error,
                    }

            if not ready:
                continue  # 모두 SKIPPED 처리됨 → 다시 루프

            # needs_confirm task는 실행하지 않고 AWAITING_CONFIRM 상태로 전환
            # (본 턴에서는 실행 중단. Synthesizer가 "진행할까요?" 안내)
            confirm_batch = [t for t in ready if t.needs_confirm]
            for t in confirm_batch:
                t.status = TaskStatus.AWAITING_CONFIRM
                terminal_ids.add(t.id)  # terminal 취급 (루프 진행을 위해) — 후속 task는 SKIPPED될 것
                awaiting_confirm.append(t)
                print(f"[EXECUTOR] {t.id} AWAITING_CONFIRM (needs_confirm=true)")
                yield {
                    "type": "task_awaiting_confirm",
                    "task_id": t.id,
                    "worker": t.worker,
                    "goal": t.goal,
                }
                ready.remove(t)

            if not ready:
                continue

            # 병렬 실행 — 이번 wave에서 동시 실행 가능한 task들 (상한 적용)
            wave = ready[: self.max_parallel]
            remaining_overflow = ready[self.max_parallel :]
            if remaining_overflow:
                print(f"[EXECUTOR] Iteration {iteration}: {len(wave)} running, {len(remaining_overflow)} queued")
            else:
                print(f"[EXECUTOR] Iteration {iteration}: running {[t.id for t in wave]}")

            # 각 task에 대한 실행 async task + 이벤트 큐 생성
            queues: Dict[str, asyncio.Queue] = {}
            runners: List[asyncio.Task] = []
            for t in wave:
                t.status = TaskStatus.RUNNING
                t.started_at = time.time()
                queue: asyncio.Queue = asyncio.Queue()
                queues[t.id] = queue
                runner = asyncio.create_task(
                    self._run_task(
                        t, context, all_tools, blackboard,
                        memory_context, user_memory_context,
                        queue,
                    )
                )
                runners.append(runner)
                yield {
                    "type": "task_started",
                    "task_id": t.id,
                    "worker": t.worker,
                    "goal": t.goal,
                }

            # 이벤트 드레인 — 완료된 runner와 queue의 이벤트를 소비
            pending_runners = set(runners)
            while pending_runners:
                # 각 queue에서 사용 가능한 이벤트 yield
                for tid, q in queues.items():
                    while not q.empty():
                        ev = await q.get()
                        if ev is None:
                            continue
                        # Level 1 — 워커의 pre-tool reasoning을 CoT 이벤트로 변환
                        # blackboard에는 _run_task에서 이미 수집되므로 여기서는 UX 표시용
                        # HTML 주석/도구 호출 마커는 task별 필터로 청크 경계 안전하게 제거
                        if isinstance(ev, dict) and ev.get("event") == "on_chat_model_stream":
                            text = Executor._extract_text(ev)
                            if text:
                                tid = ev.get("_task_id") or ""
                                tf = tag_filters.get(tid)
                                if tf is None:
                                    tf = _StreamTagFilter()
                                    tag_filters[tid] = tf
                                filtered = tf.feed(text)
                                if filtered:
                                    yield {
                                        "type": "task_thinking",
                                        "task_id": tid or None,
                                        "content": filtered,
                                    }
                            continue
                        yield ev

                # 완료된 runner 제거 (timeout=0.05로 폴링)
                done, pending_runners = await asyncio.wait(
                    pending_runners, timeout=0.05,
                    return_when=asyncio.FIRST_COMPLETED
                )
                for d in done:
                    # runner 자체의 예외는 _run_task 내부에서 처리하므로 여기선 거의 없음
                    exc = d.exception()
                    if exc:
                        print(f"[EXECUTOR] Runner unexpected exception: {exc}")

            # 마지막 flush — 모든 queue의 남은 이벤트
            for tid, q in queues.items():
                while not q.empty():
                    ev = await q.get()
                    if ev is None:
                        continue
                    # 드레인 루프와 동일한 task_thinking 필터링 적용
                    if isinstance(ev, dict) and ev.get("event") == "on_chat_model_stream":
                        text = Executor._extract_text(ev)
                        if text:
                            ev_tid = ev.get("_task_id") or ""
                            tf = tag_filters.get(ev_tid)
                            if tf is None:
                                tf = _StreamTagFilter()
                                tag_filters[ev_tid] = tf
                            filtered = tf.feed(text)
                            if filtered:
                                yield {
                                    "type": "task_thinking",
                                    "task_id": ev_tid or None,
                                    "content": filtered,
                                }
                        continue
                    yield ev

            # wave task들의 최종 상태를 terminal_ids에 반영
            for t in wave:
                terminal_ids.add(t.id)
                if t.status == TaskStatus.DONE:
                    completed_ids.add(t.id)
                    yield {
                        "type": "task_completed",
                        "task_id": t.id,
                        "worker": t.worker,
                        "goal": t.goal,
                        "elapsed_ms": t.elapsed_ms(),
                        "result_preview": (t.result or "")[:200],
                    }
                elif t.status == TaskStatus.FAILED:
                    yield {
                        "type": "task_failed",
                        "task_id": t.id,
                        "worker": t.worker,
                        "goal": t.goal,
                        "error": t.error,
                        "elapsed_ms": t.elapsed_ms(),
                    }

        # 모든 task_thinking 필터의 남은 버퍼 flush — 태그 외부 안전 텍스트만 방출
        for ev_tid, tf in tag_filters.items():
            tail = tf.flush()
            if tail:
                yield {
                    "type": "task_thinking",
                    "task_id": ev_tid or None,
                    "content": tail,
                }

        total_ms = int((time.time() - executor_start) * 1000)
        stats = {
            "done": sum(1 for t in plan.tasks if t.status == TaskStatus.DONE),
            "failed": sum(1 for t in plan.tasks if t.status == TaskStatus.FAILED),
            "skipped": sum(1 for t in plan.tasks if t.status == TaskStatus.SKIPPED),
            "awaiting_confirm": sum(1 for t in plan.tasks if t.status == TaskStatus.AWAITING_CONFIRM),
        }
        print(f"[EXECUTOR] Done — total={total_ms}ms, {stats}")
        yield {
            "type": "executor_done",
            "total_ms": total_ms,
            "stats": stats,
            "has_awaiting_confirm": len(awaiting_confirm) > 0,
        }

    async def _run_task(
        self,
        task: Task,
        context: RequestContext,
        all_tools: List[BaseTool],
        blackboard: Blackboard,
        memory_context: Optional[Dict],
        user_memory_context: Optional[Dict],
        event_queue: asyncio.Queue,
    ) -> None:
        """단일 task 실행 (워커 호출 + blackboard 기록 + 예외 처리)

        결과 이벤트와 task 내부 스트리밍 이벤트를 event_queue에 push.
        task.status/result/error/completed_at을 in-place 업데이트.
        """
        worker_name = INTENT_TO_WORKER.get(task.worker)
        if not worker_name:
            # Intent enum으로 역변환 시도
            from app.agents.state import Intent
            intent_enum = None
            for i in Intent:
                if i.value == task.worker:
                    intent_enum = i
                    break
            if intent_enum:
                worker_name = INTENT_TO_WORKER.get(intent_enum)

        if not worker_name:
            task.status = TaskStatus.FAILED
            task.error = f"Unknown worker: '{task.worker}'"
            task.completed_at = time.time()
            return

        # 의존 task 결과 수집 → task_dependencies로 주입
        dep_results: Dict[str, str] = {}
        if task.depends:
            dep_results = await blackboard.get_many(task.depends)

        # Task-scoped context 생성 (원본 context 변경 금지)
        task_context: Dict[str, Any] = dict(context)
        task_context["task_goal"] = task.goal
        task_context["task_id"] = task.id
        task_context["task_dependencies"] = dep_results

        # Worker 메시지 — task goal만 담은 단일 HumanMessage
        # (원본 사용자 메시지를 넣으면 워커가 scope를 오해할 수 있음)
        # 단, depends=[] (첫 단계) task에는 사용자 첨부 이미지를 multimodal로 동봉.
        # 후속 task는 blackboard에서 선행 결과 텍스트를 받으므로 이미지 재전달 불필요.
        images = context.get("images") or []
        if images and not task.depends:
            content_blocks: List[Dict[str, Any]] = []
            for img in images:
                media_type = img.get("media_type") if isinstance(img, dict) else getattr(img, "media_type", None)
                data = img.get("base64_data") if isinstance(img, dict) else getattr(img, "base64_data", None)
                if not data:
                    continue
                content_blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type or "image/jpeg",
                        "data": data,
                    },
                })
            content_blocks.append({"type": "text", "text": task.goal})
            messages: List[BaseMessage] = [HumanMessage(content=content_blocks)]
            print(f"[EXECUTOR] {task.id} ({task.worker}): multimodal goal with {len(content_blocks)-1} image(s)")
        else:
            messages = [HumanMessage(content=task.goal)]

        try:
            worker = get_worker(worker_name)
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = f"get_worker failed: {type(e).__name__}: {e}"
            task.completed_at = time.time()
            return

        collected_text_parts: List[str] = []

        async def run_worker():
            """워커 실행하며 스트리밍 이벤트를 queue에 push + 결과 텍스트 수집"""
            async for event in worker.stream_response(
                messages, task_context, all_tools,
                memory_context, user_memory_context,
            ):
                # Level 2 — on_tool_start 감지 시 Haiku narrator 비동기 호출 (fire-and-forget)
                if isinstance(event, dict) and event.get("event") == "on_tool_start":
                    tool_name = event.get("name", "") or event.get("data", {}).get("name", "")
                    tool_input = event.get("data", {}).get("input", {}) if isinstance(event.get("data"), dict) else {}
                    # 비동기로 narration 생성 → queue에 task_narration 이벤트 push
                    # narration 생성이 도구 실행을 블로킹하지 않음
                    asyncio.create_task(
                        Executor._narrate_and_enqueue(
                            task.id, task.goal, tool_name, tool_input, event_queue
                        )
                    )

                # 워커 이벤트를 task_id와 함께 래핑하여 queue에 전달
                wrapped = dict(event) if isinstance(event, dict) else {"event": "raw", "data": event}
                wrapped["_task_id"] = task.id
                await event_queue.put(wrapped)

                # 텍스트 수집 (블랙보드 저장용)
                text = Executor._extract_text(event)
                if text:
                    collected_text_parts.append(text)

        try:
            await asyncio.wait_for(run_worker(), timeout=self.task_timeout)

            result_text = "".join(collected_text_parts).strip()
            if not result_text:
                result_text = f"(no output from {task.worker})"

            await blackboard.put(task.id, result_text)
            task.result = result_text
            task.status = TaskStatus.DONE
            task.completed_at = time.time()

        except asyncio.TimeoutError:
            task.status = TaskStatus.FAILED
            task.error = f"Task timeout ({self.task_timeout}s)"
            task.completed_at = time.time()
            # 부분 결과라도 blackboard에 저장 (후속 task 참고용)
            partial = "".join(collected_text_parts).strip()
            if partial:
                await blackboard.put(task.id, f"[TIMEOUT, 부분결과]\n{partial}")

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = f"{type(e).__name__}: {e}"
            task.completed_at = time.time()

    @staticmethod
    async def _narrate_and_enqueue(
        task_id: str,
        task_goal: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        event_queue: asyncio.Queue,
    ) -> None:
        """Haiku narrator로 도구 호출 내레이션 생성 → queue에 task_narration 이벤트 push.

        비동기 fire-and-forget으로 호출. 실패 시 조용히 무시 (규칙 기반 tool_status 폴백 있음).
        """
        try:
            from app.agents.narrator import get_narrator
            narrator = get_narrator()
            narration = await narrator.narrate(tool_name, tool_input, task_goal)
            if narration:
                await event_queue.put({
                    "type": "task_narration",
                    "_task_id": task_id,
                    "tool": tool_name,
                    "content": narration,
                })
        except Exception as e:
            # 조용히 실패 — 기존 rule-based tool_status가 이미 UX 커버
            print(f"[EXECUTOR] Narrator skipped for {tool_name}: {type(e).__name__}")

    @staticmethod
    def _extract_text(event: Dict[str, Any]) -> str:
        """on_chat_model_stream 이벤트에서 텍스트 추출 (orchestrator와 동일 패턴)"""
        if isinstance(event, dict) and event.get("event") == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content"):
                content = chunk.content
                if isinstance(content, str):
                    return content
                elif isinstance(content, list):
                    text = ""
                    for item in content:
                        if isinstance(item, dict) and "text" in item:
                            text += item["text"]
                        elif isinstance(item, str):
                            text += item
                    return text
        return ""


# ============================================================
# Singleton factory
# ============================================================

_executor_instance: Optional[Executor] = None


def get_executor() -> Executor:
    """Executor 싱글톤 반환"""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = Executor()
    return _executor_instance
