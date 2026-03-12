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
import logging.handlers

from app.adapters.mcp_adapter import MCPAdapter
from app.utils.file_cleanup import file_cleanup_scheduler
from app.utils.chromadb_cleanup import session_cleanup_scheduler
from app.utils.report_email_scheduler import report_email_scheduler
from app.utils.nightly_summary_scheduler import nightly_summary_scheduler

load_dotenv()

# ── 로깅 설정: 콘솔 + 파일 동시 출력 ──
_log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
os.makedirs(_log_dir, exist_ok=True)
_log_file = os.path.join(_log_dir, "server.log")

_log_fmt = logging.Formatter(
    "[%(asctime)s] %(levelname)-7s %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# 파일 핸들러: 10MB 로테이션, 최대 5개 백업
_file_handler = logging.handlers.RotatingFileHandler(
    _log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_file_handler.setFormatter(_log_fmt)

# 루트 로거에 파일 핸들러 추가
logging.root.setLevel(logging.INFO)
logging.root.addHandler(_file_handler)

# print() 출력도 로그 파일로 복제 (콘솔 출력은 그대로 유지)
class _TeeWriter:
    """stdout/stderr를 가로채서 로그 파일에도 기록"""
    def __init__(self, original, log_func):
        self._original = original
        self._log_func = log_func
    def write(self, text):
        if text and text.strip():
            self._log_func(text.rstrip())
        self._original.write(text)
    def flush(self):
        self._original.flush()
    # subprocess/uvicorn이 fileno()를 호출할 수 있으므로 위임
    def fileno(self):
        return self._original.fileno()
    def isatty(self):
        return self._original.isatty()

_print_logger = logging.getLogger("print")
sys.stdout = _TeeWriter(sys.stdout, _print_logger.info)
sys.stderr = _TeeWriter(sys.stderr, _print_logger.warning)

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
    print("[STARTUP] File Cleanup Scheduler starting...")
    file_cleanup_scheduler.start()

    # ChromaDB 세션 컬렉션 자동 정리 스케줄러 시작
    print("[STARTUP] Session Collection Cleanup Scheduler starting...")
    session_cleanup_scheduler.start()

    # 주간 리포트 이메일 스케줄러 시작
    print("[STARTUP] Weekly Report Email Scheduler starting...")
    report_email_scheduler.start()

    # 일일 개발 요약 스케줄러 시작
    print("[STARTUP] Nightly Summary Scheduler starting...")
    nightly_summary_scheduler.start()

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
            file_cleanup_scheduler.stop()
            session_cleanup_scheduler.stop()
            report_email_scheduler.stop()
            nightly_summary_scheduler.stop()
            await close_mcp_adapter()
            # Notification service pool cleanup
            from app.services.notice_service import _notification_service
            if _notification_service:
                await _notification_service.close()
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

from app.api.routes import chat, upload, auth, workspace, chat_a2a, feedback, report, board

# 라우터 등록
app.include_router(auth.router, prefix="/api", tags=["auth"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(chat_a2a.router, prefix="/api", tags=["A2A Chat"])  # 계층적 에이전트
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(workspace.router, prefix="/api", tags=["workspaces"])
app.include_router(feedback.router, prefix="/api", tags=["feedback"])
app.include_router(report.router, prefix="/api", tags=["report"])
app.include_router(board.router, prefix="/api", tags=["notifications"])

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
