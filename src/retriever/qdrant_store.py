"""Qdrant 向量存储 — 仅 Dense 向量。"""

import logging
from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, OptimizersConfigDiff, PointStruct, VectorParams
from ..config import QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION, VECTOR_SIZE
from ..chunker.paper_chunker import TextChunk

logger = logging.getLogger(__name__)
_client: Optional[QdrantClient] = None

def get_client() -> QdrantClient:
    global _client
    if _client is None: _client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return _client

def ensure_collection() -> bool:
    client = get_client()
    try:
        client.get_collection(QDRANT_COLLECTION)
        return True
    except Exception:
        pass
    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        optimizers_config=OptimizersConfigDiff(indexing_threshold=0),
    )
    logger.info("Created collection: %s", QDRANT_COLLECTION)
    return True

def delete_collection():
    try: get_client().delete_collection(QDRANT_COLLECTION)
    except Exception: pass

def upsert_chunks(chunks: list[TextChunk], dense_vectors: list[list[float]],
                  sparse_vectors: list[dict]) -> int:
    if not chunks: return 0
    ensure_collection()
    client = get_client()
    points = [PointStruct(id=hash(c.id) & 0x7FFFFFFFFFFFFFFF,
                          vector=dense_vectors[i],
                          payload=c.to_payload())
              for i, c in enumerate(chunks)]
    client.upsert(collection_name=QDRANT_COLLECTION, points=points, wait=True)
    logger.info("Upserted %d chunks", len(points))
    return len(points)

def delete_by_paper_id(paper_id: str) -> int:
    get_client().delete(collection_name=QDRANT_COLLECTION,
                        points_selector={"filter": {"must": [{"key": "paper_id", "match": {"value": paper_id}}]}})
    return 0

def collection_info() -> dict:
    try:
        info = get_client().get_collection(QDRANT_COLLECTION)
        return {"name": QDRANT_COLLECTION, "points_count": info.points_count or 0}
    except Exception as e:
        return {"name": QDRANT_COLLECTION, "error": str(e)}
