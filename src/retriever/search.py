"""Dense-only retrieval."""

import logging
from ..config import RETRIEVE_TOP_K
from .qdrant_store import get_client, ensure_collection, QDRANT_COLLECTION
from ..embedding.bge_m3 import encode_query

logger = logging.getLogger(__name__)

async def search(query, top_k=None, section_filter=None, paper_id=None):
    if top_k is None: top_k = RETRIEVE_TOP_K
    ensure_collection()
    client = get_client()
    qv = encode_query(query)
    must = []
    if section_filter: must.append({"key": "section_category", "match": {"value": section_filter}})
    if paper_id: must.append({"key": "paper_id", "match": {"value": paper_id}})
    qfilter = {"must": must} if must else None
    result = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=qv["dense"],
        limit=top_k, with_payload=True, query_filter=qfilter,
    )
    hits = []
    for pt in result.points:
        p = pt.payload or {}
        hits.append({
            "paper_id": p.get("paper_id",""),
            "paper_title": p.get("paper_title",""),
            "section_title": p.get("section_title",""),
            "section_category": p.get("section_category",""),
            "text": p.get("text",""),
            "authors": p.get("authors",[]),
            "score": pt.score,
            "chunk_index": p.get("chunk_index",0),
        })
    return hits

async def search_by_paper_id(paper_id, query, top_k=None):
    return await search(query, top_k=top_k, paper_id=paper_id)
