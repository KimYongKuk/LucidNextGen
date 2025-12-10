"""파일 업로드 API"""
import base64
from fastapi import APIRouter, UploadFile, File, Form, Depends
from app.services.chromadb_service import ChromaDBService, get_chromadb_service

router = APIRouter()


@router.post("/v1/upload/file")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form("anonymous"),
    session_id: str = Form(None),
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """파일 업로드 및 ChromaDB 저장 (세션별 또는 user별)"""

    try:
        # 파일 읽기
        file_content = await file.read()

        # ChromaDB에 저장 (텍스트 추출 + 임베딩)
        result = await chromadb.upload_file(
            file_content=file_content,
            filename=file.filename,
            user_id=user_id,
            session_id=session_id
        )

        return {
            "status": "success",
            "message": "File uploaded successfully",
            "filename": result["filename"],
            "file_size": len(file_content),
            "processing_result": {
                "status": "success",
                "message": "Document processed and embedded",
                "document_count": 1,
                "chunk_count": result.get("chunks", 0),
                "filename": result["filename"],
                "file_id": result.get("file_id", "")
            }
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"File upload failed: {str(e)}",
            "filename": file.filename,
            "file_size": 0
        }


@router.post("/v1/upload/image")
async def upload_image(
    file: UploadFile = File(...),
    user_id: str = Form("anonymous")
):
    """이미지 업로드 (base64 인코딩 반환)"""

    try:
        # 파일 읽기
        file_content = await file.read()

        # base64 인코딩
        base64_data = base64.b64encode(file_content).decode('utf-8')

        # media_type 확인
        media_type = file.content_type or "image/jpeg"

        return {
            "status": "success",
            "message": "Image uploaded successfully",
            "filename": file.filename,
            "file_size": len(file_content),
            "media_type": media_type,
            "base64_data": base64_data,
            "user_id": user_id
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Image upload failed: {str(e)}",
            "filename": file.filename,
            "file_size": 0,
            "media_type": "",
            "base64_data": "",
            "user_id": user_id
        }


@router.get("/v1/upload/list")
async def list_uploaded_files(
    user_id: str = "anonymous",
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """업로드된 파일 목록 조회 (현재는 간단한 응답만)"""

    return {
        "status": "success",
        "user_id": user_id,
        "files": [],
        "total_files": 0
    }


@router.delete("/v1/upload/session/{session_id}")
async def delete_session_files(
    session_id: str,
    chromadb: ChromaDBService = Depends(get_chromadb_service)
):
    """세션의 업로드된 파일 전체 삭제"""

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
        return {
            "status": "error",
            "message": f"Failed to delete session files: {str(e)}",
            "session_id": session_id
        }
