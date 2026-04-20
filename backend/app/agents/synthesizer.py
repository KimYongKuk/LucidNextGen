"""Synthesizer — Blackboard 결과를 사용자용 단일 응답으로 합성

Planner-Executor 아키텍처의 최종 단계. Haiku 모델로 각 task 결과를
가독성 있는 한국어 응답으로 통합한다.

설계 문서: docs/history/2026-04-20_Planner-Executor-design.md
"""

import asyncio
from typing import AsyncIterator, Optional, List

from langchain_core.messages import HumanMessage, SystemMessage, AIMessageChunk

from app.core.model_config import get_orchestrator_config
from app.core.region_fallback import get_region_fallback_manager
from app.agents.state import Plan, TaskStatus, RequestContext
from app.agents.blackboard import Blackboard
from app.agents.workers.base_worker import CachedChatBedrockConverse


SYNTHESIZER_SYSTEM = """당신은 루시드AI의 최종 응답 합성자입니다.

여러 전문 워커가 병렬로 수행한 sub-task 결과들을 받아,
사용자에게 **단일 응답**으로 깔끔하게 합성하세요.

## 핵심 원칙

1. **중복 제거**: 워커들이 겹치는 내용을 냈을 수 있음 → 한 번만 언급
2. **구조화**: 관련 결과는 표/불릿으로 묶어서
3. **사실만**: 결과 텍스트에 없는 내용 추가 금지 (hallucination 금지)
4. **톤**: 간결하고 친근한 한국어
5. **실패 task**: 명시적으로 알림 ("⚠️ X 조회 실패: ...")
6. **건너뛴 task**: 이유 간단히 설명
7. **승인 대기 task**: 사용자에게 진행 여부 묻기 (아래 섹션 참조)

## 승인 대기 (AWAITING_CONFIRM) 처리

일부 task가 쓰기 작업(예약 등록, 메일 발송)이라 사용자 승인 대기 중이면:
1. 먼저 **완료된 task 결과**를 요약해서 보여주기
2. 그 다음 "**아래 내용으로 진행할까요?**" 문구와 함께 승인 필요 항목을 표로 제시
3. 예/아니오로 답할 수 있게 안내

예시:
> ✅ 아래를 확인했습니다:
> - 회의실 현황: 본사 C/R3 비어있음
> - 참석자 일정: 최지원님 충돌 있음
>
> **아래 내용으로 진행할까요?**
>
> | 항목 | 내용 |
> |------|------|
> | 📅 캘린더 등록 | 4/29 14:00~15:00 |
> | 🏢 회의실 예약 | C/R3 |
>
> 진행 원하시면 "응"이라고 답해주세요.

## 출력 형식

- Markdown 사용 가능 (표, 불릿, 이모지 적절히)
- 제목은 `##` 정도, 과도한 중첩 금지
- 본 응답 외 추가 질문 제안이나 메타 설명 금지"""


class Synthesizer:
    """Blackboard + Plan 기반 최종 응답 합성 (Haiku)"""

    def __init__(self):
        self._region_mgr = get_region_fallback_manager()
        self._was_fallback = self._region_mgr.is_fallback_active
        self.llm = self._create_llm()

    def _create_llm(self) -> CachedChatBedrockConverse:
        """Haiku + Prompt Caching. 고정 SYNTHESIZER_SYSTEM(~600 토큰)을 캐시."""
        config = get_orchestrator_config()
        effective_model_id = self._region_mgr.get_model_id(config.model_id)
        return CachedChatBedrockConverse(
            model=effective_model_id,
            temperature=0.3,
            max_tokens=4096,
        )

    def _ensure_correct_region(self):
        current_fallback = self._region_mgr.is_fallback_active
        if current_fallback != self._was_fallback:
            self._was_fallback = current_fallback
            self.llm = self._create_llm()

    async def synthesize(
        self,
        original_message: str,
        plan: Plan,
        blackboard: Blackboard,
        context: RequestContext,
    ) -> AsyncIterator[dict]:
        """Blackboard 결과를 합성하여 on_chat_model_stream 형식 이벤트로 yield

        Yields:
            워커가 생성하는 것과 동일 형식의 {"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk}}
            이벤트. chat.py / 프론트가 기존 처리 로직 재사용 가능.
        """
        self._ensure_correct_region()

        # Plan이 단일 trivial task이고 성공했으면 워커 결과를 그대로 통과시켜도 됨
        # (불필요한 Haiku 호출 방지)
        if plan.is_trivial and len(plan.tasks) == 1 and plan.tasks[0].status == TaskStatus.DONE:
            text = plan.tasks[0].result or ""
            print(f"[SYNTHESIZER] Trivial passthrough — {len(text)} chars (skip LLM)")
            if text:
                yield {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": AIMessageChunk(content=text)},
                }
            return

        # 합성 프롬프트 빌드
        prompt = self._build_prompt(original_message, plan, blackboard)

        try:
            import time as _t
            t0 = _t.time()
            # Bedrock Converse의 llm.astream()이 실제로 토큰 단위 스트리밍을 하지 않음
            # (전체 응답을 1개 chunk로 덤프) → ainvoke로 받은 뒤 수동 청킹.
            response = await self.llm.ainvoke([
                SystemMessage(content=SYNTHESIZER_SYSTEM),
                HumanMessage(content=prompt),
            ])
            invoke_ms = int((_t.time() - t0) * 1000)

            # content 텍스트 추출 (str 또는 List[Dict])
            text = ""
            if hasattr(response, "content"):
                c = response.content
                if isinstance(c, str):
                    text = c
                elif isinstance(c, list):
                    for it in c:
                        if isinstance(it, dict) and "text" in it:
                            text += it["text"]
                        elif isinstance(it, str):
                            text += it

            print(f"[SYNTHESIZER] ainvoke {invoke_ms}ms, total_chars={len(text)} → 수동 청킹(5자)")

            # 수동 청킹: 5자씩, 5ms delay — chat.py 레거시 path와 동일한 UX
            CHUNK_SIZE = 5
            CHUNK_DELAY = 0.005
            for i in range(0, len(text), CHUNK_SIZE):
                mini = text[i:i + CHUNK_SIZE]
                yield {
                    "event": "on_chat_model_stream",
                    "data": {"chunk": AIMessageChunk(content=mini)},
                }
                await asyncio.sleep(CHUNK_DELAY)

            total_ms = int((_t.time() - t0) * 1000)
            print(f"[SYNTHESIZER] Stream done — chars={len(text)}, total={total_ms}ms")

        except Exception as e:
            print(f"[SYNTHESIZER] Streaming failed: {type(e).__name__}: {e}")
            # 실패 시 raw 결과를 그대로 덤프 (최후 safety)
            fallback = self._build_fallback_text(plan, blackboard)
            yield {
                "event": "on_chat_model_stream",
                "data": {"chunk": AIMessageChunk(content=fallback)},
            }

    def _build_prompt(
        self,
        original_message: str,
        plan: Plan,
        blackboard: Blackboard,
    ) -> str:
        """Haiku에게 전달할 합성 프롬프트 구성"""
        lines: List[str] = []
        lines.append("## 사용자 원본 요청")
        lines.append(original_message)
        lines.append("")
        lines.append("## Plan rationale")
        lines.append(plan.rationale or "(없음)")
        lines.append("")
        lines.append("## Task별 실행 결과")
        lines.append("")

        for t in plan.tasks:
            status_icon = {
                TaskStatus.DONE: "✅",
                TaskStatus.FAILED: "❌",
                TaskStatus.SKIPPED: "⏭️",
                TaskStatus.AWAITING_CONFIRM: "⏳",
                TaskStatus.PENDING: "⏸️",
                TaskStatus.RUNNING: "⏳",
            }.get(t.status, "?")

            header = f"### {status_icon} [{t.id}] {t.worker} — {t.goal}"
            if t.needs_confirm:
                header += " (승인 필요)"
            lines.append(header)

            if t.status == TaskStatus.DONE:
                result = (t.result or "").strip()
                # HTML 코멘트 마커(FOLLOW_UP / HANDOFF / NO_RESULTS 등) 제거 —
                # Synthesizer LLM이 이를 본문으로 오해/인용하는 문제 방지
                import re as _re
                result = _re.sub(r'<!--[A-Z_]+:?[^>]*-->', '', result)
                result = _re.sub(r'\n{3,}', '\n\n', result).strip()
                # 결과가 너무 길면 잘라서 전달 (토큰 절약)
                if len(result) > 4000:
                    result = result[:4000] + f"\n\n...[{len(result)-4000}자 생략]"
                lines.append(result or "(빈 결과)")
            elif t.status == TaskStatus.FAILED:
                lines.append(f"**실패:** {t.error or 'unknown error'}")
            elif t.status == TaskStatus.SKIPPED:
                lines.append(f"**건너뜀:** {t.error or '선행 task 실패/미완료'}")
            elif t.status == TaskStatus.AWAITING_CONFIRM:
                lines.append("**승인 대기 중:** 사용자 확인 필요 (아직 실행하지 않음)")

            lines.append("")

        lines.append("## 지시")
        lines.append("위 결과를 사용자 원본 요청에 대한 **단일 응답**으로 합성하세요.")
        has_confirm = any(t.status == TaskStatus.AWAITING_CONFIRM for t in plan.tasks)
        if has_confirm:
            lines.append("**AWAITING_CONFIRM task가 있으므로 반드시 '아래 내용으로 진행할까요?' 문구로 사용자 승인을 요청하세요.**")

        return "\n".join(lines)

    @staticmethod
    def _build_fallback_text(plan: Plan, blackboard: Blackboard) -> str:
        """Haiku 실패 시 최소 폴백 응답 (raw task 결과 덤프)"""
        lines = ["요청을 처리했습니다."]
        for t in plan.tasks:
            if t.status == TaskStatus.DONE and t.result:
                lines.append(f"\n**{t.goal}:**")
                lines.append(t.result[:1000])
            elif t.status == TaskStatus.FAILED:
                lines.append(f"\n⚠️ {t.goal} 실패: {t.error}")
            elif t.status == TaskStatus.AWAITING_CONFIRM:
                lines.append(f"\n⏳ {t.goal} — 승인 대기 중. '응'이라고 답하시면 진행합니다.")
        return "\n".join(lines)


# ============================================================
# Singleton factory
# ============================================================

_synthesizer_instance: Optional[Synthesizer] = None


def get_synthesizer() -> Synthesizer:
    global _synthesizer_instance
    if _synthesizer_instance is None:
        _synthesizer_instance = Synthesizer()
    return _synthesizer_instance
