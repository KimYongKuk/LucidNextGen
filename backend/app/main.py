"""
LFChatbot FastAPI - MVP
"""
import os
import sys

# Windows 환경 설정
if sys.platform == 'win32':
    os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="LFChatbot API",
    version="2.0.0",
    docs_url="/docs"
)

# CORS (frontend는 3001 포트 사용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001", "http://localhost:3000", "http://127.0.0.1:3001", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.routes import chat, upload

# 라우터 등록
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(upload.router, prefix="/api", tags=["upload"])

@app.get("/")
async def root():
    return {"message": "LFChatbot API v2.0", "status": "healthy"}

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
