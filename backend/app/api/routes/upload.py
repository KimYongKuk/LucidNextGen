"""Upload APIs"""
import base64
import asyncio
import logging
import uuid
from pathlib import Path as FilePath
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Query, Path, BackgroundTasks
from fastapi.responses import FileResponse
from app.services.chromadb_service import (
    ChromaDBService,
    get_chromadb_service,
    get_admin_chromadb_service,
)

# PDF 출력 디렉토리
PDF_OUTPUT_DIR = FilePath(__file__).parent.parent.parent.parent / "data" / "pdf_output"
# PPT 출력 디렉토리
PPT_OUTPUT_DIR = FilePath(__file__).parent.parent.parent.parent / "data" / "ppt_output"
# DOCX 출력 디렉토리
DOCX_OUTPUT_DIR = FilePath(__file__).parent.parent.parent.parent / "data" / "docx_output"
# XLSX 디렉토리
XLSX_UPLOAD_DIR = FilePath(__file__).parent.parent.parent.parent / "data" / "xlsx_upload"
XLSX_OUTPUT_DIR = FilePath(__file__).parent.parent.parent.parent / "data" / "xlsx_output"
# 사용자 업로드 디렉토리 (이미지 포함, 날짜/사용자ID별 정리)
USER_UPLOAD_DIR = FilePath(__file__).parent.parent.parent.parent / "data" / "user_uploads"
# 레거시 이미지 디렉토리 (기존 stored_filename 하위 호환용)
IMAGE_OUTPUT_DIR_LEGACY = FilePath(__file__).parent.parent.parent.parent / "data" / "image_output"

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory status tracking (file_id -> dict)
UPLOAD_STATUS = {}


def _detect_file_encryption(file_content: bytes, filename: str) -> tuple[bool, str]:
    """파일 암호화(비밀번호 보호) 여부 감지.
    Returns: (is_encrypted, reason_if_encrypted)
    감지 실패/예외 시 False 반환 (정상 임베딩 경로로 진행).
    """
    import io as _io
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    try:
        if ext == "pdf":
            import PyPDF2
            reader = PyPDF2.PdfReader(_io.BytesIO(file_content))
            if reader.is_encrypted:
                return True, "PDF 암호화 (비밀번호 보호)"
        elif ext in ("docx", "xlsx", "xls", "pptx"):
            # Office 암호화 파일은 OLE2 Compound Document 형식 (D0CF11E0)
            # 일반 OOXML은 ZIP(PK) 형식
            if file_content[:4] == b"\xd0\xcf\x11\xe0":
                return True, "Office 파일 암호화 (OLE2 Compound)"
    except Exception:
        pass

    return False, ""

async def _process_upload_background(
    file_content: bytes,
    filename: str,
    user_id: str,
    session_id: str,
    chromadb: ChromaDBService,
    collection: str | None,
    chunk_size: int | None,
    chunk_overlap: int | None,
    file_id: str,
):
    """백그라운드에서 파일 업로드 처리.

    Status 값:
    - processing: 진행 중
    - completed: 임베딩까지 성공 (RAG 검색 가능)
    - completed_disk_only: 디스크 저장은 됐으나 임베딩 스킵/실패 (첨부는 가능, 검색 불가)
    - failed: 처리 자체 실패 (디스크 저장도 미완)
    """
    UPLOAD_STATUS[file_id] = {
        "status": "processing",
        "filename": filename,
        "message": "Processing started",
        "progress": 0
    }
    logger.info(f"Starting background upload for {filename} (ID: {file_id})")

    # 표준 경고 문구 (사용자 노출용 — 내부 경로/에러 상세는 절대 포함하지 않음)
    ENCRYPTED_WARNING = (
        "암호화된 파일은 IT VOC 등록을 위한 파일 업로드만 가능합니다.\n"
        "암호화된 파일은 분석/요약이 불가하므로, 복호화 후 업로드 하세요."
    )
    INDEXING_FAILED_WARNING = (
        "이 파일은 분석/요약용 인덱싱에 실패했습니다.\n"
        "IT VOC 등록을 위한 첨부는 가능하며, 분석/요약이 필요하시면 복호화 후 업로드 하세요."
    )

    # 1) 사전 암호화 감지 → 임베딩 스킵
    is_encrypted, enc_reason = _detect_file_encryption(file_content, filename)
    if is_encrypted:
        logger.warning(f"Encrypted file detected, skipping embedding: {filename} ({enc_reason})")
        UPLOAD_STATUS[file_id] = {
            "status": "completed_disk_only",
            "filename": filename,
            "message": "업로드 완료",
            "warning": ENCRYPTED_WARNING,
            "progress": 100,
        }
        await asyncio.sleep(600)
        if file_id in UPLOAD_STATUS:
            del UPLOAD_STATUS[file_id]
        return

    # 2) 정상 임베딩 시도
    try:
        await chromadb.upload_file(
            file_content=file_content,
            filename=filename,
            user_id=user_id,
            session_id=session_id,
            collection=collection,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            file_id=file_id
        )
        UPLOAD_STATUS[file_id] = {
            "status": "completed",
            "filename": filename,
            "message": "Upload complete",
            "progress": 100
        }
        logger.info(f"Background upload complete for {filename} (ID: {file_id})")
    except Exception as e:
        # 임베딩 실패여도 디스크엔 이미 저장됨 → soft fail. 내부 에러는 로그에만 남김
        logger.warning(f"Embedding failed (disk-only success) for {filename} (ID: {file_id}): {e}")
        UPLOAD_STATUS[file_id] = {
            "status": "completed_disk_only",
            "filename": filename,
            "message": "업로드 완료",
            "warning": INDEXING_FAILED_WARNING,
            "progress": 100,
        }

    # 10분 후 상태 정보 삭제 (메모리 관리)
    await asyncio.sleep(600)
    if file_id in UPLOAD_STATUS:
        del UPLOAD_STATUS[file_id]

@router.get("/v1/upload/status/{file_id}")
async def get_upload_status(file_id: str):
    """파일 업로드 상태 확인"""
    status = UPLOAD_STATUS.get(file_id)
    if not status:
        # 메모리에 없으면 DB(Chroma)에 있는지 확인해볼 수도 있음
        # 하지만 여기서는 간단히 메모리 상태만 반환하거나 404
        return {"status": "unknown", "message": "Status not found (expired or invalid ID)"}
    return status

# ... (upload_file and admin_upload_file remain mostly same, just ensure they use the updated _process_upload_background)

# 최대 파일 크기 (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/v1/upload/file")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form("anonymous"),
    session_id: str = Form(None),
    collection: str | None = Form(None),
    chunk_size: int | None = Form(None),
    chunk_overlap: int | None = Form(None),
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """사용자 저장소로 업로드/임베딩 (비동기 백그라운드 처리)"""

    # 1. 파일 내용 읽기 (메모리)
    file_content = await file.read()
    file_size = len(file_content)

    # 파일 크기 제한 (50MB)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기는 50MB를 초과할 수 없습니다. (현재: {file_size / (1024*1024):.2f}MB)"
        )

    # 1-1. 업로드 원본 파일을 디스크에 보관 (user_uploads/{date}/{user_id}/)
    try:
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        safe_uid = user_id.replace("/", "").replace("\\", "").replace("..", "").replace(" ", "_")
        upload_dir = USER_UPLOAD_DIR / today / safe_uid
        upload_dir.mkdir(parents=True, exist_ok=True)
        upload_path = upload_dir / file.filename
        with open(upload_path, "wb") as f:
            f.write(file_content)
        logger.info(f"Original file saved: {upload_path}")
    except Exception as e:
        logger.warning(f"Failed to save original file: {e}")

    # 1-2. Excel 파일은 XlsxWorker 작업용으로 별도 경로에도 저장
    if file.filename and file.filename.lower().endswith(('.xlsx', '.xls')):
        try:
            xlsx_dir = XLSX_UPLOAD_DIR / (session_id or "no_session")
            xlsx_dir.mkdir(parents=True, exist_ok=True)
            xlsx_path = xlsx_dir / file.filename
            with open(xlsx_path, "wb") as f:
                f.write(file_content)
            logger.info(f"XLSX original saved: {xlsx_path}")
        except Exception as e:
            logger.warning(f"Failed to save XLSX original: {e}")

    # 2. File ID 미리 생성
    file_id = str(uuid.uuid4())
    
    # 3. 초기 상태 설정
    UPLOAD_STATUS[file_id] = {
        "status": "pending",
        "filename": file.filename,
        "message": "Queued for processing",
        "progress": 0
    }
    
    # 4. 백그라운드 작업 등록
    background_tasks.add_task(
        _process_upload_background,
        file_content,
        file.filename,
        user_id,
        session_id,
        chromadb,
        collection,
        chunk_size,
        chunk_overlap,
        file_id
    )
    
    # 5. 즉시 응답 반환
    return {
        "status": "processing",
        "message": "파일 업로드가 시작되었습니다. (백그라운드 처리 중)",
        "file_id": file_id,
        "filename": file.filename,
        "file_size": file_size,
        "chunk_count": 0,
    }


@router.post("/v1/admin/upload/file")
async def admin_upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form("admin"),
    session_id: str = Form(None),
    collection: str | None = Form(None),
    chunk_size: int | None = Form(None),
    chunk_overlap: int | None = Form(None),
    chromadb: ChromaDBService = Depends(get_admin_chromadb_service)
):
    """관리자 저장소(chromadb_admin)로 업로드/임베딩 (비동기 백그라운드 처리)"""

    # 1. 파일 내용 읽기
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
    UPLOAD_STATUS[file_id] = {
        "status": "pending",
        "filename": file.filename,
        "message": "Queued for processing",
        "progress": 0
    }
    
    # 4. 백그라운드 작업 등록
    background_tasks.add_task(
        _process_upload_background,
        file_content,
        file.filename,
        user_id,
        session_id,
        chromadb,
        collection,
        chunk_size,
        chunk_overlap,
        file_id
    )
    
    # 5. 즉시 응답 반환
    return {
        "status": "processing",
        "message": "파일 업로드가 시작되었습니다. (백그라운드 처리 중)",
        "file_id": file_id,
        "filename": file.filename,
        "file_size": file_size,
        "chunk_count": 0,
    }

@router.post("/v1/upload/image")
async def upload_image(
    file: UploadFile = File(...),
    user_id: str = Form("anonymous"),
    session_id: str = Form(None),
):
    """이미지 업로드 - base64로 인코딩하여 즉시 반환"""
    try:
        # 이미지 파일 검증
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(
                status_code=400,
                detail=f"이미지 파일만 업로드 가능합니다. (현재: {file.content_type})"
            )
        
        # 파일 크기 제한 (50MB)
        file_content = await file.read()
        if len(file_content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail="이미지 크기는 50MB를 초과할 수 없습니다."
            )
        
        # Base64 인코딩
        base64_data = base64.b64encode(file_content).decode("utf-8")

        # 디스크에 저장 (채팅 히스토리 복원용, user_uploads/{date}/{user_id}/)
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        ext = FilePath(file.filename).suffix if file.filename else ".png"
        safe_user_id = user_id.replace("/", "").replace("\\", "").replace("..", "").replace(" ", "_")
        unique_name = f"{uuid.uuid4()}{ext}"

        image_dir = USER_UPLOAD_DIR / today / safe_user_id
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / unique_name
        image_path.write_bytes(file_content)

        # stored_filename에 상대 경로 포함 (날짜/사용자ID/파일명)
        stored_filename = f"{today}/{safe_user_id}/{unique_name}"

        logger.info(f"Image uploaded by {user_id}: {file.filename} ({file.content_type}, {len(file_content)} bytes) -> {stored_filename}")

        return {
            "media_type": file.content_type,
            "base64_data": base64_data,
            "filename": file.filename,
            "stored_filename": stored_filename,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"이미지 업로드 실패: {str(e)}")


@router.get("/v1/upload/list")
async def list_uploaded_files(
    user_id: str = Query("anonymous"),
    session_id: str | None = Query(None),
    collection: str | None = Query(None),
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """List uploaded files grouped by file_id for user/session storage."""
    try:
        collection_obj = chromadb.get_collection(user_id=user_id, session_id=session_id, collection=collection)
        
        # 1. ChromaDB에서 완료된 파일 조회
        total = collection_obj.count()
        files = []
        
        if total > 0:
            records = collection_obj.get(include=["metadatas"], limit=total)
            by_file: dict[str, dict] = {}
            raw_meta = records.get("metadatas") or []
            meta_rows = raw_meta[0] if raw_meta and isinstance(raw_meta[0], list) else raw_meta
            for meta in meta_rows:
                if not isinstance(meta, dict): continue
                fid = meta.get("file_id")
                fname = meta.get("filename", "unknown")
                if not fid: continue
                if fid not in by_file:
                    by_file[fid] = {
                        "file_id": fid,
                        "filename": fname,
                        "collection": collection_obj.name,
                        "chunk_count": 0,
                        "status": "ready",
                        "updated_at": None,
                    }
                by_file[fid]["chunk_count"] += 1
            files = list(by_file.values())

        # 2. 처리 중인 파일 병합 (메모리 상태 확인)
        # 현재 세션/유저와 관련된 파일만 필터링하는 로직이 필요하지만, 
        # 간단히 모든 processing 상태 파일을 추가하거나, 
        # UPLOAD_STATUS에 user_id/session_id를 저장해서 필터링해야 함.
        # 여기서는 간단히 모든 processing 파일을 추가 (데모용)
        # 실제로는 UPLOAD_STATUS에 메타데이터 추가 필요
        
        for fid, status in UPLOAD_STATUS.items():
            if status["status"] in ["pending", "processing"]:
                # 중복 확인 (이미 완료되어 DB에 있을 수도 있음)
                if not any(f["file_id"] == fid for f in files):
                    files.append({
                        "file_id": fid,
                        "filename": status["filename"],
                        "collection": collection_obj.name,
                        "chunk_count": 0,
                        "status": status["status"], # processing or pending
                        "updated_at": None,
                        "message": status["message"]
                    })

        return {"status": "success", "user_id": user_id, "session_id": session_id, "collection": collection_obj.name, "files": files, "total_files": len(files)}
    except Exception as e:
        # If collection does not exist, return empty (but check processing)
        files = []
        for fid, status in UPLOAD_STATUS.items():
            if status["status"] in ["pending", "processing"]:
                 files.append({
                    "file_id": fid,
                    "filename": status["filename"],
                    "collection": collection or "unknown",
                    "chunk_count": 0,
                    "status": status["status"],
                    "updated_at": None,
                    "message": status["message"]
                })
        
        return {
            "status": "success",
            "user_id": user_id,
            "session_id": session_id,
            "collection": collection,
            "files": files,
            "total_files": len(files),
            "message": f"empty_or_error: {e}",
        }


@router.get("/v1/admin/upload/list")
async def admin_list_uploaded_files(
    user_id: str = Query("admin"),
    session_id: str | None = Query(None),
    collection: str | None = Query(None),
    chromadb: ChromaDBService = Depends(get_admin_chromadb_service)
):
    """관리자 저장소 리스트"""

    try:
        collection_obj = chromadb.get_collection(user_id=user_id, session_id=session_id, collection=collection)
        total = collection_obj.count()
        if total == 0:
            return {"status": "success", "user_id": user_id, "files": [], "total_files": 0, "total_chunks": 0}

        records = collection_obj.get(include=["metadatas"], limit=total)
        by_file: dict[str, dict] = {}
        raw_meta = records.get("metadatas") or []
        meta_rows = raw_meta[0] if raw_meta and isinstance(raw_meta[0], list) else raw_meta
        for meta in meta_rows:
            if not isinstance(meta, dict):
                continue
            fid = meta.get("file_id")
            fname = meta.get("filename", "unknown")
            uploaded_at = meta.get("uploaded_at")  # 메타데이터에서 업로드 시간 추출
            if not fid:
                continue
            if fid not in by_file:
                by_file[fid] = {
                    "file_id": fid,
                    "filename": fname,
                    "collection": collection_obj.name,
                    "chunk_count": 0,
                    "status": "ready",
                    "updated_at": uploaded_at,  # 실제 업로드 시간 사용
                }
            by_file[fid]["chunk_count"] += 1

        files = list(by_file.values())
        return {
            "status": "success",
            "user_id": user_id,
            "session_id": session_id,
            "collection": collection_obj.name,
            "files": files,
            "total_files": len(files),
            "total_chunks": total,  # 컬렉션 전체 청크 수 추가
        }
    except Exception as e:
        return {
            "status": "success",
            "user_id": user_id,
            "session_id": session_id,
            "collection": collection,
            "files": [],
            "total_files": 0,
            "total_chunks": 0,
            "message": f"empty_or_error: {e}",
        }


@router.post("/v1/admin/upload/collection")
async def admin_create_collection(
    collection_name: str = Form(...),
    chromadb: ChromaDBService = Depends(get_admin_chromadb_service),
):
    """빈 컬렉션을 명시적으로 생성합니다."""
    try:
        # 유효성 검증
        if not collection_name or not collection_name.strip():
            raise HTTPException(status_code=400, detail="컬렉션 이름이 비어있습니다.")

        if len(collection_name) > 50:
            raise HTTPException(status_code=400, detail="컬렉션 이름은 50자를 초과할 수 없습니다.")

        import re
        if not re.match(r'^[a-zA-Z0-9_-]+$', collection_name):
            raise HTTPException(
                status_code=400,
                detail="컬렉션 이름은 영문, 숫자, 하이픈(-), 언더스코어(_)만 사용할 수 있습니다."
            )

        # 중복 확인
        existing = chromadb.client.list_collections()
        existing_names = [getattr(c, "name", getattr(c, "_name", None)) for c in existing]
        existing_names = [n for n in existing_names if n]

        if collection_name in existing_names:
            raise HTTPException(status_code=409, detail=f"컬렉션 '{collection_name}'이 이미 존재합니다.")

        # 빈 컬렉션 생성 (스레드 풀)
        from app.services.chromadb_service import _executor
        await asyncio.get_event_loop().run_in_executor(
            _executor,
            chromadb.get_collection,
            "admin",
            None,
            collection_name
        )

        return {
            "status": "success",
            "collection": collection_name,
            "message": f"컬렉션 '{collection_name}'이 생성되었습니다."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create collection: {e}")
        raise HTTPException(status_code=500, detail=f"컬렉션 생성 실패: {str(e)}")


@router.get("/v1/admin/upload/collections")
async def admin_list_collections(
    chromadb: ChromaDBService = Depends(get_admin_chromadb_service),
):
    """관리자 데이터베이스에 생성된 컬렉션 목록과 각 컬렉션의 문서 수를 반환합니다."""
    try:
        collections = chromadb.client.list_collections()
        collection_info = []
        names = []

        for c in collections:
            # 컬렉션 객체에서 name 속성 안전하게 추출
            name = None
            if hasattr(c, "name"):
                name = c.name
            elif hasattr(c, "_name"):
                name = c._name

            if name:
                names.append(name)
                # 각 컬렉션의 문서 수 조회
                try:
                    collection_obj = chromadb.client.get_collection(
                        name,
                        embedding_function=chromadb.embedding_function
                    )
                    count = collection_obj.count()
                except Exception:
                    count = 0

                collection_info.append({
                    "name": name,
                    "count": count
                })

        return {
            "status": "success",
            "collections": names,  # 기존 호환성 유지
            "collection_info": collection_info,  # 추가 정보 (이름 + 문서 수)
            "total": len(names),
        }
    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        return {
            "status": "error",
            "collections": [],
            "collection_info": [],
            "message": str(e),
        }


@router.delete("/v1/admin/upload/collection/{collection_name}")
async def admin_delete_collection(
    collection_name: str,
    chromadb: ChromaDBService = Depends(get_admin_chromadb_service),
):
    """특정 컬렉션을 삭제합니다."""
    try:
        # ChromaDB 삭제 작업을 스레드 풀에서 실행 (다른 요청 차단 방지)
        from app.services.chromadb_service import _executor
        await asyncio.get_event_loop().run_in_executor(
            _executor,
            chromadb.client.delete_collection,
            collection_name
        )
        return {"status": "success", "collection": collection_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete collection: {e}")


@router.delete("/v1/admin/upload/file/{collection}/{file_id}")
async def admin_delete_file(
    collection: str = Path(..., description="컬렉션 이름"),
    file_id: str = Path(..., description="삭제할 file_id"),
    chromadb: ChromaDBService = Depends(get_admin_chromadb_service),
):
    """컬렉션 내 특정 file_id에 해당하는 모든 청크를 삭제합니다."""
    try:
        collection_obj = chromadb.get_collection(user_id="admin", session_id=None, collection=collection)
        result = collection_obj.delete(where={"file_id": file_id}) or []
        removed = len(result) if hasattr(result, "__len__") else None
        return {
            "status": "success",
            "collection": collection,
            "file_id": file_id,
            "removed": removed,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")


@router.delete("/v1/upload/session/{session_id}")
async def delete_session_files(
    session_id: str,
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """Delete files uploaded for a session"""

    try:
        result = await chromadb.delete_session_files(session_id)

        if result.get("success"):
            return {
                "status": "success",
                "message": f"Session {session_id} files deleted successfully",
                "session_id": session_id
            }
        else:
            return {
                "status": "error",
                "message": result.get("error", "Unknown error"),
                "session_id": session_id
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete session files: {e}")


@router.post("/v1/upload/session/{session_id}/cleanup")
async def cleanup_session_files_beacon(
    session_id: str,
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """
    POST endpoint for navigator.sendBeacon (브라우저 언로드 시 사용)

    sendBeacon은 POST만 지원하므로 DELETE 대신 이 엔드포인트 사용.
    브라우저 탭 닫기, 새로고침, 세션 전환 시 자동 정리용.
    """
    try:
        result = await chromadb.delete_session_files(session_id)
        logger.info(f"Session cleanup via beacon: {session_id}, success={result.get('success')}")
        return {"status": "success" if result.get("success") else "error"}
    except Exception as e:
        logger.warning(f"Cleanup failed for session {session_id}: {e}")
        return {"status": "error"}


@router.delete("/v1/admin/upload/session/{session_id}")
async def admin_delete_session_files(
    session_id: str,
    chromadb: ChromaDBService = Depends(get_admin_chromadb_service)
):
    """관리자 저장소에서 세션 파일 삭제"""

    try:
        result = await chromadb.delete_session_files(session_id)

        if result.get("success"):
            return {
                "status": "success",
                "message": f"Session {session_id} files deleted successfully",
                "session_id": session_id
            }
        else:
            return {
                "status": "error",
                "message": result.get("error", "Unknown error"),
                "session_id": session_id
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete session files: {e}")


# ============================================================
# PDF Download APIs
# ============================================================

@router.get("/v1/pdf/list")
async def list_generated_pdfs():
    """생성된 PDF 파일 목록 조회"""
    try:
        if not PDF_OUTPUT_DIR.exists():
            return {"status": "success", "files": [], "total": 0}

        files = []
        for pdf_file in PDF_OUTPUT_DIR.glob("*.pdf"):
            stat = pdf_file.stat()
            files.append({
                "filename": pdf_file.name,
                "size": stat.st_size,
                "created_at": stat.st_mtime,  # 수정 시간 사용
                "download_url": f"/api/v1/pdf/download/{pdf_file.name}"
            })

        # 최신순 정렬
        files.sort(key=lambda x: x["created_at"], reverse=True)

        return {"status": "success", "files": files, "total": len(files)}
    except Exception as e:
        logger.error(f"Failed to list PDFs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/image/download/{filename:path}")
async def download_image(filename: str):
    """이미지 파일 다운로드 (채팅 히스토리 복원용)

    stored_filename 형식:
    - 신규: {date}/{user_id}/{uuid}.ext (user_uploads/ 하위)
    - 레거시: {user_id}_{uuid}.ext (image_output/ 하위)
    """
    from urllib.parse import unquote
    import mimetypes

    try:
        decoded_filename = unquote(filename)
        if ".." in decoded_filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        file_path = None

        # 1) 신규 형식: user_uploads/{date}/{user_id}/{filename}
        if "/" in decoded_filename:
            candidate = USER_UPLOAD_DIR / decoded_filename
            resolved = candidate.resolve()
            # path traversal 방어
            if str(resolved).startswith(str(USER_UPLOAD_DIR.resolve())):
                if resolved.exists():
                    file_path = resolved

        # 2) 레거시 형식: image_output/{flat_filename}
        if file_path is None:
            safe_filename = decoded_filename.replace("/", "").replace("\\", "")
            candidate = IMAGE_OUTPUT_DIR_LEGACY / safe_filename
            if candidate.exists():
                file_path = candidate

        if file_path is None:
            raise HTTPException(status_code=404, detail=f"Image not found: {decoded_filename}")

        media_type, _ = mimetypes.guess_type(str(file_path))
        if not media_type or not media_type.startswith("image/"):
            media_type = "application/octet-stream"

        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download image: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/pdf/download/{filename:path}")
async def download_pdf(filename: str, inline: bool = False):
    """PDF 파일 다운로드 (inline=true 시 브라우저에서 미리보기)"""
    from urllib.parse import quote, unquote

    try:
        # URL 디코딩 (한글 파일명 처리)
        decoded_filename = unquote(filename)

        # 보안: 경로 탐색 방지
        if ".." in decoded_filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        # 파일명만 추출 (경로 제거)
        safe_filename = decoded_filename.replace("/", "").replace("\\", "")

        file_path = PDF_OUTPUT_DIR / safe_filename

        if not file_path.exists():
            logger.error(f"PDF not found: {file_path}")
            raise HTTPException(status_code=404, detail=f"PDF not found: {safe_filename}")

        # 한글 파일명 인코딩
        encoded_filename = quote(safe_filename)

        # inline: 브라우저 내장 PDF 뷰어로 표시, attachment: 다운로드
        disposition = "inline" if inline else "attachment"

        return FileResponse(
            path=str(file_path),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"{disposition}; filename*=UTF-8''{encoded_filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download PDF: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/ppt/download/{filename:path}")
async def download_ppt(filename: str):
    """PPT 파일 다운로드"""
    from urllib.parse import quote, unquote

    try:
        decoded_filename = unquote(filename)

        if ".." in decoded_filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        safe_filename = decoded_filename.replace("/", "").replace("\\", "")

        file_path = PPT_OUTPUT_DIR / safe_filename

        if not file_path.exists():
            logger.error(f"PPT not found: {file_path}")
            raise HTTPException(status_code=404, detail=f"PPT not found: {safe_filename}")

        encoded_filename = quote(safe_filename)

        return FileResponse(
            path=str(file_path),
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download PPT: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/docx/download/{filename:path}")
async def download_docx(filename: str):
    """DOCX(Word) 파일 다운로드"""
    from urllib.parse import quote, unquote

    try:
        decoded_filename = unquote(filename)

        if ".." in decoded_filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        safe_filename = decoded_filename.replace("/", "").replace("\\", "")

        file_path = DOCX_OUTPUT_DIR / safe_filename

        if not file_path.exists():
            logger.error(f"DOCX not found: {file_path}")
            raise HTTPException(status_code=404, detail=f"DOCX not found: {safe_filename}")

        encoded_filename = quote(safe_filename)

        return FileResponse(
            path=str(file_path),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download DOCX: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/xlsx/download/{filename:path}")
async def download_xlsx(filename: str):
    """XLSX 파일 다운로드"""
    from urllib.parse import quote, unquote

    try:
        decoded_filename = unquote(filename)

        if ".." in decoded_filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        safe_filename = decoded_filename.replace("/", "").replace("\\", "")

        file_path = XLSX_OUTPUT_DIR / safe_filename

        # Fallback: xlsx_output에 없으면 xlsx_upload 하위 디렉토리 검색
        if not file_path.exists():
            found = False
            if XLSX_UPLOAD_DIR.exists():
                for session_dir in XLSX_UPLOAD_DIR.iterdir():
                    if session_dir.is_dir():
                        candidate = session_dir / safe_filename
                        if candidate.exists():
                            file_path = candidate
                            found = True
                            break
            if not found:
                logger.error(f"XLSX not found: {safe_filename}")
                raise HTTPException(status_code=404, detail=f"XLSX not found: {safe_filename}")

        encoded_filename = quote(safe_filename)

        return FileResponse(
            path=str(file_path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download XLSX: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
