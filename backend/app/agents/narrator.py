"""Narrator — 도구 호출을 사용자 친화적 내레이션으로 변환 (Haiku 기반)

CoT 가시성 UX의 Level 2 구성요소. `on_tool_start` 이벤트에서 tool_name + tool_input + task_goal을
받아 1줄(약 40자) 자연어 설명 생성.

비동기 fire-and-forget으로 호출되어 실제 도구 실행을 블로킹하지 않음.
실패 시 조용히 무시 (규칙 기반 fallback이 a2a_streaming에 이미 있음).
"""

import json
from typing import Optional

from langchain_aws import ChatBedrockConverse
from langchain_core.messages import HumanMessage

from app.core.model_config import get_orchestrator_config
from app.core.region_fallback import get_region_fallback_manager


NARRATOR_PROMPT = """지금 AI Agent가 수행 중인 도구 호출을 **사용자에게 보여줄 1줄 설명**으로 바꿔주세요.

**규칙:**
- 한국어
- 40자 이내 (짧을수록 좋음)
- 맨 앞에 관련 이모지 1개
- "~중..." 같은 현재진행형으로 끝
- 도구 이름/기술 용어 노출 금지 — 사용자 관점에서 무엇을 하는지만
- 구체적 정보(키워드/날짜/사번 등)는 포함, 없으면 생략
- 따옴표/마침표 등 추가 텍스트 없이 한 줄만 출력

**컨텍스트:**
- 전체 Task 목표: {task_goal}
- 호출되는 도구 이름: {tool_name}
- 도구 입력 (일부): {tool_input}

**예시 출력:**
- 🔍 'PR파트' 관련 메일을 찾아보는 중...
- 🏢 성서사무실 23시 빈 회의실 확인 중...
- 📅 2026-04-28 일정 충돌 확인 중...
- 📝 회의 아젠다 초안을 작성하는 중...

출력:"""


class Narrator:
    """Haiku 기반 내레이션 생성기 (싱글톤)"""

    def __init__(self):
        self._region_mgr = get_region_fallback_manager()
        self._was_fallback = self._region_mgr.is_fallback_active
        self.llm = self._create_llm()

    def _create_llm(self) -> ChatBedrockConverse:
        """Haiku, max_tokens 작게 — 1줄이면 충분"""
        config = get_orchestrator_config()  # 기본 Haiku
        effective_model_id = self._region_mgr.get_model_id(config.model_id)
        return ChatBedrockConverse(
            model=effective_model_id,
            temperature=0.3,  # 약간의 자연스러움
            max_tokens=80,    # 1줄 한국어면 충분
        )

    def _ensure_correct_region(self):
        current_fallback = self._region_mgr.is_fallback_active
        if current_fallback != self._was_fallback:
            self._was_fallback = current_fallback
            self.llm = self._create_llm()

    async def narrate(
        self,
        tool_name: str,
        tool_input: dict,
        task_goal: str = "",
    ) -> Optional[str]:
        """도구 호출 1건에 대한 내레이션 생성

        Returns: 1줄 내레이션 (이모지 포함) 또는 None (실패 시)
        """
        self._ensure_correct_region()

        try:
            # 입력 일부만 잘라서 전달 (토큰 절약, 민감정보 축소)
            input_str = json.dumps(tool_input or {}, ensure_ascii=False)
            if len(input_str) > 300:
                input_str = input_str[:300] + "...[생략]"

            prompt = NARRATOR_PROMPT.format(
                task_goal=(task_goal or "(지정 없음)")[:200],
                tool_name=tool_name,
                tool_input=input_str,
            )

            response = await self.llm.ainvoke([HumanMessage(content=prompt)])

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

            text = text.strip().split("\n")[0].strip()  # 첫 줄만
            # 따옴표 제거
            text = text.strip('"\'`')
            if not text or len(text) > 100:
                return None

            return text

        except Exception as e:
            print(f"[Narrator] Failed: {type(e).__name__}: {e}")
            return None


# Singleton
_narrator_instance: Optional[Narrator] = None


def get_narrator() -> Narrator:
    global _narrator_instance
    if _narrator_instance is None:
        _narrator_instance = Narrator()
    return _narrator_instance
