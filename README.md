# Paper RAG — Personal Academic Paper RAG System

Build your own RAG knowledge base for academic papers. Parse PDF/DOCX with Marker, embed with BGE-M3, store in Qdrant, semantic search via Web UI + REST API + MCP.

## Architecture

```
 PDF/DOCX → Marker → Markdown → Chapter Split → BGE-M3 → Qdrant (dense)
                                              ↓
                                         SQLite metadata
                                              ↓
                      FastAPI ← Web UI / REST API / MCP(SSE)
                         ↓
                   DeepSeek API (RAG answer)
```

## Quick Start

### 1. Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager (or pip)
- [Qdrant](https://qdrant.tech/) vector database
- [Marker](https://github.com/VikParuchuri/marker) document parser (included as tomarkdown skill)
- **DeepSeek API key** (required for LLM generation — see [Setting API Key](#setting-api-key))

### 2. Install

```bash
# Clone the repo
git clone <your-repo-url>
cd paper-rag

# Install with uv
uv sync

# Or with pip
pip install -e .
```

### 3. Setting API Key

**This step is required for the Ask AI feature to work.**

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and set your DeepSeek API key:

```ini
DEEPSEEK_API_KEY=sk-your-actual-key-here
```

> **Get a key**: Register at [platform.deepseek.com](https://platform.deepseek.com) → API Keys → Create.  
> **No key?** Search still works, but Ask AI (LLM generation) will return an error.  
> **Never commit `.env`** — it's in `.gitignore`.

### 4. Install Qdrant

```bash
# Docker (recommended)
docker run -d -p 6333:6333 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant

# Or download binary
curl -L https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-gnu.tar.gz | tar xz
./qdrant
```

### 5. Initialize

```bash
uv run python -c "from src.db.metadata import init_db; init_db(); print('OK')"
```

### 6. Run

```bash
# Development server
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8765

# Production (after pip install)
uvicorn src.main:app --host 0.0.0.0 --port 8765
```

### 7. Open Web UI

Navigate to **http://localhost:8765**

## Features

### 📚 Library Management
- Upload PDF/DOCX papers
- Auto-parsed via Marker (tables, equations, figures preserved)
- Download original PDF or parsed Markdown ZIP
- Tag, search, and organize your paper collection

### 🔍 Semantic Search
- BGE-M3 embedding (1024-dim dense vectors)
- Search across all papers by content, not just titles
- Filter by section (abstract, methods, results, references)

### 🤖 Ask AI (RAG)
- Ask questions about your paper library
- DeepSeek API generates answers grounded in your documents
- Sources cited with paper title and section

### 🔌 MCP Integration
Add to your MCP client config (DeepSeek TUI, Claude Desktop):

```json
{
  "mcpServers": {
    "paper-rag": {
      "url": "http://localhost:8765/mcp/sse"
    }
  }
}
```

MCP tools: `search_papers`, `get_paper_detail`, `get_paper_fulltext`, `list_papers`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST   | `/api/papers/upload` | Upload and index a paper |
| GET    | `/api/papers` | List papers (paginated) |
| GET    | `/api/papers/{id}` | Paper metadata |
| GET    | `/api/papers/{id}/original` | Download original PDF |
| GET    | `/api/papers/{id}/markdown-zip` | Download parsed Markdown + images ZIP |
| DELETE | `/api/papers/{id}` | Delete paper and index |
| GET    | `/api/papers/{id}/markdown` | Raw parsed markdown |
| PUT    | `/api/papers/{id}/tags` | Update paper tags |
| POST   | `/api/search` | Semantic search |
| POST   | `/api/ask` | RAG question-answering |
| POST   | `/api/ask/stream` | Streaming RAG answer |
| GET    | `/api/index/status` | Index statistics |
| POST   | `/api/index/rebuild` | Rebuild all indexes |
| GET    | `/api/export` | Export all data as tar.gz |
| POST   | `/api/import` | Import data from tar.gz (no re-parsing) |
| POST   | `/api/reset` | Clear all data (requires confirm token) |

## Configuration

All settings via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | — | **Required** for Ask AI |
| `QDRANT_HOST` | `localhost` | Qdrant server address |
| `QDRANT_PORT` | `6333` | Qdrant port |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | Embedding model |
| `EMBEDDING_DEVICE` | `cpu` | or `cuda` |
| `RAG_HOST` | `0.0.0.0` | Bind address |
| `RAG_PORT` | `8765` | Bind port |
| `ENABLE_RERANK` | `true` | Cross-encoder reranking |
| `LLM_MODEL` | `deepseek-chat` | LLM model name |
| `MARKER_FORCE_OCR` | `false` | Force OCR mode |

## Project Structure

```
paper-rag/
├── pyproject.toml
├── .env.example              # Template — copy to .env and fill in
├── .gitignore
├── MANIFEST.in
├── README.md
├── src/
│   ├── __init__.py
│   ├── config.py              # All settings (reads .env)
│   ├── main.py                # FastAPI entry point
│   ├── parser/
│   │   ├── marker.py          # Marker PDF/DOCX converter
│   │   └── structure.py       # Metadata extractor
│   ├── chunker/
│   │   └── paper_chunker.py   # Section-aware chunking
│   ├── embedding/
│   │   └── bge_m3.py          # BGE-M3 embedding
│   ├── retriever/
│   │   ├── qdrant_store.py    # Qdrant collection management
│   │   └── search.py          # Dense vector search
│   ├── llm/
│   │   └── generator.py       # DeepSeek API RAG generation
│   ├── db/
│   │   └── metadata.py        # SQLite metadata CRUD
│   ├── api/
│   │   ├── routes.py          # REST endpoints
│   │   └── mcp_server.py      # MCP tools (SSE)
│   └── web/
│       └── static/
│           ├── index.html
│           ├── app.js
│           └── style.css
├── data/                      # Created at runtime (gitignored)
│   ├── papers/                # Original PDF/DOCX files
│   ├── parsed/                # Marker output markdown
│   └── metadata.db            # SQLite database
└── qdrant_storage/            # Qdrant persistence (gitignored)
```

## Notes

- **First startup** downloads BGE-M3 model (~2.2 GB) from HuggingFace
- **Marker first run** downloads OCR models (~2-4 GB)
- Total disk: ~10 GB for models + space for papers
- For CPU-only, set `EMBEDDING_DEVICE=cpu`

## License

MIT
