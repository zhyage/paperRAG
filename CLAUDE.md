# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## rules
* answer questions by chinese

## Commands

```bash
# One-click startup (Qdrant + server)
./start.sh

# Install
uv sync

# Run dev server (Qdrant must already be running)
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8765

# Run CLI entry point
uv run python -m src.main

# Initialize SQLite database
uv run python -c "from src.db.metadata import init_db; init_db(); print('OK')"
```

Web UI at http://localhost:8765, API docs at http://localhost:8765/docs.

## Architecture

PDF/DOCX → Marker parser → Markdown → Section-aware chunking → BGE-M3 embedding → Qdrant (vector store) + SQLite (metadata) → FastAPI + Web UI / REST API / MCP(SSE) → DeepSeek API (RAG answer).

### Data pipeline (per upload)

1. **Parser** ([src/parser/marker.py](src/parser/marker.py)) — calls external Marker CLI to convert PDF/DOCX to Markdown. File identity is SHA256 hash (the paper ID). Plain text/markdown files skip Marker and are copied as-is.
2. **Structure** ([src/parser/structure.py](src/parser/structure.py)) — extracts title, authors, abstract, and section hierarchy from parsed Markdown via regex patterns (supports Chinese + English).
3. **Chunker** ([src/chunker/paper_chunker.py](src/chunker/paper_chunker.py)) — section-aware chunking with sliding window. Sections are detected boundaries; large sections get windowed with overlap. Each chunk carries paper_id, section metadata, and text.
4. **Embedding** ([src/embedding/bge_m3.py](src/embedding/bge_m3.py)) — BGE-M3 1024-dim dense vectors + sparse lexical weights. Uses FlagEmbedding library with sentence-transformers fallback. Singleton encoder, lazy-loaded on first use.
5. **Vector store** ([src/retriever/qdrant_store.py](src/retriever/qdrant_store.py)) — Qdrant collection with cosine distance. Upsert/deletes chunks per paper. Lazy client singleton.
6. **Metadata DB** ([src/db/metadata.py](src/db/metadata.py)) — SQLite with WAL mode. Stores paper metadata (title, authors, year, journal, doi, tags, file paths).
7. **Search** ([src/retriever/search.py](src/retriever/search.py)) — dense-only search. Encodes query with BGE-M3, queries Qdrant with optional section/paper_id filter.

### Services

- **REST API** ([src/api/routes.py](src/api/routes.py)) — FastAPI router mounted at /api. Endpoints for upload (multi-file), list, get, delete, download original/zip, update tags, search, ask, streaming ask, index status/rebuild.
- **MCP Server** ([src/api/mcp_server.py](src/api/mcp_server.py)) — FastMCP SSE server mounted at /mcp. Exposes search_papers, get_paper_detail, get_paper_fulltext, list_papers, add_paper_to_library (info only).
- **LLM** ([src/llm/generator.py](src/llm/generator.py)) — DeepSeek API via httpx. Builds context from retrieved chunks, supports streaming. Requires DEEPSEEK_API_KEY in .env.
- **Web UI** ([src/web/static/](src/web/static/)) — Vanilla HTML/CSS/JS frontend served by FastAPI.

### Key config ([src/config.py](src/config.py))

Env vars prefixed with RAG_/QDRANT_/EMBEDDING_/LLM_/MARKER_. All config loaded from .env at import time. Key paths:
- `data/papers/` — uploaded files
- `data/parsed/` — Marker output (subdirs by paper ID)
- `data/metadata.db` — SQLite
- `qdrant_storage/` — Qdrant persist dir (gitignored)

### Upload flow ([src/api/routes.py:68](src/api/routes.py#L68))

1. Save uploaded file to `data/papers/` (SHA256 filename)
2. Convert via Marker → Markdown
3. Extract metadata (title, authors, sections)
4. Section-aware chunking → embedding → Qdrant upsert
5. Write metadata to SQLite

### MCP integration

MCP SSE endpoint at `/mcp/sse`. Mounted in [src/main.py:73](src/main.py#L73) via `mount_mcp()`. Config for clients (Claude Desktop, DeepSeek TUI) in README.

## Dependencies

Python 3.11+, uv/pip, Qdrant server, Marker CLI (external), DeepSeek API key.
