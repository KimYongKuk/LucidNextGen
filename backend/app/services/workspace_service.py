# -*- coding: utf-8 -*-
"""
워크스페이스 서비스

워크스페이스(Workspace)는 사용자가 문서를 업로드하고 관리할 수 있는 독립적인 작업 공간입니다.
각 워크스페이스는 고유한 벡터 스토어 컬렉션을 가지며, 채팅 세션과 연결될 수 있습니다.
"""
import uuid
import re
import logging
from typing import List, Dict, Optional
from datetime import datetime
from fastapi import UploadFile, HTTPException

from app.core.database import get_database_connection
from app.services.chromadb_service import get_chromadb_service, ChromaDBService

logger = logging.getLogger(__name__)

# 사전정의 PII 패턴 (개인정보 모니터링용)
PII_PATTERNS = {
    "resident_number": r"\d{6}[-\s]?\d{7}",  # 주민등록번호
    "account_number": r"\d{3,4}[-\s]?\d{2,6}[-\s]?\d{2,6}",  # 계좌번호
    "phone_number": r"01[016789][-\s]?\d{3,4}[-\s]?\d{4}",  # 전화번호
    "credit_card": r"\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}",  # 신용카드
    "email": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",  # 이메일
}

PII_PATTERN_LABELS = {
    "resident_number": "주민등록번호",
    "account_number": "계좌번호",
    "phone_number": "전화번호",
    "credit_card": "신용카드",
    "email": "이메일",
}

class WorkspaceService:
    def __init__(self):
        self.db = get_database_connection()
        self.chromadb = get_chromadb_service()

    def _get_collection_name(self, workspace_uuid: str) -> str:
        return f"workspace_{workspace_uuid}"

    def create_workspace(self, user_id: str, name: str, description: str = None, instructions: str = None, is_public: bool = False) -> Dict:
        """워크스페이스 생성"""
        workspace_uuid = str(uuid.uuid4())

        with self.db.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO workspaces (uuid, user_id, name, description, instructions, is_public)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (workspace_uuid, user_id, name, description, instructions, 1 if is_public else 0))
            workspace_id = cursor.lastrowid

            # Return created workspace
            cursor.execute("SELECT * FROM workspaces WHERE id = %s", (workspace_id,))
            return cursor.fetchone()

    def get_workspaces(self, user_id: str) -> List[Dict]:
        """사용자의 모든 워크스페이스 목록 조회 (본인 소유만)"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM workspaces
                WHERE user_id = %s
                ORDER BY updated_at DESC
            """, (user_id,))
            return cursor.fetchall()

    def get_public_workspaces(self) -> List[Dict]:
        """공용 워크스페이스 목록 조회 (모든 사용자에게 노출)"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM workspaces
                WHERE is_public = 1
                ORDER BY updated_at DESC
            """)
            return cursor.fetchall()

    def get_all_workspaces(self) -> List[Dict]:
        """모든 워크스페이스 조회 (Admin 전용)"""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM workspaces
                ORDER BY user_id, updated_at DESC
            """)
            return cursor.fetchall()

    def get_workspace(self, workspace_id: int) -> Optional[Dict]:
        """ID로 워크스페이스 조회"""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM workspaces WHERE id = %s", (workspace_id,))
            return cursor.fetchone()
            
    def get_workspace_by_uuid(self, workspace_uuid: str) -> Optional[Dict]:
        """UUID로 워크스페이스 조회"""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM workspaces WHERE uuid = %s", (workspace_uuid,))
            return cursor.fetchone()

    def has_files(self, workspace_id: int) -> bool:
        """워크스페이스에 파일이 있는지 빠르게 확인"""
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return False

        collection_name = self._get_collection_name(workspace['uuid'])
        try:
            collection = self.chromadb.client.get_collection(collection_name)
            return collection.count() > 0
        except Exception:
            return False

    def update_workspace(self, workspace_id: int, name: str = None, description: str = None, instructions: str = None, is_public: Optional[bool] = None) -> bool:
        """워크스페이스 메타데이터 업데이트"""
        fields = []
        params = []

        if name is not None:
            fields.append("name = %s")
            params.append(name)
        if description is not None:
            fields.append("description = %s")
            params.append(description)
        if instructions is not None:
            fields.append("instructions = %s")
            params.append(instructions)
        if is_public is not None:
            fields.append("is_public = %s")
            params.append(1 if is_public else 0)

        if not fields:
            return False
            
        params.append(workspace_id)
        query = f"UPDATE workspaces SET {', '.join(fields)} WHERE id = %s"
        
        with self.db.get_cursor() as cursor:
            cursor.execute(query, params)
            if cursor.rowcount > 0:
                return True
            
            # If rowcount is 0, check if workspace exists (it might be just no changes)
            cursor.execute("SELECT id FROM workspaces WHERE id = %s", (workspace_id,))
            return cursor.fetchone() is not None

    def delete_workspace(self, workspace_id: int) -> bool:
        """워크스페이스 및 벡터 스토어 삭제"""
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            return False
            
        # 1. Delete from DB
        with self.db.get_cursor() as cursor:
            cursor.execute("DELETE FROM workspaces WHERE id = %s", (workspace_id,))
            
        # 2. Delete ChromaDB Collection
        try:
            collection_name = self._get_collection_name(workspace['uuid'])
            self.chromadb.client.delete_collection(collection_name)
        except Exception as e:
            logger.warning(f"Failed to delete ChromaDB collection for workspace {workspace_id}: {e}")
            
        return True

    async def upload_file(self, workspace_id: int, file: UploadFile) -> Dict:
        """워크스페이스의 벡터 스토어에 파일 업로드 (UploadFile 객체 사용)"""
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        collection_name = self._get_collection_name(workspace['uuid'])
        file_content = await file.read()

        # Use ChromaDB service to upload
        result = await self.chromadb.upload_file(
            file_content=file_content,
            filename=file.filename,
            user_id=workspace['user_id'],
            collection=collection_name,
            replace_existing=False  # Append mode
        )

        return result

    async def upload_file_from_content(
        self,
        workspace_id: int,
        file_content: bytes,
        filename: str,
        file_id: str = None
    ) -> Dict:
        """워크스페이스의 벡터 스토어에 파일 업로드 (바이트 콘텐츠 사용, 백그라운드 처리용)"""
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        collection_name = self._get_collection_name(workspace['uuid'])

        # Use ChromaDB service to upload
        result = await self.chromadb.upload_file(
            file_content=file_content,
            filename=filename,
            user_id=workspace['user_id'],
            collection=collection_name,
            replace_existing=False,  # Append mode
            file_id=file_id
        )

        return result

    def list_files(self, workspace_id: int) -> List[Dict]:
        """워크스페이스의 벡터 스토어 파일 목록 조회"""
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")
            
        collection_name = self._get_collection_name(workspace['uuid'])
        
        try:
            collection = self.chromadb.client.get_collection(collection_name)
            if collection.count() == 0:
                return []
                
            records = collection.get(include=["metadatas"])
            
            by_file = {}
            metadatas = records.get("metadatas", [])
            
            for meta in metadatas:
                if not meta: continue
                fid = meta.get("file_id")
                if not fid: continue
                
                if fid not in by_file:
                    by_file[fid] = {
                        "file_id": fid,
                        "filename": meta.get("filename", "unknown"),
                        "uploaded_at": meta.get("uploaded_at"),
                        "chunk_count": 0
                    }
                by_file[fid]["chunk_count"] += 1
                
            return list(by_file.values())
            
        except Exception as e:
            # Collection might not exist yet if no files uploaded
            return []

    def delete_file(self, workspace_id: int, file_id: str) -> bool:
        """워크스페이스의 벡터 스토어에서 파일 삭제"""
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        collection_name = self._get_collection_name(workspace['uuid'])

        try:
            collection = self.chromadb.client.get_collection(collection_name)
            collection.delete(where={"file_id": file_id})
            return True
        except Exception as e:
            logger.error(f"Failed to delete file {file_id} from workspace {workspace_id}: {e}")
            return False

    def get_file_chunks(self, workspace_id: int, file_id: str, limit: int = 10, offset: int = 0) -> Dict:
        """파일의 텍스트 청크 조회 (미리보기용, Admin 전용)"""
        workspace = self.get_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace not found")

        collection_name = self._get_collection_name(workspace['uuid'])

        try:
            collection = self.chromadb.client.get_collection(collection_name)
            records = collection.get(
                where={"file_id": file_id},
                include=["documents", "metadatas"]
            )

            documents = records.get("documents", [])
            metadatas = records.get("metadatas", [])
            total = len(documents)

            # 페이지네이션 적용
            start = offset
            end = min(offset + limit, total)

            chunks = []
            for i in range(start, end):
                chunks.append({
                    "index": i,
                    "text": documents[i] if i < len(documents) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {}
                })

            return {
                "total": total,
                "offset": offset,
                "limit": limit,
                "chunks": chunks
            }

        except Exception as e:
            logger.error(f"Failed to get chunks for file {file_id} in workspace {workspace_id}: {e}")
            return {"total": 0, "offset": offset, "limit": limit, "chunks": []}

    def search_chunks_by_pattern(
        self,
        pattern_type: Optional[str] = None,
        workspace_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict:
        """
        모든 워크스페이스에서 PII 패턴으로 청크 검색 (Admin 전용)

        Args:
            pattern_type: PII 패턴 타입 (resident_number, account_number, phone_number, credit_card, email)
            workspace_id: 특정 워크스페이스만 검색 (None이면 전체)
            limit: 반환할 최대 결과 수
            offset: 페이지네이션 오프셋

        Returns:
            검색 결과 딕셔너리
        """
        if pattern_type and pattern_type not in PII_PATTERNS:
            return {"total": 0, "results": [], "error": f"Unknown pattern type: {pattern_type}"}

        # 검색 대상 워크스페이스 결정
        if workspace_id:
            workspace = self.get_workspace(workspace_id)
            if not workspace:
                return {"total": 0, "results": [], "error": "Workspace not found"}
            workspaces = [workspace]
        else:
            workspaces = self.get_all_workspaces()

        results = []
        pattern = re.compile(PII_PATTERNS[pattern_type]) if pattern_type else None

        for ws in workspaces:
            collection_name = self._get_collection_name(ws['uuid'])

            try:
                collection = self.chromadb.client.get_collection(collection_name)
                if collection.count() == 0:
                    continue

                # 모든 청크 조회
                records = collection.get(include=["documents", "metadatas"])
                documents = records.get("documents", [])
                metadatas = records.get("metadatas", [])
                ids = records.get("ids", [])

                for i, doc in enumerate(documents):
                    if not doc:
                        continue

                    # 패턴 매칭
                    if pattern:
                        matches = pattern.findall(doc)
                        if not matches:
                            continue
                        matched_text = ", ".join(matches[:3])  # 최대 3개 매치만 표시
                    else:
                        matched_text = ""

                    meta = metadatas[i] if i < len(metadatas) else {}
                    chunk_id = ids[i] if i < len(ids) else ""

                    # 청크 인덱스 추출 (ID 형식: {file_id}_{index})
                    chunk_index = 0
                    if "_" in chunk_id:
                        try:
                            chunk_index = int(chunk_id.split("_")[-1])
                        except ValueError:
                            pass

                    results.append({
                        "workspace_id": ws['id'],
                        "workspace_name": ws['name'],
                        "user_id": ws['user_id'],
                        "file_id": meta.get("file_id", ""),
                        "filename": meta.get("filename", "unknown"),
                        "chunk_index": chunk_index,
                        "chunk_text": doc[:500] + ("..." if len(doc) > 500 else ""),  # 500자 제한
                        "matched_text": matched_text,
                    })

            except Exception as e:
                logger.warning(f"Search failed for workspace {ws['id']}: {e}")
                continue

        total = len(results)
        paginated_results = results[offset:offset + limit]

        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "pattern_type": pattern_type,
            "pattern_label": PII_PATTERN_LABELS.get(pattern_type, "") if pattern_type else "",
            "results": paginated_results
        }

# Singleton
_workspace_service = None

def get_workspace_service() -> WorkspaceService:
    global _workspace_service
    if _workspace_service is None:
        _workspace_service = WorkspaceService()
    return _workspace_service
