"""
主入口 — FastAPI 应用启动。

启动方式:
    uv run python -m src.main

或手动:
    cd my/rag && uv run uvicorn src.main:app --host 0.0.0.0 --port 8765
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse

from .config import PROJECT_ROOT, HOST, PORT, MCP_SSE_PATH
from .db.metadata import init_db
from .api.routes import router as api_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("paper-rag")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期."""
    init_db()
    logger.info("Paper RAG starting on %s:%d", HOST, PORT)
    yield
    logger.info("Paper RAG shutting down")


app = FastAPI(
    title="Paper RAG",
    description="RAG system for academic papers",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — 允许任何来源（开发环境）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由
app.include_router(api_router)

# 静态文件 (Web UI)
static_dir = PROJECT_ROOT / "src" / "web" / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    """Web UI 入口."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Paper RAG running", "docs": "/docs"}


def mount_mcp(app: FastAPI):
    """将 MCP SSE 端点挂载到 FastAPI."""
    try:
        from .api.mcp_server import mcp as mcp_instance

        mcp_app = mcp_instance.sse_app()
        app.mount("/mcp", mcp_app)
        logger.info("MCP SSE endpoint mounted at /mcp")
    except Exception as e:
        logger.warning("Failed to mount MCP: %s", e)


# 挂载 MCP
try:
    mount_mcp(app)
except Exception as e:
    logger.warning("MCP mount deferred: %s", e)


# ── 直接运行时启动 uvicorn ────────────────────────────────

def main():
    """Entry point for `paper-rag` CLI command."""
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
    )

if __name__ == "__main__":
    main()
