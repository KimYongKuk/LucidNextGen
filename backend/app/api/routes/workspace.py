# -*- coding: utf-8 -*-
"""
워크스페이스 API 라우트

워크스페이스 생성, 조회, 수정, 삭제 및 파일 관리 엔드포인트를 제공합니다.
"""
import logging
import os
import uuid
import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, BackgroundTasks
from pydantic import BaseModel
from datetime import datetime

from app.services.workspace_service import WorkspaceService, get_workspace_service
from app.api.dependencies.auth_jwt import get_current_user
from app.api.dependencies.authz import assert_workspace_owner, get_current_admin

router = APIRouter()
logger = logging.getLogger(__name__)

# 최대 파일 크기 (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# 공용 워크스페이스를 생성/전환할 수 있는 운영자 사번 (기본 A2304013)
# 프론트엔드의 NEXT_PUBLIC_OPERATOR_USERS와 동일한 의미를 백엔드에서 강제함
_OPERATOR_USERS = [
    u.strip()
    for u in os.getenv("OPERATOR_USER_IDS", "A2304013").split(",")
    if u.strip()
]


def _is_operator(user_id: Optional[str]) -> bool:
    return bool(user_id) and user_id in _OPERATOR_USERS


# In-memory status tracking (file_id -> dict)
WORKSPACE_UPLOAD_STATUS = {}

# ============================================================================
# Pydantic Models
# ============================================================================

class WorkspaceCreate(BaseModel):
    name: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    is_public: Optional[bool] = False

class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    is_public: Optional[bool] = None

class WorkspaceResponse(BaseModel):
    id: int
    uuid: str
    user_id: str
    name: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    is_public: bool = False
    created_at: datetime
    updated_at: datetime

class FileResponse(BaseModel):
    file_id: str
    filename: str
    chunk_count: int
    uploaded_at: Optional[datetime] = None


class ChunkSearchRequest(BaseModel):
    pattern_type: Optional[str] = None  # resident_number, account_number, phone_number, credit_card, email
    workspace_id: Optional[int] = None  # 특정 워크스페이스만 검색 (None이면 전체)
    limit: int = 50
    offset: int = 0


class ChunkSearchResult(BaseModel):
    workspace_id: int
    workspace_name: str
    user_id: str
    file_id: str
    filename: str
    chunk_index: int
    chunk_text: str
    matched_text: str

# ============================================================================
# Endpoints
# ============================================================================

@router.get("/v1/workspaces", response_model=List[WorkspaceResponse])
async def list_workspaces(
    current_user: dict = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """사용자의 모든 워크스페이스 목록 조회 (본인 소유만, JWT 인증 사번 기준)"""
    return service.get_workspaces(current_user["empno"])

@router.get("/v1/workspaces/public", response_model=List[WorkspaceResponse])
async def list_public_workspaces(
    service: WorkspaceService = Depends(get_workspace_service)
):
    """공용 워크스페이스 목록 조회 (모든 사용자에게 노출)"""
    return service.get_public_workspaces()

@router.post("/v1/workspaces", response_model=WorkspaceResponse)
async def create_workspace(
    workspace: WorkspaceCreate,
    current_user: dict = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """새 워크스페이스 생성 (owner 는 JWT 인증 사번으로 강제, is_public=True 는 운영자만)"""
    authenticated_empno = current_user["empno"]
    try:
        is_public = bool(workspace.is_public) and _is_operator(authenticated_empno)
        if workspace.is_public and not is_public:
            logger.warning(
                f"[SECURITY] non_operator_public_attempt empno={authenticated_empno} forcing is_public=False"
            )
        return service.create_workspace(
            user_id=authenticated_empno,
            name=workspace.name,
            description=workspace.description,
            instructions=workspace.instructions,
            is_public=is_public,
        )
    except Exception as e:
        logger.error(f"Failed to create workspace: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/v1/workspaces/{workspace_uuid}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_uuid: str,
    current_user: dict = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """UUID로 워크스페이스 조회 (소유자 또는 공용 워크스페이스면 허용)"""
    workspace = service.get_workspace_by_uuid(workspace_uuid)
    assert_workspace_owner(workspace, current_user["empno"])
    return workspace

@router.put("/v1/workspaces/{workspace_uuid}")
async def update_workspace(
    workspace_uuid: str,
    update_data: WorkspaceUpdate,
    current_user: dict = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """워크스페이스 메타데이터 업데이트 (소유자만, is_public 전환은 운영자만)"""
    authenticated_empno = current_user["empno"]
    workspace = service.get_workspace_by_uuid(workspace_uuid)
    assert_workspace_owner(workspace, authenticated_empno, allow_public=False)

    # is_public 전환은 운영자만 허용
    is_public = update_data.is_public
    if is_public is not None and not _is_operator(authenticated_empno):
        raise HTTPException(status_code=403, detail="Only operators can toggle public workspace")

    success = service.update_workspace(
        workspace_id=workspace["id"],
        name=update_data.name,
        description=update_data.description,
        instructions=update_data.instructions,
        is_public=is_public,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Workspace not found or no changes made")

    return {"status": "success", "message": "Workspace updated"}

@router.delete("/v1/workspaces/{workspace_uuid}")
async def delete_workspace(
    workspace_uuid: str,
    current_user: dict = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """워크스페이스 및 파일 삭제 (소유권 검증)"""
    workspace = service.get_workspace_by_uuid(workspace_uuid)
    assert_workspace_owner(workspace, current_user["empno"], allow_public=False)

    success = service.delete_workspace(workspace["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"status": "success", "message": "Workspace deleted"}

# ============================================================================
# Workspace File Management (Background Processing)
# ============================================================================

async def _process_workspace_upload_background(
    file_content: bytes,
    filename: str,
    workspace_id: int,
    file_id: str,
    service: WorkspaceService,
):
    """
    백그라운드에서 워크스페이스 파일 업로드 처리

    채팅/Admin 업로드와 동일하게 메인 프로세스에서 직접 실행하여
    싱글톤 ChromaDBService(임베딩 모델)를 공유합니다.

    Status 값:
    - processing / completed / completed_disk_only / failed
    """
    from app.api.routes.upload import _detect_file_encryption

    WORKSPACE_UPLOAD_STATUS[file_id] = {
        "status": "processing",
        "filename": filename,
        "workspace_id": workspace_id,
        "message": "Processing started",
        "progress": 0
    }
    logger.info(f"Starting background upload for {filename} (ID: {file_id}) to workspace {workspace_id}")

    # 표준 경고 문구 (사용자 노출용 — 내부 경로/에러 상세는 포함하지 않음)
    ENCRYPTED_WARNING = (
        "암호화된 파일은 IT VOC 등록을 위한 파일 업로드만 가능합니다.\n"
        "암호화된 파일은 분석/요약이 불가하므로, 복호화 후 업로드 하세요."
    )
    INDEXING_FAILED_WARNING = (
        "이 파일은 분석/요약용 인덱싱에 실패했습니다.\n"
        "IT VOC 등록을 위한 첨부는 가능하며, 분석/요약이 필요하시면 복호화 후 업로드 하세요."
    )

    # 1) 사전 암호화 감지
    is_encrypted, enc_reason = _detect_file_encryption(file_content, filename)
    if is_encrypted:
        logger.warning(f"Encrypted file detected, skipping embedding: {filename} ({enc_reason})")
        WORKSPACE_UPLOAD_STATUS[file_id] = {
            "status": "completed_disk_only",
            "filename": filename,
            "workspace_id": workspace_id,
            "message": "업로드 완료",
            "warning": ENCRYPTED_WARNING,
            "progress": 100,
        }
        await asyncio.sleep(600)
        if file_id in WORKSPACE_UPLOAD_STATUS:
            del WORKSPACE_UPLOAD_STATUS[file_id]
        return

    # 2) 정상 임베딩 시도
    try:
        result = await service.upload_file_from_content(
            workspace_id=workspace_id,
            file_content=file_content,
            filename=filename,
            file_id=file_id
        )
        WORKSPACE_UPLOAD_STATUS[file_id] = {
            "status": "completed",
            "filename": filename,
            "workspace_id": workspace_id,
            "message": "Upload complete",
            "progress": 100,
            "result": result
        }
        logger.info(f"Background upload complete for {filename} (ID: {file_id})")
    except Exception as e:
        # 내부 에러 상세는 로그에만 남기고 사용자에게는 표준 안내만
        logger.warning(f"Embedding failed (disk-only success) for {filename} (ID: {file_id}): {e}")
        import traceback
        traceback.print_exc()
        WORKSPACE_UPLOAD_STATUS[file_id] = {
            "status": "completed_disk_only",
            "filename": filename,
            "workspace_id": workspace_id,
            "message": "업로드 완료",
            "warning": INDEXING_FAILED_WARNING,
            "progress": 100,
        }

    # 10분 후 상태 정보 삭제 (메모리 관리)
    await asyncio.sleep(600)
    if file_id in WORKSPACE_UPLOAD_STATUS:
        del WORKSPACE_UPLOAD_STATUS[file_id]


@router.get("/v1/workspaces/upload/status/{file_id}")
async def get_workspace_upload_status(file_id: str):
    """워크스페이스 파일 업로드 상태 확인"""
    status = WORKSPACE_UPLOAD_STATUS.get(file_id)
    if not status:
        return {"status": "unknown", "message": "Status not found (expired or invalid ID)"}
    return status


@router.post("/v1/workspaces/{workspace_uuid}/upload")
async def upload_workspace_file(
    workspace_uuid: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """워크스페이스에 파일 업로드 (비동기 백그라운드 처리, 소유권 검증)"""
    try:
        # 워크스페이스 존재 및 소유권 확인 (업로드는 owner만 — 공용이라도 차단)
        workspace = service.get_workspace_by_uuid(workspace_uuid)
        assert_workspace_owner(workspace, current_user["empno"], allow_public=False)

        workspace_id = workspace["id"]

        # 1. 파일 내용 읽기 (메모리)
        file_content = await file.read()
        file_size = len(file_content)

        # 파일 크기 제한 (50MB)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"파일 크기는 50MB를 초과할 수 없습니다. (현재: {file_size / (1024*1024):.2f}MB)"
            )

        # 2. File ID 미리 생성
        file_id = str(uuid.uuid4())

        # 3. 초기 상태 설정
        WORKSPACE_UPLOAD_STATUS[file_id] = {
            "status": "pending",
            "filename": file.filename,
            "workspace_id": workspace_id,
            "message": "Queued for processing",
            "progress": 0
        }

        # 4. 백그라운드 작업 등록 (싱글톤 ChromaDBService 사용)
        background_tasks.add_task(
            _process_workspace_upload_background,
            file_content,
            file.filename,
            workspace_id,
            file_id,
            service,
        )

        # 5. 즉시 응답 반환
        return {
            "status": "processing",
            "message": "파일 업로드가 시작되었습니다. (백그라운드 처리 중)",
            "file_id": file_id,
            "filename": file.filename,
            "file_size": file_size,
            "workspace_id": workspace_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start upload to workspace {workspace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/v1/workspaces/{workspace_uuid}/files", response_model=List[FileResponse])
async def list_workspace_files(
    workspace_uuid: str,
    current_user: dict = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """워크스페이스의 파일 목록 조회 (소유자 또는 공용 워크스페이스면 허용)"""
    workspace = service.get_workspace_by_uuid(workspace_uuid)
    assert_workspace_owner(workspace, current_user["empno"])
    return service.list_files(workspace["id"])

@router.delete("/v1/workspaces/{workspace_uuid}/files/{file_id}")
async def delete_workspace_file(
    workspace_uuid: str,
    file_id: str,
    current_user: dict = Depends(get_current_user),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """워크스페이스에서 파일 삭제 (소유권 검증, 공용이라도 owner만)"""
    workspace = service.get_workspace_by_uuid(workspace_uuid)
    assert_workspace_owner(workspace, current_user["empno"], allow_public=False)

    success = service.delete_file(workspace["id"], file_id)
    if not success:
        raise HTTPException(status_code=404, detail="File not found")
    return {"status": "success", "message": "File deleted"}


# ============================================================================
# Admin Endpoints (전체 워크스페이스 관리)
# ============================================================================

@router.get("/v1/admin/workspaces")
async def admin_list_all_workspaces(
    _admin: dict = Depends(get_current_admin),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """모든 워크스페이스 조회 (운영자 전용)"""
    workspaces = service.get_all_workspaces()
    return {"workspaces": workspaces}


@router.get("/v1/admin/workspaces/{workspace_id}/files")
async def admin_list_workspace_files(
    workspace_id: int,
    _admin: dict = Depends(get_current_admin),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """워크스페이스의 파일 목록 조회 (운영자 전용)"""
    workspace = service.get_workspace(workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")

    files = service.list_files(workspace_id)
    return {
        "workspace": workspace,
        "files": files
    }


@router.get("/v1/admin/workspaces/{workspace_id}/files/{file_id}/chunks")
async def admin_get_file_chunks(
    workspace_id: int,
    file_id: str,
    limit: int = Query(10, ge=1, le=100, description="청크 개수 제한"),
    offset: int = Query(0, ge=0, description="시작 오프셋"),
    _admin: dict = Depends(get_current_admin),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """파일의 텍스트 청크 조회 (운영자 전용, 미리보기)"""
    return service.get_file_chunks(workspace_id, file_id, limit, offset)


@router.delete("/v1/admin/workspaces/{workspace_id}")
async def admin_delete_workspace(
    workspace_id: int,
    _admin: dict = Depends(get_current_admin),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """워크스페이스 삭제 (운영자 전용)"""
    success = service.delete_workspace(workspace_id)
    if not success:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return {"status": "success", "message": "Workspace deleted"}


@router.delete("/v1/admin/workspaces/{workspace_id}/files/{file_id}")
async def admin_delete_file(
    workspace_id: int,
    file_id: str,
    _admin: dict = Depends(get_current_admin),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """워크스페이스에서 파일 삭제 (운영자 전용)"""
    success = service.delete_file(workspace_id, file_id)
    if not success:
        raise HTTPException(status_code=404, detail="File not found")
    return {"status": "success", "message": "File deleted"}


@router.post("/v1/admin/workspaces/search-chunks")
async def admin_search_chunks(
    request: ChunkSearchRequest,
    _admin: dict = Depends(get_current_admin),
    service: WorkspaceService = Depends(get_workspace_service)
):
    """
    청크 검색 - PII 패턴 기반 (Admin 전용)

    개인정보 모니터링을 위한 패턴 검색:
    - resident_number: 주민등록번호
    - account_number: 계좌번호
    - phone_number: 전화번호
    - credit_card: 신용카드번호
    - email: 이메일 주소
    """
    return service.search_chunks_by_pattern(
        pattern_type=request.pattern_type,
        workspace_id=request.workspace_id,
        limit=request.limit,
        offset=request.offset
    )
