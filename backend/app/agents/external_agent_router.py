"""External Agent Router — 워크스페이스 부착 외부 Agent 사전 라우터.

Orchestrator 진입 시점에 호출:
- workspace_id 있고 부착된 외부 Agent (MISO/Runner/Webhook)가 1개 이상이면
- Haiku에게 "이 발화가 부착 Agent와 매칭되는지 / 어떤 slug?" 질문
- 매칭되면 → MisoWorker 등 인스턴스화 + 직접 stream
- 매칭 안 되면 → orchestrator의 기존 흐름 (Planner-Executor 또는 Legacy IntentClassifier)으로 흘러감

설계: docs/agent-hub/05_routing.md
"""
import json
import logging
from typing import Optional, List, Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_aws import ChatBedrockConverse

from app.core.database import get_database_connection
from app.core.model_config import get_orchestrator_config

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are an external agent router.

User is in a workspace with several "external agents" attached. Decide if user's
utterance should trigger one of them, or skip (let the default chat flow handle it).

Output strict JSON only:
- {"action": "external", "slug": "...", "rationale": "..."}  ← matched
- {"action": "skip", "rationale": "..."}                      ← no clear match

Rules:
- ONLY pick an agent when the user's intent CLEARLY matches the agent's hint.
- If multiple agents match, pick the most specific one.
- General conversation, casual greetings, file/web search → skip.
- "@slug" or "/use slug" mentions → external with that slug.
"""


def _build_user_prompt(message: str, agents: List[Dict[str, Any]]) -> str:
    """Agent 후보를 포함한 user prompt 구성."""
    lines = ["사용자 발화:", f'  "{message}"', "", "부착된 외부 Agent:"]
    for a in agents:
        slug = a.get("slug")
        name = a.get("name") or slug
        platform = a.get("platform") or "?"
        manifest = a.get("manifest") or {}
        if isinstance(manifest, str):
            try:
                manifest = json.loads(manifest)
            except json.JSONDecodeError:
                manifest = {}
        intent_hints = (manifest.get("intent_hints") or {}).get("system_prompt") or ""
        desc = a.get("description") or ""
        lines.append(f"- slug={slug} | platform={platform} | name={name}")
        if desc:
            lines.append(f"  description: {desc[:200]}")
        if intent_hints:
            lines.append(f"  use_when: {intent_hints[:300]}")
    lines.append("")
    lines.append("판정:")
    return "\n".join(lines)


class ExternalAgentRouter:
    def __init__(self):
        cfg = get_orchestrator_config()
        self.llm = ChatBedrockConverse(
            model_id=cfg.model_id,
            max_tokens=200,
            temperature=0,
        )

    async def fetch_attached_external_agents(self, workspace_id: str) -> List[Dict[str, Any]]:
        """workspace_agents에서 부착된 외부 Agent (Native 제외) fetch.

        manifest는 raw로 fetch (DB 직접) — _serialize의 마스킹 적용 안 됨.
        실행 시 api_key 평문 필요하므로.
        """
        db = get_database_connection()
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT a.id, a.slug, a.name, a.description, a.platform,
                       a.manifest, a.runner_id
                FROM agents a
                INNER JOIN workspace_agents wa ON wa.agent_id = a.id
                WHERE wa.workspace_id = %s
                  AND a.status = 'active'
                  AND a.is_native_seed = 0
                ORDER BY wa.attached_at DESC
                """,
                (workspace_id,),
            )
            rows = cursor.fetchall()
            for r in rows:
                if isinstance(r.get("manifest"), str):
                    try:
                        r["manifest"] = json.loads(r["manifest"])
                    except json.JSONDecodeError:
                        pass
            return rows

    async def route(
        self,
        message: str,
        attached_agents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """외부 Agent 매칭 결정.

        반환:
          - {"action": "external", "slug": ..., "agent": {...}, "rationale": ...}
          - {"action": "skip", "rationale": ...}
        """
        if not attached_agents:
            return {"action": "skip", "rationale": "no attached external agents"}

        # 명시적 @slug 또는 /use slug 패턴 우선 (LLM 호출 회피)
        for prefix in ("@", "/use "):
            if message.lstrip().startswith(prefix):
                token = message.lstrip()[len(prefix):].split(maxsplit=1)[0]
                for a in attached_agents:
                    if a["slug"] == token:
                        return {"action": "external", "slug": token, "agent": a, "rationale": "explicit mention"}

        # LLM 분류
        try:
            user_prompt = _build_user_prompt(message, attached_agents)
            response = await self.llm.ainvoke([
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ])
            content = (response.content or "").strip()
            # JSON 추출 (LLM이 ```json 감쌀 수 있음)
            if content.startswith("```"):
                content = content.strip("`")
                if content.startswith("json"):
                    content = content[4:].strip()
            data = json.loads(content)
        except Exception as e:
            logger.warning(f"[ExternalAgentRouter] LLM parse failed: {e} — skip fallback")
            return {"action": "skip", "rationale": f"LLM error: {e}"}

        action = data.get("action")
        if action == "external":
            slug = data.get("slug")
            agent = next((a for a in attached_agents if a["slug"] == slug), None)
            if not agent:
                return {"action": "skip", "rationale": f"slug '{slug}' not in attached list"}
            return {
                "action": "external",
                "slug": slug,
                "agent": agent,
                "rationale": data.get("rationale", ""),
            }
        return {"action": "skip", "rationale": data.get("rationale", "")}


_router_instance: Optional[ExternalAgentRouter] = None


def get_external_agent_router() -> ExternalAgentRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = ExternalAgentRouter()
    return _router_instance


async def instantiate_worker_for_agent(agent: Dict[str, Any]):
    """매니페스트 기반 외부 Worker 인스턴스화.

    Phase 1: MISO만 지원. Runner/Webhook은 후속.
    """
    platform = agent.get("platform")
    runtime = (agent.get("manifest") or {}).get("runtime") or {}

    if platform == "miso":
        from app.agents.workers.miso_worker import MisoWorker
        return MisoWorker(
            agent_id=agent["id"],
            agent_slug=agent["slug"],
            agent_name=agent["name"],
            runtime=runtime,
        )
    raise NotImplementedError(f"platform '{platform}' not yet supported")
