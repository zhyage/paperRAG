"""
配置中心 - 所有模块的配置来源。
通过环境变量 + .env 文件覆盖默认值。
"""

import os
from pathlib import Path

# ── 项目根 ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DATA_DIR = PROJECT_ROOT / "data"
PAPERS_DIR = DATA_DIR / "papers"        # 原始 PDF/DOCX

# ── 从 .env 文件加载 (必须最先，变量依赖它) ────────────────
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key not in os.environ:
                    os.environ[key] = val

PARSED_DIR = DATA_DIR / "parsed"        # Marker 输出 Markdown
METADATA_DB = DATA_DIR / "metadata.db"  # SQLite
QDRANT_STORAGE = PROJECT_ROOT / "qdrant_storage"

# 确保目录存在
for d in [DATA_DIR, PAPERS_DIR, PARSED_DIR, QDRANT_STORAGE]:
    d.mkdir(parents=True, exist_ok=True)

# ── Qdrant ────────────────────────────────────────────────
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "papers")
VECTOR_SIZE = 1024

# ── BGE-M3 Embedding ─────────────────────────────────────
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cpu")
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
DENSE_DIM = 1024

# ── 分块 ──────────────────────────────────────────────────
CHUNK_MIN_SIZE = int(os.getenv("CHUNK_MIN_SIZE", "256"))
CHUNK_MAX_SIZE = int(os.getenv("CHUNK_MAX_SIZE", "1024"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "128"))

# ── 检索 ──────────────────────────────────────────────────
RETRIEVE_TOP_K = int(os.getenv("RETRIEVE_TOP_K", "10"))
RERANK_TOP_K = int(os.getenv("RERANK_TOP_K", "5"))
RERANK_MODEL = os.getenv("RERANK_MODEL", "BAAI/bge-reranker-base")
ENABLE_RERANK = os.getenv("ENABLE_RERANK", "true").lower() == "true"

# ── LLM (DeepSeek API) ───────────────────────────────────
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", os.getenv("OPENAI_API_KEY", ""))
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))

# ── Marker 解析 ───────────────────────────────────────────
MARKER_SCRIPT = Path(os.getenv(
    "MARKER_SCRIPT",
    str(Path.home() / ".deepseek/skills/tomarkdown/scripts/convert.py")
))
MARKER_FORCE_OCR = os.getenv("MARKER_FORCE_OCR", "false").lower() == "true"
MARKER_USE_LLM = os.getenv("MARKER_USE_LLM", "false").lower() == "true"

# ── 服务 ──────────────────────────────────────────────────
HOST = os.getenv("RAG_HOST", "0.0.0.0")
PORT = int(os.getenv("RAG_PORT", "8765"))
MCP_SSE_PATH = os.getenv("MCP_SSE_PATH", "/mcp/sse")

# ── 论文元数据字段 (SQLite schema) ────────────────────────
PAPER_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    authors     TEXT,
    abstract    TEXT,
    year        INTEGER,
    journal     TEXT,
    doi         TEXT,
    tags        TEXT,
    filename    TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    parsed_path TEXT,
    page_count  INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);
"""
