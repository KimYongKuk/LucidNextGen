"""
Start FastAPI with multiple workers (Windows-compatible)
"""
import multiprocessing

if __name__ == "__main__":
    # Required for Windows multiprocessing
    multiprocessing.freeze_support()

    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        workers=1,  # ChromaDB PersistentClient: single-process only
        log_level="info",
        access_log=True
    )
