# -*- coding: utf-8 -*-
"""
Agent Hub API 라우트 — Agent CRUD + 설치/부착

설계: docs/agent-hub/04_registration_flow.md
- 등록은 페르소나별 위저드에서 호출 (Phase 1: native 차단, miso/runner/webhook 허용)
- Native Agent는 user_agents 없이 자동 활성화
- soft delete만 사용
"""
import os
import asyncio
import json
import uuid
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage

from app.core.database import get_database_connection
from app.services.agent_service import AgentService, get_agent_service
from app.services.agent_validator_service import get_agent_validator_service
from app.api.dependencies.auth_jwt import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# Operator 권한 체크
# ============================================================
_OPERATOR_USERS = [
    u.strip()
    for u in os.getenv("OPERATOR_USER_IDS", "A2304013").split(",")
    if u.strip()
]


def _is_operator(user_id: Optional[str]) -> bool:
    return bool(user_id) and user_id in _OPERATOR_USERS


# ============================================================
# Pydantic Models
# ============================================================

class AgentCreateRequest(BaseModel):
    slug: str = Field(..., min_length=2, max_length=100, pattern=r"^[a-z0-9-]+$")
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    platform: str = Field(..., description="miso | runner | webhook (native is code-deployed)")
    capabilities: List[str] = Field(..., min_length=1)
    manifest: Dict[str, Any]
    visibility: str = Field("private", description="private | team | public")
    icon: Optional[str] = None
    tags: Optional[List[str]] = None
    author_team: Optional[str] = None
    runner_id: Optional[str] = Field(None, description="Required for runner platform")


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    tags: Optional[List[str]] = None
    capabilities: Optional[List[str]] = None
    manifest: Optional[Dict[str, Any]] = None
    visibility: Optional[str] = None


class AgentStatusChangeRequest(BaseModel):
    status: str = Field(..., description="active | maintenance | disabled")


class AttachToWorkspaceRequest(BaseModel):
    workspace_id: str


class MisoProbeRequest(BaseModel):
    api_key: str = Field(..., min_length=10, description="MISO API key (app-...)")


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., description="approved | rejected | request_changes")
    comment: Optional[str] = None
    report_ids: Optional[List[str]] = Field(None, description="reports reviewed (audit trail)")


class AgentExecuteRequest(BaseModel):
    query: str = Field(..., min_length=1, description="사용자 발화")
    workspace_id: Optional[str] = Field(None, description="실행 컨텍스트 워크스페이스 (선택)")
    session_id: Optional[str] = Field(None, description="채팅 세션 ID (선택)")


# ============================================================
# 카탈로그 조회
# ============================================================

@router.get("/v1/agents")
async def list_agents(
    platform: Optional[str] = Query(None),
    visibility: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    is_native_seed: Optional[bool] = Query(None),
    author: Optional[str] = Query(None, description="filter by author user_id"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Agent 카탈로그 조회 (필터링)"""
    return service.list_agents(
        platform=platform,
        visibility=visibility,
        status=status,
        is_native_seed=is_native_seed,
        author_user_id=author,
        limit=limit,
        offset=offset,
    )


@router.get("/v1/agents/me/active")
async def list_my_active_agents(
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """내 Active Agents = Native(전체) ∪ 사용자가 설치한 외부 Agent"""
    return service.list_user_active_agents(current_user["empno"])


@router.get("/v1/agents/{slug}")
async def get_agent(
    slug: str,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Agent 상세 조회"""
    agent = service.get_agent_by_slug(slug)
    if not agent or agent["status"] == "deleted":
        raise HTTPException(status_code=404, detail=f"agent '{slug}' not found")
    return agent


# ============================================================
# 등록 / 수정 / 삭제
# ============================================================

@router.post("/v1/agents", status_code=201)
async def create_agent(
    request: AgentCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Agent 등록 — pending_review 진입.

    Phase 1 페르소나 게이팅:
    - native: API로 등록 불가 (코드 배포)
    - miso: 모든 사용자
    - runner: operator only
    - webhook: 개발자 (Phase 1은 operator only로 갈음)
    """
    user_id = current_user["empno"]

    # 페르소나 게이팅
    if request.platform == "native":
        raise HTTPException(status_code=403, detail="Native agents are deployed via code")
    if request.platform == "runner" and not _is_operator(user_id):
        raise HTTPException(status_code=403, detail="Runner 매크로 등록은 관리자 전용입니다.")
    if request.platform == "webhook" and not _is_operator(user_id):
        # Phase 1은 webhook도 관리자 전용으로 보수적 시작
        raise HTTPException(status_code=403, detail="Webhook 등록은 관리자 전용입니다.")

    # Runner 플랫폼인데 runner_id 없으면 차단
    if request.platform == "runner" and not request.runner_id:
        raise HTTPException(status_code=400, detail="runner_id required for runner platform")

    # MISO: 등록 시점에 endpoint 자동 판별 (사용자가 mode/endpoint 입력 X)
    manifest = dict(request.manifest)
    if request.platform == "miso":
        rt = dict(manifest.get("runtime") or {})
        api_key = rt.get("api_key")
        if not api_key or not api_key.startswith("app-"):
            raise HTTPException(status_code=400, detail="MISO API 키가 누락되었거나 형식이 잘못되었습니다.")
        detected = await _detect_miso_endpoint_from_key(api_key)
        if not detected["detected"]:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"MISO API 키로 endpoint를 판별하지 못했습니다 "
                    f"(chat={detected['chat_status']}, workflow={detected['workflow_status']}). "
                    "MISO Factory에서 키를 다시 확인해주세요."
                ),
            )
        rt["mode"] = detected["mode"]
        rt["endpoint"] = detected["endpoint"]
        rt["platform"] = "miso"
        manifest["runtime"] = rt

    created = service.create_agent(
        author_user_id=user_id,
        slug=request.slug,
        name=request.name,
        description=request.description,
        platform=request.platform,
        manifest=manifest,
        capabilities=request.capabilities,
        visibility=request.visibility,
        author_team=request.author_team,
        icon=request.icon,
        tags=request.tags,
        runner_id=request.runner_id,
    )

    # 자동 검증 트리거 (백그라운드)
    validator = get_agent_validator_service()
    background_tasks.add_task(validator.trigger_validation, created["id"])

    return created


@router.patch("/v1/agents/{slug}")
async def update_agent(
    slug: str,
    request: AgentUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Agent 수정 — 새 patch 버전 생성 + pending_review 진입 + 재검증"""
    updates = {k: v for k, v in request.model_dump(exclude_unset=True).items() if v is not None}
    updated = service.update_agent(slug, current_user["empno"], updates)

    # 재검증 트리거
    validator = get_agent_validator_service()
    background_tasks.add_task(validator.trigger_validation, updated["id"])

    return updated


@router.delete("/v1/agents/{slug}")
async def delete_agent(
    slug: str,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Agent soft delete (status='deleted'). 작성자 또는 operator만 가능."""
    user_id = current_user["empno"]
    return service.soft_delete_agent(slug, user_id, _is_operator(user_id))


@router.post("/v1/agents/{slug}/status")
async def change_agent_status(
    slug: str,
    request: AgentStatusChangeRequest,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Agent 상태 변경 (operator only) — active / maintenance / disabled"""
    user_id = current_user["empno"]
    return service.change_status(slug, request.status, user_id, _is_operator(user_id))


# ============================================================
# 설치 / 제거 (외부 Agent만)
# ============================================================

@router.post("/v1/agents/{slug}/install")
async def install_agent(
    slug: str,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """사용자가 외부 Agent 설치 (user_agents INSERT). Native는 거부."""
    return service.install_for_user(current_user["empno"], slug)


@router.delete("/v1/agents/{slug}/install")
async def uninstall_agent(
    slug: str,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """사용자가 외부 Agent 제거"""
    return service.uninstall_for_user(current_user["empno"], slug)


# ============================================================
# 워크스페이스 부착 / 해제
# ============================================================

@router.get("/v1/workspaces/{workspace_id}/agents")
async def list_workspace_agents(
    workspace_id: str,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """워크스페이스에 부착된 Agent 목록"""
    return service.list_workspace_agents(workspace_id)


@router.post("/v1/workspaces/{workspace_id}/agents")
async def attach_agent_to_workspace(
    workspace_id: str,
    slug: str = Query(..., description="agent slug"),
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Agent를 워크스페이스에 부착"""
    return service.attach_to_workspace(workspace_id, slug, current_user["empno"])


@router.delete("/v1/workspaces/{workspace_id}/agents/{slug}")
async def detach_agent_from_workspace(
    workspace_id: str,
    slug: str,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """워크스페이스에서 Agent 제거"""
    return service.detach_from_workspace(workspace_id, slug)


# ============================================================
# 검증 리포트 / 승인 (operator)
# ============================================================

@router.get("/v1/agents/{slug}/reviews")
async def list_agent_reviews(
    slug: str,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Agent의 검증 리포트 목록 (작성자 또는 operator만)"""
    user_id = current_user["empno"]
    agent = service.get_agent_by_slug(slug)
    if not agent:
        raise HTTPException(status_code=404, detail=f"agent '{slug}' not found")
    if agent["author_user_id"] != user_id and not _is_operator(user_id):
        raise HTTPException(status_code=403, detail="작성자 또는 관리자만 접근 가능합니다.")

    db = get_database_connection()
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM agent_review_reports
            WHERE agent_id = %s
            ORDER BY created_at DESC
            LIMIT 50
            """,
            (agent["id"],),
        )
        rows = cursor.fetchall()
        for r in rows:
            if isinstance(r.get("findings"), str):
                try:
                    r["findings"] = json.loads(r["findings"])
                except json.JSONDecodeError:
                    pass
        return rows


@router.get("/v1/agents/{slug}/approvals")
async def list_agent_approvals(
    slug: str,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """Agent의 승인 결정 이력 (작성자 또는 operator만)."""
    user_id = current_user["empno"]
    agent = service.get_agent_by_slug(slug)
    if not agent:
        raise HTTPException(status_code=404, detail=f"agent '{slug}' not found")
    if agent["author_user_id"] != user_id and not _is_operator(user_id):
        raise HTTPException(status_code=403, detail="작성자 또는 관리자만 접근 가능합니다.")

    db = get_database_connection()
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT * FROM agent_approvals
            WHERE agent_id = %s
            ORDER BY decided_at DESC
            LIMIT 20
            """,
            (agent["id"],),
        )
        rows = cursor.fetchall()
        for r in rows:
            if isinstance(r.get("report_ids"), str):
                try:
                    r["report_ids"] = json.loads(r["report_ids"])
                except json.JSONDecodeError:
                    pass
        return rows


@router.post("/v1/agents/{slug}/approvals", status_code=201)
async def create_approval_decision(
    slug: str,
    request: ApprovalDecisionRequest,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """인간 승인 결정 (operator only).

    decision:
    - approved → agents.status = 'active'
    - rejected → agents.status = 'rejected'
    - request_changes → agents.status = 'rejected' (작성자 수정 후 재제출)
    """
    user_id = current_user["empno"]
    if not _is_operator(user_id):
        raise HTTPException(status_code=403, detail="관리자 전용입니다.")

    if request.decision not in ("approved", "rejected", "request_changes"):
        raise HTTPException(status_code=400, detail=f"invalid decision: {request.decision}")

    agent = service.get_agent_by_slug(slug)
    if not agent:
        raise HTTPException(status_code=404, detail=f"agent '{slug}' not found")
    if agent["status"] not in ("pending_approval", "pending_review", "rejected"):
        raise HTTPException(
            status_code=400,
            detail=f"agent status is '{agent['status']}', not approvable"
        )

    approval_id = str(uuid.uuid4())
    db = get_database_connection()
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO agent_approvals
                (id, agent_id, agent_version, report_ids, approver_user_id,
                 decision, comment)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                approval_id, agent["id"], agent["version"],
                json.dumps(request.report_ids or [], ensure_ascii=False),
                user_id, request.decision, request.comment,
            ),
        )

    # 상태 갱신
    if request.decision == "approved":
        new_status = "active"
    else:
        new_status = "rejected"
    with db.get_cursor() as cursor:
        cursor.execute(
            "UPDATE agents SET status = %s WHERE id = %s",
            (new_status, agent["id"]),
        )

    # 작성자에게 알림 (자기 자신이 결정한 경우 제외)
    if agent["author_user_id"] != user_id:
        decision_labels = {
            "approved": "✅ 승인",
            "rejected": "❌ 반려",
            "request_changes": "⚠ 변경 요청",
        }
        label = decision_labels.get(request.decision, request.decision)
        notif_id = str(uuid.uuid4())
        body = f"검토 결과: {label}"
        if request.comment:
            body += f"\n\n코멘트: {request.comment}"
        with db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO user_notifications
                    (id, user_id, type, title, body, agent_id, link_url)
                VALUES (%s, %s, 'system', %s, %s, %s, %s)
                """,
                (
                    notif_id,
                    agent["author_user_id"],
                    f"'{agent['name']}' 검토 결과 도착",
                    body,
                    agent["id"],
                    f"/agent-store/{agent['slug']}",
                ),
            )
        logger.info(f"[Approval] notification sent to author={agent['author_user_id']}")

    logger.info(f"[Approval] slug={slug} {request.decision} by={user_id} -> status={new_status}")
    return {
        "approval_id": approval_id,
        "agent_id": agent["id"],
        "decision": request.decision,
        "new_status": new_status,
    }


@router.get("/v1/agents/admin/approval-queue")
async def list_approval_queue(
    current_user: dict = Depends(get_current_user),
):
    """승인 대기 큐 (operator only). pending_approval + pending_review 모두 포함."""
    user_id = current_user["empno"]
    if not _is_operator(user_id):
        raise HTTPException(status_code=403, detail="관리자 전용입니다.")

    db = get_database_connection()
    with db.get_cursor() as cursor:
        cursor.execute(
            """
            SELECT a.*,
                   (SELECT MAX(created_at) FROM agent_review_reports
                    WHERE agent_id = a.id AND agent_version = a.version) AS last_review_at
            FROM agents a
            WHERE a.status IN ('pending_review', 'pending_approval')
              AND a.is_native_seed = FALSE
            ORDER BY a.created_at ASC
            LIMIT 200
            """
        )
        rows = cursor.fetchall()
        for r in rows:
            for f in ("manifest", "tags", "capabilities"):
                if isinstance(r.get(f), str):
                    try:
                        r[f] = json.loads(r[f])
                    except json.JSONDecodeError:
                        pass
        return rows


# ============================================================
# MISO 키 probe — Chat/Workflow 자동 판별
# ============================================================

import httpx as _httpx

MISO_BASE_URL = os.getenv("MISO_API_BASE_URL", "https://api.miso.landf.co.kr")


@router.post("/v1/agents/miso/probe")
async def probe_miso_mode(
    request: MisoProbeRequest,
    current_user: dict = Depends(get_current_user),
):
    """MISO API 키 유효성 검증 + Chat/Workflow 자동 판별.

    실제 호출 기반: 정상 body로 두 endpoint POST → 200 받은 쪽이 정답.
    프론트 입력 단계 실시간 검증에서도 사용.

    응답:
    - {valid: true, mode: "chat" | "workflow", endpoint: "/ext/v1/..."}
    - {valid: false, reason: "..."}
    """
    user_id = current_user["empno"]
    if not _is_operator(user_id):
        raise HTTPException(status_code=403, detail="관리자 전용입니다.")

    api_key = request.api_key.strip()
    if not api_key.startswith("app-"):
        return {"valid": False, "reason": "MISO API 키는 'app-'로 시작합니다."}

    result = await _detect_miso_endpoint_from_key(api_key)
    if result["detected"]:
        return {
            "valid": True,
            "mode": result["mode"],
            "endpoint": result["endpoint"],
            "diagnostic": {
                "chat_status": result["chat_status"],
                "workflow_status": result["workflow_status"],
            },
        }
    return {
        "valid": False,
        "reason": (
            f"MISO 응답에서 정상 endpoint 미발견 — "
            f"chat={result['chat_status']}, workflow={result['workflow_status']}"
        ),
        "diagnostic": {
            "chat_status": result["chat_status"],
            "workflow_status": result["workflow_status"],
            "chat_body": result["chat_body"],
            "workflow_body": result["workflow_body"],
        },
    }


async def _detect_miso_endpoint_from_key(api_key: str) -> Dict:
    """API 키로 MISO endpoint 자동 판별 — 진단 정보 포함 응답.

    응답:
      - {"detected": True, "mode": "chat|workflow", "endpoint": "...",
         "chat_status": int, "workflow_status": int, "chat_body": str, "workflow_body": str}
      - {"detected": False, "chat_status": ..., "workflow_status": ..., "chat_body": ..., "workflow_body": ...}
    """
    import sys
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    chat_url = f"{MISO_BASE_URL}/ext/v1/chat"
    wf_url = f"{MISO_BASE_URL}/ext/v1/workflows/run"

    async def try_endpoint(client, url, body, label):
        try:
            resp = await client.post(url, headers=headers, json=body)
            body_snippet = (resp.text or "")[:300]
            # error code 추출
            error_code = ""
            try:
                data = resp.json()
                if isinstance(data, dict):
                    error_code = (data.get("code") or data.get("error_code") or "").lower()
            except Exception:
                pass
            print(f"[MISO detect] {label} -> {resp.status_code} code={error_code or '-'} | body={body_snippet[:120]}", flush=True, file=sys.stderr)
            return {"status": resp.status_code, "code": error_code, "body": body_snippet}
        except Exception as e:
            print(f"[MISO detect] {label} EXCEPTION: {type(e).__name__}: {e}", flush=True, file=sys.stderr)
            return {"status": 0, "code": "", "body": f"{type(e).__name__}: {str(e)[:200]}"}

    print(f"[MISO detect] start url={MISO_BASE_URL} key_prefix={api_key[:10]}...", flush=True, file=sys.stderr)
    async with _httpx.AsyncClient(timeout=8.0) as client:
        chat_task = try_endpoint(
            client, chat_url,
            {"query": ".", "inputs": {}, "mode": "blocking", "user": "lucid-hub-detect"},
            "chat",
        )
        wf_task = try_endpoint(
            client, wf_url,
            {"inputs": {}, "mode": "blocking", "user": "lucid-hub-detect"},
            "workflow",
        )
        chat_r, wf_r = await asyncio.gather(chat_task, wf_task)

    # 정교한 판정 — status 코드 + error code 종합
    def is_valid_endpoint(r):
        """이 endpoint가 키와 매칭되는가? 200 또는 invalid_param(필드 누락 정상) → True."""
        if r["status"] == 200:
            return True
        if r["status"] == 400 and "invalid_param" in r["code"]:
            return True
        return False

    def is_wrong_endpoint(r):
        """이 endpoint가 키와 매칭 안 됨? 401/403 또는 not_*_app/unauthorized → True."""
        if r["status"] in (401, 403):
            return True
        if r["status"] == 400 and ("not_" in r["code"] or "unauthorized" in r["code"]):
            return True
        return False

    chat_ok = is_valid_endpoint(chat_r)
    wf_ok = is_valid_endpoint(wf_r)
    chat_wrong = is_wrong_endpoint(chat_r)
    wf_wrong = is_wrong_endpoint(wf_r)

    base = {
        "chat_status": chat_r["status"],
        "workflow_status": wf_r["status"],
        "chat_body": chat_r["body"],
        "workflow_body": wf_r["body"],
    }

    # 명확한 케이스: 한쪽 valid + 다른쪽 wrong
    if chat_ok and wf_wrong:
        return {"detected": True, "mode": "chat", "endpoint": "/ext/v1/chat", **base}
    if wf_ok and chat_wrong:
        return {"detected": True, "mode": "workflow", "endpoint": "/ext/v1/workflows/run", **base}
    # 한쪽만 valid (다른쪽 status 모호)
    if chat_ok and not wf_ok:
        return {"detected": True, "mode": "chat", "endpoint": "/ext/v1/chat", **base}
    if wf_ok and not chat_ok:
        return {"detected": True, "mode": "workflow", "endpoint": "/ext/v1/workflows/run", **base}
    # 둘 다 valid (이론상 불가, 안전망: chat 우선)
    if chat_ok and wf_ok:
        return {"detected": True, "mode": "chat", "endpoint": "/ext/v1/chat", **base}
    return {"detected": False, **base}




# ============================================================
# Agent 단독 실행 (orchestrator 우회) — 외부 Agent 검증/명시 호출
# ============================================================

@router.post("/v1/agents/{slug}/execute")
async def execute_agent(
    slug: str,
    request: AgentExecuteRequest,
    current_user: dict = Depends(get_current_user),
    service: AgentService = Depends(get_agent_service),
):
    """등록된 외부 Agent (MISO/Runner/Webhook)를 단독 호출하여 SSE 스트리밍 응답.

    워크스페이스 채팅 자연어 라우팅과 별개로, 명시적으로 Agent를 호출하는 경로.
    """
    user_id = current_user["empno"]
    agent = service.get_agent_by_slug(slug)
    if not agent:
        raise HTTPException(status_code=404, detail=f"agent '{slug}' not found")
    if agent["status"] != "active":
        raise HTTPException(
            status_code=400,
            detail=f"agent '{slug}' status는 '{agent['status']}' — active 상태만 실행 가능",
        )
    if agent["is_native_seed"]:
        raise HTTPException(status_code=400, detail="Native Agent는 기존 채팅으로 호출하세요.")

    platform = agent["platform"]
    manifest = agent.get("manifest") or {}
    runtime = manifest.get("runtime") or {}

    # 마스킹된 manifest로 들어오므로 실제 키는 DB에서 raw fetch
    db = get_database_connection()
    with db.get_cursor() as cursor:
        cursor.execute("SELECT manifest FROM agents WHERE id = %s", (agent["id"],))
        row = cursor.fetchone()
        if row:
            raw_manifest = row.get("manifest")
            if isinstance(raw_manifest, str):
                try:
                    raw_manifest = json.loads(raw_manifest)
                except json.JSONDecodeError:
                    raw_manifest = None
            if isinstance(raw_manifest, dict):
                runtime = raw_manifest.get("runtime") or runtime

    # Worker 인스턴스화
    if platform == "miso":
        from app.agents.workers.miso_worker import MisoWorker
        worker = MisoWorker(
            agent_id=agent["id"],
            agent_slug=slug,
            agent_name=agent["name"],
            runtime=runtime,
        )
    else:
        # Runner/Webhook은 후속 (Phase G-2)
        raise HTTPException(
            status_code=501,
            detail=f"platform '{platform}' 실행은 아직 구현되지 않았습니다.",
        )

    # SSE 스트림 생성
    context = {
        "user_id": user_id,
        "workspace_id": request.workspace_id,
        "session_id": request.session_id,
    }
    messages = [HumanMessage(content=request.query)]

    async def event_stream():
        try:
            async for event in worker.stream_response(messages, context):
                # SSE 형식: "data: {json}\n\n"
                # langchain message chunk는 직렬화 불가 → content만 추출
                if event.get("event") == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk:
                        if hasattr(chunk, "content"):
                            event = {**event, "data": {"chunk": {"content": chunk.content}}}
                        elif isinstance(chunk, dict):
                            pass  # 이미 dict면 그대로
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            err = {"event": "stream_error", "error": f"{type(e).__name__}: {str(e)[:300]}"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
