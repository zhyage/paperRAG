"""
REST API 路由 — FastAPI 端点。
提供论文管理、检索、问答接口。
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, File, Form, UploadFile, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import (
    PROJECT_ROOT,
    PAPERS_DIR,
    PARSED_DIR,
    METADATA_DB,
)
from ..parser.marker import convert_paper, copy_upload_to_papers
from ..parser.structure import extract_metadata_from_markdown, extract_title_from_meta
from ..chunker.paper_chunker import chunk_paper
from ..embedding.bge_m3 import encode
from ..retriever.qdrant_store import upsert_chunks, delete_by_paper_id, collection_info
from ..retriever.search import search as rag_search
from ..llm.generator import generate_answer
from ..db.metadata import (
    init_db,
    add_paper as db_add_paper,
    get_paper as db_get_paper,
    list_papers as db_list_papers,
    delete_paper as db_delete_paper,
    update_paper_tags as db_update_tags,
    get_all_paper_ids,
)
from .export_import import (
    build_export_tarball,
    restore_from_tarball,
    get_reset_dry_run_info,
    execute_reset,
    CONFIRM_TOKEN,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["API"])


# ── 请求/响应模型 ─────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = 10
    section_filter: Optional[str] = None
    paper_id: Optional[str] = None


class AskRequest(BaseModel):
    question: str
    top_k: int = 10
    section_filter: Optional[str] = None
    paper_id: Optional[str] = None
    history: Optional[list[dict]] = None


class TagUpdate(BaseModel):
    tags: list[str]


# ── 论文管理 ──────────────────────────────────────────────

@router.post("/papers/upload")
async def upload_paper(
    files: list[UploadFile] = File(...),
    force_ocr: bool = Form(False),
    use_llm: bool = Form(False),
    page_range: str = Form(""),
    disable_image_extraction: bool = Form(False),
):
    """上传并索引一篇或多篇论文."""
    results = []
    for file in files:
        try:
            # 保存上传文件
            dest_path = await copy_upload_to_papers(file)

            # 用 Marker 解析
            result = await convert_paper(
                dest_path,
                force_ocr=force_ocr,
                use_llm=use_llm,
                page_range=page_range if page_range else None,
                disable_image_extraction=disable_image_extraction,
            )
            if not result["success"]:
                results.append({"filename": file.filename, "status": "error", "error": result['error']})
                continue

            md_path = result["parsed_md"]
            meta_path = result.get("parsed_meta")

            # 提取元数据
            struct = extract_metadata_from_markdown(md_path)
            title = struct.get("title") or extract_title_from_meta(meta_path) or file.filename

            # 分块
            chunks = chunk_paper(
                md_path,
                paper_id=result["file_id"],
                paper_title=title,
                authors=struct.get("authors", []),
                sections=struct.get("sections", []),
            )
            logger.info("Chunked paper %s into %d chunks", result["file_id"], len(chunks))

            # Embedding
            if chunks:
                chunk_texts = [c.text for c in chunks]
                vecs = encode(chunk_texts)
                dense = [v["dense"] for v in vecs]
                sparse = [v["sparse"] for v in vecs]
                upsert_chunks(chunks, dense, sparse)

            # 写元数据
            paper_meta = {
                "file_id": result["file_id"],
                "title": title,
                "authors": struct.get("authors", []),
                "abstract": struct.get("abstract", ""),
                "year": None,
                "journal": "",
                "doi": "",
                "tags": [],
                "filename": file.filename,
                "file_path": str(dest_path),
                "parsed_path": str(md_path),
                "page_count": 0,
            }
            db_add_paper(paper_meta)

            results.append({
                "paper_id": result["file_id"],
                "filename": file.filename,
                "title": title,
                "chunks": len(chunks),
                "status": "ok",
            })
        except Exception as e:
            logger.exception("Upload failed for %s", file.filename)
            results.append({"filename": file.filename, "status": "error", "error": str(e)})

    return {"results": results, "total": len(results)}


@router.get("/papers")
async def list_papers(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    tag: Optional[str] = None,
    year: Optional[int] = None,
    search: Optional[str] = None,
):
    """论文列表."""
    return db_list_papers(page=page, page_size=page_size, tag=tag, year=year, search=search)


@router.get("/papers/{paper_id}")
async def get_paper(paper_id: str):
    """论文详情."""
    paper = db_get_paper(paper_id)
    if not paper:
        raise HTTPException(404, "Paper not found")
    return paper


@router.delete("/papers/{paper_id}")
async def delete_paper(paper_id: str):
    """删除论文及其索引."""
    paper = db_get_paper(paper_id)
    if not paper:
        raise HTTPException(404, "Paper not found")

    db_delete_paper(paper_id)
    delete_by_paper_id(paper_id)

    # 删除解析文件
    parsed_dir = PARSED_DIR / paper_id
    if parsed_dir.exists():
        shutil.rmtree(parsed_dir)

    # 删除原始文件
    orig = Path(paper.get("file_path", ""))
    if orig.exists():
        orig.unlink(missing_ok=True)

    return {"status": "deleted"}


@router.put("/papers/{paper_id}/tags")
async def update_tags(paper_id: str, body: TagUpdate):
    """更新论文标签."""
    paper = db_update_tags(paper_id, body.tags)
    if not paper:
        raise HTTPException(404, "Paper not found")
    return paper


@router.get("/papers/{paper_id}/markdown")
async def get_paper_markdown(paper_id: str):
    """获取论文的解析后 Markdown 原文."""
    paper = db_get_paper(paper_id)
    if not paper:
        raise HTTPException(404, "Paper not found")
    parsed_path = paper.get("parsed_path", "")
    if not parsed_path or not os.path.exists(parsed_path):
        raise HTTPException(404, "Markdown not found")
    return FileResponse(parsed_path, media_type="text/markdown; charset=utf-8")



@router.get("/papers/{paper_id}/original")
async def download_original(paper_id: str):
    paper = db_get_paper(paper_id)
    if not paper: raise HTTPException(404, "Paper not found")
    fp = paper.get("file_path", "")
    if not fp or not os.path.exists(fp): raise HTTPException(404, "Original file not found")
    return FileResponse(fp, media_type="application/octet-stream", filename=paper.get("filename","paper.pdf"))


@router.get("/papers/{paper_id}/markdown-zip")
async def download_markdown_zip(paper_id: str):
    paper = db_get_paper(paper_id)
    if not paper: raise HTTPException(404, "Paper not found")
    parsed_dir = Path(paper.get("parsed_path", "")).parent
    if not parsed_dir.exists(): raise HTTPException(404, "Parsed files not found")
    import zipfile, io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(parsed_dir.iterdir()):
            zf.write(f, f.name)
    buf.seek(0)
    name = f"{paper_id[:12]}_parsed.zip"
    return StreamingResponse(iter([buf.read()]), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename={name}'})
# ── 检索 ──────────────────────────────────────────────────

@router.post("/search")
async def search_endpoint(req: SearchRequest):
    """语义检索."""
    hits = await rag_search(
        query=req.query,
        top_k=req.top_k,
        section_filter=req.section_filter,
        paper_id=req.paper_id,
    )
    return {"query": req.query, "results": hits, "count": len(hits)}


# ── 问答 ──────────────────────────────────────────────────

@router.post("/ask")
async def ask_endpoint(req: AskRequest):
    """基于检索结果生成回答."""
    hits = await rag_search(
        query=req.question,
        top_k=req.top_k,
        section_filter=req.section_filter,
        paper_id=req.paper_id,
    )

    if not hits:
        return {"answer": "No relevant papers found.", "sources": []}

    answer = await generate_answer(req.question, hits, req.history, stream=False)
    return {
        "answer": answer,
        "sources": [
            {
                "paper_id": h["paper_id"],
                "paper_title": h["paper_title"],
                "section": h["section_title"],
                "text_snippet": h["text"][:300],
                "score": h["score"],
            }
            for h in hits[:5]
        ],
    }


@router.post("/ask/stream")
async def ask_stream_endpoint(req: AskRequest):
    """流式回答."""
    hits = await rag_search(
        query=req.question,
        top_k=req.top_k,
        section_filter=req.section_filter,
        paper_id=req.paper_id,
    )

    if not hits:
        async def empty():
            yield "data: No relevant papers found.\n\n"
        return StreamingResponse(empty(), media_type="text/event-stream")

    async def stream_gen():
        gen = await generate_answer(req.question, hits, req.history, stream=True)
        async for chunk in gen:
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_gen(), media_type="text/event-stream")


# ── 索引状态 ──────────────────────────────────────────────

@router.get("/index/status")
async def index_status():
    """返回索引状态."""
    qdrant = collection_info()
    paper_count = len(get_all_paper_ids())
    return {
        "vector_store": qdrant,
        "paper_count": paper_count,
        "db_path": str(METADATA_DB),
        "qdrant_collection": qdrant.get("name", ""),
    }


@router.post("/index/rebuild")
async def rebuild_index():
    """重建全部索引（危险操作）."""
    from ..retriever.qdrant_store import delete_collection
    delete_collection()
    paper_ids = get_all_paper_ids()
    indexed = 0
    for pid in paper_ids:
        paper = db_get_paper(pid)
        if not paper:
            continue
        md_path = Path(paper.get("parsed_path", ""))
        if not md_path.exists():
            continue
        struct = extract_metadata_from_markdown(md_path)
        chunks = chunk_paper(
            md_path,
            paper_id=pid,
            paper_title=paper.get("title", ""),
            authors=paper.get("authors", []),
            sections=struct.get("sections", []),
        )
        if chunks:
            chunk_texts = [c.text for c in chunks]
            vecs = encode(chunk_texts)
            dense = [v["dense"] for v in vecs]
            sparse = [v["sparse"] for v in vecs]
            upsert_chunks(chunks, dense, sparse)
        indexed += 1
    return {"status": "rebuilt", "papers_indexed": indexed}


# ── 数据迁移 ──────────────────────────────────────────────

@router.get("/export")
async def export_data():
    """导出全部论文、向量、元数据为 tar.gz 包。"""
    import time
    buf = await build_export_tarball()
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    filename = f"paper-rag-export-{ts}.tar.gz"
    return StreamingResponse(
        iter([buf.read()]),
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_data(file: UploadFile = File(...)):
    """从导出的 tar.gz 包恢复数据（不走 Marker，不走 embedding）。"""
    if not file.filename or not file.filename.endswith(".tar.gz"):
        raise HTTPException(400, "Please upload a .tar.gz export file")
    result = await restore_from_tarball(file)
    return result


class ResetRequest(BaseModel):
    confirm: str = ""


@router.post("/reset")
async def reset_data(req: ResetRequest):
    """清空全部论文数据。需要确认令牌。"""
    if req.confirm != CONFIRM_TOKEN:
        info = get_reset_dry_run_info()
        raise HTTPException(
            400,
            detail={
                "error": f"Must confirm reset. Send confirm='{CONFIRM_TOKEN}'.",
                "hint": "Consider exporting your data first: GET /api/export",
                "would_delete": info,
            },
        )
    return execute_reset()
