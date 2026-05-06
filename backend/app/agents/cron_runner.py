# -*- coding: utf-8 -*-
"""Cron Runner — 스케줄러가 호출하는 외부 Agent 자동 실행기.

설계 원칙:
- self-contained: workspace_uuid + agent_id만 받으면 끝까지 실행 가능
- 결과는 새 chat_session에 기록 (auto_generated=1) + user_notifications로 사용자에게 통보
- 실패해도 알림은 발행 (사용자가 cron이 깨졌다는 걸 알아야 함)

흐름:
1. workspace + agent + cron 등록자 (= attached_by_user_id) 정보 조회
2. 새 session_id 발급, chat_sessions INSERT (auto_generated=1)
3. MisoWorker 인스턴스화
4. 가짜 user 메시지 ("자동 실행: ...") 만들어 stream_response 호출
5. on_chat_model_stream chunk를 모아 assistant 응답 텍스트 구성
6. chat_log_new에 user/assistant 메시지 INSERT
7. user_notifications INSERT (link_url=/chat/{session_id}, type=schedule_done)
"""
import os
import json
import time
import uuid
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, AIMessageChunk

logger = logging.getLogger(__name__)


CRON_PROMPT_DEFAULT = "🔄 자동 실행: 정기 워크플로우를 실행해주세요."


class CronRunResult:
    def __init__(self, session_id: str, status: str, error: Optional[str] = None):
        self.session_id = session_id
        self.status = status  # "success" | "failed"
        self.error = error


async def run_cron_agent(workspace_uuid: str, agent_id: str) -> CronRunResult:
    """단일 cron 실행 — 메서드 시그니처를 좁게 유지하여 스케줄러 등록·테스트 양쪽에서 재사용."""
    from app.core.database import get_database_connection
    from app.services.agent_service import get_agent_service
    from app.services.workspace_service import WorkspaceService
    from app.agents.external_agent_router import instantiate_worker_for_agent

    db = get_database_connection()
    started = time.time()

    # 1) 메타데이터 조회
    workspace_service = WorkspaceService()
    workspace = workspace_service.get_workspace_by_uuid(workspace_uuid)
    if not workspace:
        logger.warning(f"[CronRunner] workspace not found: {workspace_uuid}")
        return CronRunResult(session_id="", status="failed", error="workspace not found")

    # workspace_agents에서 등록자 (= attached_by_user_id) 조회 → cron 실행 user_id로 사용
    attached_user_id: Optional[str] = None
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT attached_by_user_id FROM workspace_agents WHERE workspace_id = %s AND agent_id = %s",
            (workspace_uuid, agent_id),
        )
        row = cursor.fetchone()
        if row:
            attached_user_id = row.get("attached_by_user_id") if isinstance(row, dict) else row[0]
    if not attached_user_id:
        # 부착 끊긴 cron job — 알림 없이 종료 (스케줄러가 정리해야 함)
        logger.warning(
            f"[CronRunner] workspace_agents row missing — cron likely orphan: "
            f"ws={workspace_uuid} agent={agent_id}"
        )
        return CronRunResult(session_id="", status="failed", error="workspace_agent attachment missing")

    # 2) Agent 매니페스트 조회 (raw, 마스킹 없이)
    agent_row: Optional[Dict[str, Any]] = None
    with db.get_cursor() as cursor:
        cursor.execute("SELECT * FROM agents WHERE id = %s AND status = 'active'", (agent_id,))
        agent_row = cursor.fetchone()
    if not agent_row:
        logger.warning(f"[CronRunner] agent not found or not active: {agent_id}")
        return CronRunResult(session_id="", status="failed", error="agent not active")

    manifest = agent_row.get("manifest")
    if isinstance(manifest, str):
        try:
            manifest = json.loads(manifest)
        except Exception:
            manifest = {}
    agent_slug = agent_row["slug"]
    agent_name = agent_row["name"]

    # 3) Cron 트리거 발화 — 매니페스트에 작성자가 정의했으면 그대로, 없으면 default
    triggers = (manifest or {}).get("triggers") or []
    cron_prompt = CRON_PROMPT_DEFAULT
    for trig in triggers:
        if isinstance(trig, dict) and trig.get("type") == "schedule":
            p = trig.get("prompt")
            if isinstance(p, str) and p.strip():
                cron_prompt = p.strip()
                break

    # 4) 새 세션 발급 + chat_sessions INSERT
    session_id = f"cron_{uuid.uuid4().hex[:24]}"
    title = f"🔄 {agent_name} 자동 실행"
    now = datetime.now()
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO chat_sessions
                (session_id, user_id, chat_mode, message_count, title,
                 created_at, updated_at, workspace_id, auto_generated, source_agent_id)
            VALUES (%s, %s, 'normal', 0, %s, %s, %s, %s, 1, %s)
            """,
            (session_id, attached_user_id, title, now, now, workspace_uuid, agent_id),
        )
    logger.info(f"[CronRunner] session created: {session_id} ws={workspace_uuid} agent={agent_slug}")

    # 5) MisoWorker (또는 platform별 worker) 인스턴스화 + stream
    # external_agent_router의 instantiate_worker_for_agent를 그대로 사용 — agent dict 형식만 맞추면 됨
    agent_for_router = {
        "id": agent_id,
        "slug": agent_slug,
        "name": agent_name,
        "platform": agent_row.get("platform"),
        "manifest": manifest,
    }
    try:
        worker = await instantiate_worker_for_agent(agent_for_router)
    except Exception as e:
        logger.exception(f"[CronRunner] worker instantiate failed: {e}")
        await _record_failure_and_notify(
            session_id, attached_user_id, agent_id, agent_name,
            f"Agent 인스턴스 생성 실패: {type(e).__name__}: {e}",
            workspace_uuid, started,
        )
        return CronRunResult(session_id=session_id, status="failed", error=str(e))

    # 6) 실행
    context = {
        "user_id": attached_user_id,
        "session_id": session_id,
        "workspace_id": workspace_uuid,
        "auto_generated": True,
    }
    answer_chunks: List[str] = []
    error_msg: Optional[str] = None
    try:
        async for ev in worker.stream_response(
            messages=[HumanMessage(content=cron_prompt)],
            context=context,
        ):
            # MisoWorker의 텍스트 chunk: {"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk}}
            if isinstance(ev, dict) and ev.get("event") == "on_chat_model_stream":
                chunk_obj = (ev.get("data") or {}).get("chunk")
                if isinstance(chunk_obj, AIMessageChunk):
                    text = chunk_obj.content
                    if isinstance(text, str):
                        answer_chunks.append(text)
    except Exception as e:
        logger.exception(f"[CronRunner] stream_response failed: {e}")
        error_msg = f"실행 중 오류: {type(e).__name__}: {e}"

    answer_text = "".join(answer_chunks).strip() or "(응답 없음)"
    elapsed_ms = int((time.time() - started) * 1000)
    status = "failed" if error_msg else "success"

    # 7) chat_log_new에 user/assistant 메시지 INSERT
    try:
        from app.services.chat_log_service import get_chat_log_service
        chat_log = get_chat_log_service()
        # cron 트리거 user 메시지 + assistant 응답을 한 번에 기록.
        # chat_log_service.save_chat_log은 user/assistant 쌍 기준이므로 그대로 사용.
        await chat_log.save_chat_log(
            session=session_id,
            user_id=attached_user_id,
            chat_mode="normal",
            input_log=cron_prompt,
            output_log=answer_text if not error_msg else f"⚠ {error_msg}",
            workspace_id=workspace_uuid,
            metadata={"auto_generated": True, "source_agent_id": agent_id, "elapsed_ms": elapsed_ms},
        )
    except Exception as e:
        logger.warning(f"[CronRunner] chat_log save failed (non-fatal): {e}")

    # 8) 사용자 알림 (성공/실패 모두)
    try:
        with db.get_cursor() as cursor:
            notif_id = str(uuid.uuid4())
            if status == "success":
                title_n = f"📨 {agent_name} 결과가 도착했습니다"
                body_n = answer_text[:200]
            else:
                title_n = f"⚠ {agent_name} 자동 실행 실패"
                body_n = (error_msg or "")[:200]
            cursor.execute(
                """
                INSERT INTO user_notifications
                    (id, user_id, type, title, body, agent_id, link_url, created_at)
                VALUES (%s, %s, 'schedule_done', %s, %s, %s, %s, %s)
                """,
                (notif_id, attached_user_id, title_n, body_n, agent_id, f"/chat/{session_id}", now),
            )
    except Exception as e:
        logger.warning(f"[CronRunner] notification insert failed (non-fatal): {e}")

    return CronRunResult(session_id=session_id, status=status, error=error_msg)


async def _record_failure_and_notify(
    session_id: str, user_id: str, agent_id: str, agent_name: str,
    error_message: str, workspace_uuid: str, started: float,
) -> None:
    """worker instantiate 단계 실패 시에도 사용자에게 통보 (조용한 실패 방지)."""
    from app.core.database import get_database_connection
    db = get_database_connection()
    now = datetime.now()
    try:
        with db.get_cursor() as cursor:
            notif_id = str(uuid.uuid4())
            cursor.execute(
                """
                INSERT INTO user_notifications
                    (id, user_id, type, title, body, agent_id, link_url, created_at)
                VALUES (%s, %s, 'schedule_done', %s, %s, %s, %s, %s)
                """,
                (notif_id, user_id,
                 f"⚠ {agent_name} 자동 실행 실패",
                 error_message[:200], agent_id, f"/chat/{session_id}", now),
            )
    except Exception as e:
        logger.warning(f"[CronRunner] failure notif insert failed: {e}")
