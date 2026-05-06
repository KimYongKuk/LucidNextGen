# -*- coding: utf-8 -*-
"""Cron Scheduler — workspace_agents의 cron 등록을 APScheduler에 wiring.

설계:
- 서버 시작 시 (re)load_all() — 모든 active agents × workspace_agents 행에 대해
  매니페스트의 triggers[type=schedule] cron을 읽어 job 등록
- workspace 부착/해제 시 add_job/remove_job 호출 (route에서 트리거)
- agent 매니페스트 갱신 시 모든 부착 워크스페이스의 job 갱신

Job ID: f"cron_{workspace_uuid}_{agent_id}" — 동일 (ws, agent) 쌍 1개 유일.
"""
import os
import json
import logging
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


CRON_ENABLED = lambda: os.getenv("AGENT_CRON_ENABLED", "true").lower() == "true"
DEFAULT_TIMEZONE = "Asia/Seoul"


class AgentCronScheduler:
    """워크스페이스 부착 + 매니페스트 schedule 트리거를 APScheduler 작업으로 매핑."""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None

    def start(self) -> None:
        if not CRON_ENABLED():
            logger.info("[AgentCronScheduler] disabled via AGENT_CRON_ENABLED")
            return
        if self.scheduler is not None:
            return
        self.scheduler = AsyncIOScheduler()
        self.scheduler.start()
        logger.info("[AgentCronScheduler] started")
        self.reload_all()

    def shutdown(self) -> None:
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None
            logger.info("[AgentCronScheduler] shut down")

    @staticmethod
    def _job_id(workspace_uuid: str, agent_id: str) -> str:
        return f"cron_{workspace_uuid}_{agent_id}"

    @staticmethod
    def _extract_cron_from_manifest(manifest: Any) -> Optional[Dict[str, str]]:
        """매니페스트의 triggers에서 첫 schedule 트리거 추출. 없으면 None."""
        if isinstance(manifest, str):
            try:
                manifest = json.loads(manifest)
            except Exception:
                return None
        if not isinstance(manifest, dict):
            return None
        triggers = manifest.get("triggers") or []
        if not isinstance(triggers, list):
            return None
        for t in triggers:
            if isinstance(t, dict) and t.get("type") == "schedule":
                cron = (t.get("cron") or "").strip()
                if cron:
                    return {
                        "cron": cron,
                        "timezone": t.get("timezone") or DEFAULT_TIMEZONE,
                    }
        return None

    def reload_all(self) -> None:
        """active agents × workspace_agents 전체를 다시 로드."""
        if self.scheduler is None:
            return
        from app.core.database import get_database_connection
        db = get_database_connection()

        # 기존 모든 cron_* job 제거 (멱등 reload)
        for job in list(self.scheduler.get_jobs()):
            if job.id and job.id.startswith("cron_"):
                self.scheduler.remove_job(job.id)

        loaded = 0
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT wa.workspace_id, wa.agent_id, a.manifest, a.name, a.slug, a.status
                FROM workspace_agents wa
                INNER JOIN agents a ON a.id = wa.agent_id
                WHERE a.status = 'active'
                """
            )
            rows = cursor.fetchall() or []

        for row in rows:
            ws = row.get("workspace_id") if isinstance(row, dict) else row[0]
            ag = row.get("agent_id") if isinstance(row, dict) else row[1]
            manifest = row.get("manifest") if isinstance(row, dict) else row[2]
            name = row.get("name") if isinstance(row, dict) else row[3]
            cron_def = self._extract_cron_from_manifest(manifest)
            if not cron_def:
                continue
            try:
                self._add_job(ws, ag, cron_def, name)
                loaded += 1
            except Exception as e:
                logger.warning(
                    f"[AgentCronScheduler] failed to add job ws={ws} agent={ag} cron='{cron_def.get('cron')}': {e}"
                )

        logger.info(f"[AgentCronScheduler] reload_all: {loaded} job(s) registered")

    def _add_job(
        self,
        workspace_uuid: str,
        agent_id: str,
        cron_def: Dict[str, str],
        agent_name: Optional[str] = None,
    ) -> None:
        if self.scheduler is None:
            return
        job_id = self._job_id(workspace_uuid, agent_id)
        try:
            tz = ZoneInfo(cron_def.get("timezone") or DEFAULT_TIMEZONE)
        except Exception:
            tz = ZoneInfo(DEFAULT_TIMEZONE)
        # cron 표현식 예: "0 9 * * *" → APScheduler CronTrigger.from_crontab
        trigger = CronTrigger.from_crontab(cron_def["cron"], timezone=tz)
        self.scheduler.add_job(
            self._dispatch,
            trigger=trigger,
            id=job_id,
            name=f"AgentCron[{agent_name or agent_id}@{workspace_uuid[:8]}]",
            args=[workspace_uuid, agent_id],
            replace_existing=True,
            misfire_grace_time=600,  # 최대 10분 지연 허용
        )

    @staticmethod
    async def _dispatch(workspace_uuid: str, agent_id: str) -> None:
        """APScheduler 콜백 — CronRunner로 위임."""
        from app.agents.cron_runner import run_cron_agent
        try:
            result = await run_cron_agent(workspace_uuid, agent_id)
            logger.info(
                f"[AgentCronScheduler] dispatch done ws={workspace_uuid[:8]} agent={agent_id[:8]} "
                f"status={result.status} session={result.session_id}"
            )
        except Exception as e:
            logger.exception(f"[AgentCronScheduler] dispatch crashed: {e}")

    # ---- 외부 호출용 (라우트가 attach/detach 시 호출) ----

    def on_workspace_attach(self, workspace_uuid: str, agent_id: str) -> None:
        """워크스페이스에 agent 부착 시 호출."""
        if self.scheduler is None:
            return
        from app.core.database import get_database_connection
        db = get_database_connection()
        with db.get_cursor() as cursor:
            cursor.execute("SELECT manifest, name FROM agents WHERE id = %s AND status = 'active'", (agent_id,))
            row = cursor.fetchone()
        if not row:
            return
        manifest = row.get("manifest") if isinstance(row, dict) else row[0]
        name = row.get("name") if isinstance(row, dict) else row[1]
        cron_def = self._extract_cron_from_manifest(manifest)
        if cron_def:
            try:
                self._add_job(workspace_uuid, agent_id, cron_def, name)
                logger.info(f"[AgentCronScheduler] attach: registered cron '{cron_def['cron']}' ws={workspace_uuid[:8]} agent={agent_id[:8]}")
            except Exception as e:
                logger.warning(f"[AgentCronScheduler] attach: cron register failed: {e}")

    def on_workspace_detach(self, workspace_uuid: str, agent_id: str) -> None:
        """워크스페이스에서 agent 해제 시 호출."""
        if self.scheduler is None:
            return
        job_id = self._job_id(workspace_uuid, agent_id)
        try:
            self.scheduler.remove_job(job_id)
            logger.info(f"[AgentCronScheduler] detach: removed job {job_id}")
        except Exception:
            pass  # 없으면 무시

    def on_agent_manifest_changed(self, agent_id: str) -> None:
        """매니페스트(특히 cron) 변경 시 — 해당 agent가 부착된 모든 워크스페이스의 job 갱신."""
        if self.scheduler is None:
            return
        from app.core.database import get_database_connection
        db = get_database_connection()
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT wa.workspace_id, a.manifest, a.name, a.status
                FROM workspace_agents wa
                INNER JOIN agents a ON a.id = wa.agent_id
                WHERE wa.agent_id = %s
                """,
                (agent_id,),
            )
            rows = cursor.fetchall() or []
        for row in rows:
            ws = row.get("workspace_id") if isinstance(row, dict) else row[0]
            manifest = row.get("manifest") if isinstance(row, dict) else row[1]
            name = row.get("name") if isinstance(row, dict) else row[2]
            status = row.get("status") if isinstance(row, dict) else row[3]
            # 기존 job 제거 → status=active이고 cron 있으면 재등록
            self.on_workspace_detach(ws, agent_id)
            if status == "active":
                cron_def = self._extract_cron_from_manifest(manifest)
                if cron_def:
                    try:
                        self._add_job(ws, agent_id, cron_def, name)
                    except Exception as e:
                        logger.warning(f"[AgentCronScheduler] re-register failed: {e}")


_singleton: Optional[AgentCronScheduler] = None


def get_agent_cron_scheduler() -> AgentCronScheduler:
    global _singleton
    if _singleton is None:
        _singleton = AgentCronScheduler()
    return _singleton
