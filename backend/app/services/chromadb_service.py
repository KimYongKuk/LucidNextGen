"""ChromaDB 파일 업로드 & 검색"""
import os
import uuid
from typing import List, Dict, Optional
import chromadb
from chromadb.config import Settings
from langchain_text_splitters import RecursiveCharacterTextSplitter
import PyPDF2
from docx import Document
import openpyxl
from pptx import Presentation
from app.services.pdf_vision_service import get_pdf_vision_service


class ChromaDBService:
    def __init__(self):
        data_path = os.path.abspath("./data/chromadb")
        os.makedirs(data_path, exist_ok=True)

        self.client = chromadb.PersistentClient(
            path=data_path,
            settings=Settings(allow_reset=True)
        )

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )

    def get_collection(self, user_id: str, session_id: Optional[str] = None):
        """컬렉션 가져오기 (세션별 또는 user별)"""
        if session_id:
            # 세션별 컬렉션 (임시 파일용)
            return self.client.get_or_create_collection(f"session_{session_id}")
        else:
            # user 컬렉션 (영구 파일용 - corp 모드용)
            return self.client.get_or_create_collection(f"user_{user_id}")

    async def extract_text(self, file_path: str, filename: str) -> str:
        """파일에서 텍스트 추출 (PDF는 하이브리드 처리)"""
        ext = filename.lower().split('.')[-1]

        if ext == 'pdf':
            # 하이브리드 PDF 처리 (텍스트 + 이미지)
            pdf_vision = get_pdf_vision_service()
            page_results = await pdf_vision.process_pdf(file_path)
            return pdf_vision.combine_page_contents(page_results)

        elif ext in ['docx', 'doc']:
            doc = Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs)

        elif ext in ['xlsx', 'xls']:
            wb = openpyxl.load_workbook(file_path)
            text = ""
            for sheet in wb.worksheets:
                for row in sheet.iter_rows(values_only=True):
                    text += " | ".join(str(cell) for cell in row if cell) + "\n"
            return text

        elif ext in ['pptx', 'ppt']:
            prs = Presentation(file_path)
            text = ""
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text += shape.text + "\n"
            return text

        elif ext == 'txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()

        raise ValueError(f"지원하지 않는 파일 형식: {ext}")

    async def upload_file(
        self,
        file_content: bytes,
        filename: str,
        user_id: str,
        session_id: Optional[str] = None,
        replace_existing: bool = True
    ) -> Dict:
        """
        파일 업로드 및 벡터화 (세션별 또는 user별)

        Args:
            file_content: 파일 내용
            filename: 파일명
            user_id: 사용자 ID
            session_id: 세션 ID (임시 파일용)
            replace_existing: True면 기존 파일 삭제 후 업로드 (기본값)
        """

        # 세션별 업로드인 경우, 기존 파일 삭제 옵션 확인
        if session_id and replace_existing:
            # 기존 세션 컬렉션 삭제 (새 파일로 교체)
            try:
                self.client.delete_collection(f"session_{session_id}")
            except Exception:
                # 컬렉션이 없으면 무시
                pass

        # 임시 파일 저장
        temp_path = f"./temp_{uuid.uuid4()}_{filename}"
        with open(temp_path, 'wb') as f:
            f.write(file_content)

        try:
            # 텍스트 추출 (async)
            text = await self.extract_text(temp_path, filename)

            # 청킹
            chunks = self.splitter.split_text(text)

            # ChromaDB에 저장 (세션별 또는 user별)
            collection = self.get_collection(user_id, session_id)
            file_id = str(uuid.uuid4())

            ids = [f"{file_id}_{i}" for i in range(len(chunks))]
            metadatas = [{"filename": filename, "file_id": file_id} for _ in chunks]

            collection.add(
                ids=ids,
                documents=chunks,
                metadatas=metadatas
            )

            return {
                "success": True,
                "file_id": file_id,
                "filename": filename,
                "chunks": len(chunks)
            }

        finally:
            # 임시 파일 삭제
            if os.path.exists(temp_path):
                os.remove(temp_path)

    async def search(
        self,
        query: str,
        user_id: str,
        session_id: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict]:
        """파일 검색 (세션별 또는 user별)"""
        collection = self.get_collection(user_id, session_id)

        if collection.count() == 0:
            return []

        results = collection.query(
            query_texts=[query],
            n_results=limit
        )

        docs = []
        if results['documents'] and results['documents'][0]:
            for i, doc in enumerate(results['documents'][0]):
                docs.append({
                    "text": doc,
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {}
                })

        return docs

    async def delete_session_files(self, session_id: str) -> Dict:
        """세션 파일 전체 삭제"""
        try:
            self.client.delete_collection(f"session_{session_id}")
            return {
                "success": True,
                "message": f"Session {session_id} files deleted"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }


# 싱글톤
_chromadb_service = None

def get_chromadb_service() -> ChromaDBService:
    global _chromadb_service
    if _chromadb_service is None:
        _chromadb_service = ChromaDBService()
    return _chromadb_service
