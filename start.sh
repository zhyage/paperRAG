#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
QDRANT_STORAGE="${PROJECT_DIR}/qdrant_storage"
QDRANT_CONTAINER="qdrant-paper-rag"

echo "=== Paper RAG Startup ==="

# ── 1. Qdrant ────────────────────────────────────────────────
if docker ps --format '{{.Names}}' | grep -q "^${QDRANT_CONTAINER}$"; then
    echo "[OK] Qdrant container '${QDRANT_CONTAINER}' is already running."
elif docker ps -a --format '{{.Names}}' | grep -q "^${QDRANT_CONTAINER}$"; then
    echo "[*] Starting existing Qdrant container..."
    docker start "${QDRANT_CONTAINER}" >/dev/null
    echo "[OK] Qdrant started."
else
    echo "[*] Creating and starting Qdrant container..."
    docker run -d \
        --name "${QDRANT_CONTAINER}" \
        -p 6333:6333 \
        -v "${QDRANT_STORAGE}:/qdrant/storage" \
        qdrant/qdrant >/dev/null
    echo "[OK] Qdrant container created and running."
fi

# ── 2. Wait for Qdrant ───────────────────────────────────────
echo -n "[*] Waiting for Qdrant..."
for i in $(seq 1 30); do
    if curl -s "http://localhost:6333/collections" >/dev/null 2>&1; then
        echo " ready."
        break
    fi
    sleep 1
    echo -n "."
done

# ── 3. Initialize DB ─────────────────────────────────────────
echo "[*] Initializing SQLite database..."
cd "${PROJECT_DIR}"
uv run python -c "from src.db.metadata import init_db; init_db()" 2>/dev/null || true
echo "[OK] Database ready."

# ── 4. Start Paper RAG ────────────────────────────────────────
echo "[*] Starting Paper RAG server on http://0.0.0.0:8765"
echo "    Web UI:  http://localhost:8765"
echo "    API docs: http://localhost:8765/docs"
echo ""
uv run uvicorn src.main:app --host 0.0.0.0 --port 8765
