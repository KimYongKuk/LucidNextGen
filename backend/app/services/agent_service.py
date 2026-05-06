# -*- coding: utf-8 -*-
"""
Agent Service — Hub Agent CRUD + 설치/부착 관리

설계: docs/agent-hub/02_data_model.md, 04_registration_flow.md
- soft delete만 사용 (status='deleted')
- Native Agent는 user_agents에 INSERT 안 함 (코드 레벨 자동 활성화)
- install_count는 user_agents INSERT/DELETE 시 애플리케이션에서 갱신
"""
import uuid
import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from fastapi import HTTPException

from app.core.database import get_database_connection

logger = logging.getLogger(__name__)


VALID_PLATFORMS = {"native", "miso", "runner", "webhook"}
VALID_VISIBILITIES = {"private", "team", "public"}
VALID_CAPABILITIES = {"chat", "run", "scheduled", "async"}
ACTIVE_STATUSES = {"active", "maintenance"}


class AgentService:
    def __init__(self):
        self.db = get_database_connection()

    # ============================================================
    # 카탈로그 조회
    # ============================================================

    def list_agents(
        self,
        platform: Optional[str] = None,
        visibility: Optional[str] = None,
        status: Optional[str] = None,
        is_native_seed: Optional[bool] = None,
        author_user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """Agent 카탈로그 조회 (필터링)"""
        conditions = []
        params: List[Any] = []

        if platform:
            conditions.append("platform = %s")
            params.append(platform)
        if visibility:
            conditions.append("visibility = %s")
            params.append(visibility)
        if status:
            conditions.append("status = %s")
            params.append(status)
        else:
            # 기본: deleted 제외
            conditions.append("status != 'deleted'")
        if is_native_seed is not None:
            conditions.append("is_native_seed = %s")
            params.append(1 if is_native_seed else 0)
        if author_user_id:
            conditions.append("author_user_id = %s")
            params.append(author_user_id)

        where = " AND ".join(conditions) if conditions else "1=1"
        params.extend([limit, offset])

        with self.db.get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT * FROM agents
                WHERE {where}
                ORDER BY install_count DESC, created_at DESC
                LIMIT %s OFFSET %s
                """,
                tuple(params),
            )
            return [self._serialize(row) for row in cursor.fetchall()]

    def get_agent_by_slug(self, slug: str) -> Optional[Dict]:
        """slug로 Agent 조회"""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM agents WHERE slug = %s", (slug,))
            row = cursor.fetchone()
            return self._serialize(row) if row else None

    def get_agent_by_id(self, agent_id: str) -> Optional[Dict]:
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM agents WHERE id = %s", (agent_id,))
            row = cursor.fetchone()
            return self._serialize(row) if row else None

    # ============================================================
    # 등록 / 수정 / 삭제
    # ============================================================

    def create_agent(
        self,
        author_user_id: str,
        slug: str,
        name: str,
        description: str,
        platform: str,
        manifest: Dict,
        capabilities: List[str],
        visibility: str = "private",
        author_team: Optional[str] = None,
        icon: Optional[str] = None,
        tags: Optional[List[str]] = None,
        runner_id: Optional[str] = None,
    ) -> Dict:
        """Agent 등록 — pending_review 상태로 생성"""
        # 검증
        if platform not in VALID_PLATFORMS:
            raise HTTPException(status_code=400, detail=f"platform must be one of {VALID_PLATFORMS}")
        if visibility not in VALID_VISIBILITIES:
            raise HTTPException(status_code=400, detail=f"visibility must be one of {VALID_VISIBILITIES}")
        if not capabilities or not all(c in VALID_CAPABILITIES for c in capabilities):
            raise HTTPException(status_code=400, detail=f"capabilities must be subset of {VALID_CAPABILITIES}")
        if platform == "native":
            raise HTTPException(status_code=403, detail="Native agents are deployed via code, not via API")

        # slug 중복 체크
        if self.get_agent_by_slug(slug):
            raise HTTPException(status_code=409, detail=f"slug '{slug}' already exists")

        agent_id = str(uuid.uuid4())

        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agents (id, slug, name, description, icon, tags,
                                    author_user_id, author_team,
                                    platform, capabilities, visibility, status,
                                    version, manifest, install_count,
                                    is_native_seed, runner_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, FALSE, %s)
                """,
                (
                    agent_id, slug, name, description, icon,
                    json.dumps(tags or [], ensure_ascii=False),
                    author_user_id, author_team,
                    platform,
                    json.dumps(capabilities, ensure_ascii=False),
                    visibility,
                    "pending_review",
                    "1.0.0",
                    json.dumps(manifest, ensure_ascii=False),
                    runner_id,
                ),
            )

        logger.info(f"[AgentService] created agent slug={slug} platform={platform} author={author_user_id}")
        return self.get_agent_by_id(agent_id)

    def update_agent(
        self,
        slug: str,
        author_user_id: str,
        updates: Dict,
    ) -> Dict:
        """Agent 수정 — 새 버전(patch +1) + pending_review 진입.

        manifest 업데이트 시: 기존 runtime의 시크릿(api_key 등)이 마스킹된 값으로
        들어오면 자동으로 DB의 raw 값으로 복원 (응답이 마스킹된 manifest를 그대로
        spread해서 PATCH 보내는 케이스 방지).
        """
        agent = self.get_agent_by_slug(slug)
        if not agent:
            raise HTTPException(status_code=404, detail=f"agent '{slug}' not found")
        if agent["author_user_id"] != author_user_id:
            raise HTTPException(status_code=403, detail="not the author")
        if agent["is_native_seed"]:
            raise HTTPException(status_code=403, detail="Native agents cannot be edited via API")

        # manifest 업데이트 시 시크릿 보존 (raw DB fetch)
        if "manifest" in updates:
            updates["manifest"] = self._preserve_secrets_on_update(
                agent["id"], updates["manifest"]
            )

        # 버전 증가 (patch)
        new_version = self._bump_patch(agent["version"])

        allowed_fields = {"name", "description", "icon", "tags", "manifest",
                          "capabilities", "visibility"}
        set_clauses = []
        params: List[Any] = []
        for key, value in updates.items():
            if key not in allowed_fields:
                continue
            if key in ("tags", "manifest", "capabilities"):
                set_clauses.append(f"{key} = %s")
                params.append(json.dumps(value, ensure_ascii=False))
            else:
                set_clauses.append(f"{key} = %s")
                params.append(value)

        # 버전 + 상태 갱신
        set_clauses.extend(["version = %s", "status = %s"])
        params.extend([new_version, "pending_review"])

        if not set_clauses:
            return agent  # nothing to update

        params.append(agent["id"])
        with self.db.get_cursor() as cursor:
            cursor.execute(
                f"UPDATE agents SET {', '.join(set_clauses)} WHERE id = %s",
                tuple(params),
            )

        logger.info(f"[AgentService] updated agent slug={slug} new_version={new_version}")

        # 매니페스트가 바뀌면 cron schedule도 변동 가능 — 갱신
        # PATCH 시 status=pending_review로 들어가므로 이 시점엔 cron 해제만 일어나고
        # 추후 운영자가 active로 승인할 때 on_agent_manifest_changed가 다시 호출되어 등록됨.
        try:
            from app.agents.cron_scheduler import get_agent_cron_scheduler
            get_agent_cron_scheduler().on_agent_manifest_changed(agent["id"])
        except Exception as e:
            logger.warning(f"[AgentService] cron sync on update failed (non-fatal): {e}")

        return self.get_agent_by_id(agent["id"])

    def soft_delete_agent(self, slug: str, requester_user_id: str, is_operator: bool) -> Dict:
        """soft delete — status='deleted'"""
        agent = self.get_agent_by_slug(slug)
        if not agent:
            raise HTTPException(status_code=404, detail=f"agent '{slug}' not found")
        if agent["author_user_id"] != requester_user_id and not is_operator:
            raise HTTPException(status_code=403, detail="only author or operator can delete")
        if agent["is_native_seed"]:
            raise HTTPException(status_code=403, detail="Native agents cannot be deleted")

        with self.db.get_cursor() as cursor:
            cursor.execute(
                "UPDATE agents SET status = 'deleted' WHERE id = %s",
                (agent["id"],),
            )

        # cron job 모두 해제
        try:
            from app.agents.cron_scheduler import get_agent_cron_scheduler
            get_agent_cron_scheduler().on_agent_manifest_changed(agent["id"])
        except Exception as e:
            logger.warning(f"[AgentService] cron unregister on delete failed (non-fatal): {e}")
        logger.info(f"[AgentService] soft-deleted agent slug={slug} by={requester_user_id}")
        return self.get_agent_by_id(agent["id"])

    def change_status(self, slug: str, new_status: str, by_user_id: str, is_operator: bool) -> Dict:
        """상태 변경 (operator only — maintenance/disabled/active 전환 등)"""
        if not is_operator:
            raise HTTPException(status_code=403, detail="operator only")
        valid_transitions = {"active", "maintenance", "disabled"}
        if new_status not in valid_transitions:
            raise HTTPException(status_code=400, detail=f"invalid status: {new_status}")

        agent = self.get_agent_by_slug(slug)
        if not agent:
            raise HTTPException(status_code=404, detail=f"agent '{slug}' not found")

        with self.db.get_cursor() as cursor:
            cursor.execute(
                "UPDATE agents SET status = %s WHERE id = %s",
                (new_status, agent["id"]),
            )
        logger.info(f"[AgentService] status change slug={slug} -> {new_status} by={by_user_id}")

        # cron job 갱신 — active 외 상태는 모두 해제, active면 매니페스트의 schedule 따라 재등록
        try:
            from app.agents.cron_scheduler import get_agent_cron_scheduler
            get_agent_cron_scheduler().on_agent_manifest_changed(agent["id"])
        except Exception as e:
            logger.warning(f"[AgentService] cron sync on status change failed (non-fatal): {e}")

        return self.get_agent_by_id(agent["id"])

    # ============================================================
    # 사용자 설치/제거 (외부 Agent만 — Native는 코드 자동 활성화)
    # ============================================================

    def install_for_user(self, user_id: str, slug: str) -> Dict:
        """사용자가 외부 Agent 설치"""
        agent = self.get_agent_by_slug(slug)
        if not agent:
            raise HTTPException(status_code=404, detail=f"agent '{slug}' not found")
        if agent["status"] != "active":
            raise HTTPException(status_code=400, detail=f"agent status is {agent['status']}, not active")
        if agent["is_native_seed"]:
            raise HTTPException(status_code=400, detail="Native agents are auto-activated, no install needed")

        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_agents (user_id, agent_id, enabled)
                VALUES (%s, %s, TRUE)
                ON DUPLICATE KEY UPDATE enabled = TRUE
                """,
                (user_id, agent["id"]),
            )
            # install_count 갱신 (애플리케이션 레벨)
            cursor.execute(
                """
                UPDATE agents SET install_count = (
                    SELECT COUNT(*) FROM user_agents WHERE agent_id = %s AND enabled = TRUE
                ) WHERE id = %s
                """,
                (agent["id"], agent["id"]),
            )

        logger.info(f"[AgentService] installed slug={slug} for user={user_id}")
        return {"installed": True, "agent_id": agent["id"]}

    def uninstall_for_user(self, user_id: str, slug: str) -> Dict:
        """사용자가 외부 Agent 제거"""
        agent = self.get_agent_by_slug(slug)
        if not agent:
            raise HTTPException(status_code=404, detail=f"agent '{slug}' not found")
        if agent["is_native_seed"]:
            raise HTTPException(status_code=400, detail="기본 탑재 Agent는 제거할 수 없습니다.")

        with self.db.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM user_agents WHERE user_id = %s AND agent_id = %s",
                (user_id, agent["id"]),
            )
            cursor.execute(
                """
                UPDATE agents SET install_count = (
                    SELECT COUNT(*) FROM user_agents WHERE agent_id = %s AND enabled = TRUE
                ) WHERE id = %s
                """,
                (agent["id"], agent["id"]),
            )

        logger.info(f"[AgentService] uninstalled slug={slug} for user={user_id}")
        return {"uninstalled": True}

    def list_user_active_agents(self, user_id: str) -> List[Dict]:
        """사용자의 Active Agents = Native(전체) ∪ 사용자가 설치한 외부 Agent"""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT a.*
                FROM agents a
                WHERE a.status IN ('active', 'maintenance')
                  AND (
                    a.is_native_seed = TRUE
                    OR a.id IN (
                        SELECT agent_id FROM user_agents
                        WHERE user_id = %s AND enabled = TRUE
                    )
                  )
                ORDER BY a.is_native_seed DESC, a.install_count DESC, a.name ASC
                """,
                (user_id,),
            )
            return [self._serialize(row) for row in cursor.fetchall()]

    # ============================================================
    # 워크스페이스 부착/해제
    # ============================================================

    def attach_to_workspace(self, workspace_id: str, slug: str, by_user_id: str) -> Dict:
        """Agent를 워크스페이스에 부착"""
        agent = self.get_agent_by_slug(slug)
        if not agent:
            raise HTTPException(status_code=404, detail=f"agent '{slug}' not found")
        if agent["status"] != "active":
            raise HTTPException(status_code=400, detail=f"agent status is {agent['status']}, not active")

        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT IGNORE INTO workspace_agents (workspace_id, agent_id, attached_by_user_id)
                VALUES (%s, %s, %s)
                """,
                (workspace_id, agent["id"], by_user_id),
            )
        logger.info(f"[AgentService] attached slug={slug} to workspace={workspace_id} by={by_user_id}")

        # 매니페스트에 schedule trigger 있으면 cron job 등록
        try:
            from app.agents.cron_scheduler import get_agent_cron_scheduler
            get_agent_cron_scheduler().on_workspace_attach(workspace_id, agent["id"])
        except Exception as e:
            logger.warning(f"[AgentService] cron register on attach failed (non-fatal): {e}")

        return {"attached": True, "agent_id": agent["id"]}

    def detach_from_workspace(self, workspace_id: str, slug: str) -> Dict:
        agent = self.get_agent_by_slug(slug)
        if not agent:
            raise HTTPException(status_code=404, detail=f"agent '{slug}' not found")

        with self.db.get_cursor() as cursor:
            cursor.execute(
                "DELETE FROM workspace_agents WHERE workspace_id = %s AND agent_id = %s",
                (workspace_id, agent["id"]),
            )

        # cron job 해제
        try:
            from app.agents.cron_scheduler import get_agent_cron_scheduler
            get_agent_cron_scheduler().on_workspace_detach(workspace_id, agent["id"])
        except Exception as e:
            logger.warning(f"[AgentService] cron unregister on detach failed (non-fatal): {e}")

        return {"detached": True}

    def list_workspace_agents(self, workspace_id: str) -> List[Dict]:
        """워크스페이스에 부착된 Agent 목록"""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT a.*
                FROM agents a
                INNER JOIN workspace_agents wa ON wa.agent_id = a.id
                WHERE wa.workspace_id = %s
                  AND a.status IN ('active', 'maintenance')
                ORDER BY wa.attached_at ASC
                """,
                (workspace_id,),
            )
            return [self._serialize(row) for row in cursor.fetchall()]

    # ============================================================
    # 내부 유틸
    # ============================================================

    def _serialize(self, row: Dict) -> Dict:
        """DB row → API response (JSON 컬럼 디코드, datetime → ISO, 시크릿 마스킹)"""
        if not row:
            return row
        result = dict(row)
        for json_field in ("tags", "capabilities", "manifest"):
            if json_field in result and isinstance(result[json_field], str):
                try:
                    result[json_field] = json.loads(result[json_field])
                except (json.JSONDecodeError, TypeError):
                    pass
        for dt_field in ("created_at", "updated_at"):
            if dt_field in result and isinstance(result[dt_field], datetime):
                result[dt_field] = result[dt_field].isoformat()
        # is_native_seed: tinyint(1) → bool
        if "is_native_seed" in result:
            result["is_native_seed"] = bool(result["is_native_seed"])
        # 시크릿 마스킹 (manifest.runtime.api_key 등 — Phase 1 평문 저장 → 응답 시 마스킹)
        if isinstance(result.get("manifest"), dict):
            result["manifest"] = self._mask_secrets(result["manifest"])
        # author 사번 → 이름/부서 매핑 (UserDirectory 캐시)
        if result.get("author_user_id"):
            try:
                from app.services import user_directory_service
                info = user_directory_service.get_user_info(result["author_user_id"])
                if info:
                    result["author_name"] = info.get("name") or result["author_user_id"]
                    # author_team이 비어있을 때만 디렉토리 값으로 보충
                    if not result.get("author_team"):
                        result["author_team"] = info.get("team") or ""
                    result["author_display"] = (
                        f"{result['author_team']} {info['name']}".strip()
                        if result.get("author_team") else info["name"]
                    )
                else:
                    result["author_name"] = result["author_user_id"]
                    result["author_display"] = result["author_user_id"]
            except Exception:
                result["author_name"] = result["author_user_id"]
                result["author_display"] = result["author_user_id"]
        return result

    def _preserve_secrets_on_update(self, agent_id: str, incoming_manifest: Dict) -> Dict:
        """update 시 들어온 manifest의 시크릿이 마스킹된 값이면 DB raw 값으로 복원.

        프론트가 마스킹된 응답을 그대로 spread해서 PATCH 보내는 실수 방지.
        시크릿 키: runtime.api_key / runtime.auth_token / runtime.password / runtime.secret
        """
        if not isinstance(incoming_manifest, dict):
            return incoming_manifest
        incoming_runtime = incoming_manifest.get("runtime")
        if not isinstance(incoming_runtime, dict):
            return incoming_manifest

        # DB에서 raw manifest 직접 fetch
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT manifest FROM agents WHERE id = %s", (agent_id,))
            row = cursor.fetchone()
            if not row:
                return incoming_manifest
            raw = row.get("manifest")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError:
                    return incoming_manifest
            if not isinstance(raw, dict):
                return incoming_manifest
            existing_runtime = raw.get("runtime") or {}

        # 시크릿 필드별로 마스킹 패턴 확인 + 복원
        SECRET_FIELDS = ("api_key", "auth_token", "password", "secret")
        for sf in SECRET_FIELDS:
            existing_val = existing_runtime.get(sf)
            incoming_val = incoming_runtime.get(sf)
            if not existing_val:
                continue
            # incoming 값이 비어있거나 마스킹 패턴이면 → 기존 값 유지
            if not incoming_val or "***" in str(incoming_val):
                incoming_runtime[sf] = existing_val
                logger.info(f"[AgentService] preserved secret '{sf}' on update (masked value detected)")

        incoming_manifest["runtime"] = incoming_runtime
        return incoming_manifest

    @staticmethod
    def _mask_secrets(manifest: Dict) -> Dict:
        """manifest 안의 시크릿 키 값을 마스킹.
        Phase 1 임시 처리. Phase 2 SSM Parameter Store 도입 후 제거 예정.
        """
        runtime = manifest.get("runtime") or {}
        if isinstance(runtime, dict):
            for secret_key in ("api_key", "auth_token", "password", "secret"):
                if secret_key in runtime and isinstance(runtime[secret_key], str):
                    val = runtime[secret_key]
                    if len(val) > 8:
                        runtime[secret_key] = f"{val[:4]}***{val[-4:]}"
                    else:
                        runtime[secret_key] = "***"
        return manifest

    def _bump_patch(self, version: str) -> str:
        """semver patch +1 (1.0.0 → 1.0.1)"""
        try:
            parts = version.split(".")
            if len(parts) != 3:
                return f"{version}-edited"
            major, minor, patch = parts
            return f"{major}.{minor}.{int(patch) + 1}"
        except (ValueError, IndexError):
            return f"{version}-edited"


# ============================================================
# Dependency injection
# ============================================================
_agent_service_instance: Optional[AgentService] = None


def get_agent_service() -> AgentService:
    global _agent_service_instance
    if _agent_service_instance is None:
        _agent_service_instance = AgentService()
    return _agent_service_instance
