"""
LFChatbot FastAPI - MVP
"""
import os
import sys
from contextlib import asynccontextmanager
import asyncio

# Windows 환경 설정
if sys.platform == 'win32':
    os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import logging

from app.adapters.mcp_adapter import MCPAdapter
from app.utils.pdf_cleanup import pdf_cleanup_scheduler
from app.utils.chromadb_cleanup import session_cleanup_scheduler

load_dotenv()

# Global MCP Adapter instance
_mcp_adapter: MCPAdapter = None


async def get_mcp_adapter() -> MCPAdapter:
    """Get or initialize the global MCP adapter instance."""
    global _mcp_adapter
    if _mcp_adapter is None:
        import time
        start = time.time()
        print("\n" + "="*70)
        print("[MCP] WARNING: MCP Adapter not initialized yet!")
        print("[MCP] Starting initialization... (This is a bottleneck if happens per request!)")
        print("="*70)

        config_path = os.path.join(os.path.dirname(__file__), "../mcp_config.json")
        _mcp_adapter = await MCPAdapter(config_path).open()

        elapsed = int((time.time() - start) * 1000)
        print("="*70)
        print(f"[MCP] Adapter initialized: {elapsed}ms")
        print(f"[MCP] Config path: {config_path}")
        print("="*70 + "\n")
    else:
        print("[MCP] Reusing cached Adapter")
    return _mcp_adapter


async def close_mcp_adapter():
    """Close the global MCP adapter instance."""
    global _mcp_adapter
    if _mcp_adapter:
        await _mcp_adapter.close()
        _mcp_adapter = None
        print("[MCP] Adapter closed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 MCP Adapter 초기화
    import time
    startup_start = time.time()
    print("\n" + "="*70)
    print("[STARTUP] FastAPI Server Starting...")
    print("="*70)

    print("[STARTUP] MCP Adapter initialization starting...")
    await get_mcp_adapter()

    # PDF 자동 정리 스케줄러 시작
    print("[STARTUP] PDF Cleanup Scheduler starting...")
    pdf_cleanup_scheduler.start()

    # ChromaDB 세션 컬렉션 자동 정리 스케줄러 시작
    print("[STARTUP] Session Collection Cleanup Scheduler starting...")
    session_cleanup_scheduler.start()

    startup_time = int((time.time() - startup_start) * 1000)
    print("="*70)
    print(f"[STARTUP] Server Ready! (Total time: {startup_time}ms)")
    print("="*70 + "\n")

    try:
        yield
    except asyncio.CancelledError:
        # uvicorn --reload 시 정상적인 종료 시그널
        pass
    finally:
        try:
            print("\n[SHUTDOWN] Server shutting down...")
            pdf_cleanup_scheduler.stop()
            session_cleanup_scheduler.stop()
            await close_mcp_adapter()
            print("[SHUTDOWN] Complete\n")
        except asyncio.CancelledError:
            # reload 시 발생하는 CancelledError 무시
            print("[SHUTDOWN] Reload detected, graceful shutdown skipped")


app = FastAPI(
    title="LFChatbot API",
    version="2.0.0",
    docs_url="/docs",
    lifespan=lifespan,
)

# CORS (외부 접속 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 origin 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Validation Error Handler (422 에러 상세 로깅)
logger = logging.getLogger(__name__)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    """
    Pydantic validation 에러 발생 시 상세 정보를 로그로 출력
    """
    logger.error("="*70)
    logger.error("[VALIDATION ERROR] Request validation failed!")
    logger.error(f"URL: {request.url}")
    logger.error(f"Method: {request.method}")
    logger.error(f"Errors: {exc.errors()}")
    
    # Request body 출력 시도
    try:
        body = await request.body()
        logger.error(f"Request Body: {body.decode('utf-8')[:1000]}")  # 처음 1000자만
    except Exception as e:
        logger.error(f"Could not read request body: {e}")
    
    logger.error("="*70)
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "body": exc.body if hasattr(exc, 'body') else None
        }
    )

from app.api.routes import chat, upload, auth, workspace, chat_a2a, feedback

# 라우터 등록
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(chat_a2a.router, prefix="/api", tags=["A2A Chat"])  # 계층적 에이전트
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(workspace.router, prefix="/api", tags=["workspaces"])
app.include_router(feedback.router, prefix="/api", tags=["feedback"])

@app.get("/")
async def root():
    print("="*60)
    print("[MAIN.PY] ROOT ENDPOINT CALLED - CODE IS UPDATED!")
    print("="*60)
    return {"message": "LFChatbot API v2.0", "status": "healthy"}

@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
