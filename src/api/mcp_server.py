"""
MCP Server — 将 RAG 能力暴露为 MCP Tools（SSE 模式）。

其他机器可通过 MCP 客户端连接，调用 search / get_paper / list_papers 等。
"""

import json
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

from ..config import MCP_SSE_PATH, HOST, PORT
from ..retriever.search import search as rag_search
from ..db.metadata import (
    get_paper as db_get_paper,
    list_papers as db_list_papers,
)

logger = logging.getLogger(__name__)

# 创建 FastMCP 实例
mcp = FastMCP(
    "paper-rag",
    host=HOST,
    port=PORT,
    sse_path=MCP_SSE_PATH,
    message_path="/mcp/messages",
)


@mcp.tool()
async def search_papers(
    query: str,
    top_k: int = 10,
    section_filter: str = "",
) -> str:
    """
    Search your paper library using semantic (vector) search.

    Args:
        query: Natural language search query (Chinese or English)
        top_k: Number of results to return (default 10)
        section_filter: Optional section type filter, e.g. 'methods', 'results', 'abstract'

    Returns:
        JSON string with search results, each containing paper title, section, text snippet, and score.
    """
    hits = await rag_search(
        query=query,
        top_k=top_k,
        section_filter=section_filter if section_filter else None,
    )
    results = []
    for h in hits:
        results.append({
            "paper_id": h["paper_id"],
            "paper_title": h["paper_title"],
            "section": h["section_title"],
            "section_category": h["section_category"],
            "text_snippet": h["text"][:500],
            "authors": h.get("authors", []),
            "score": round(h["score"], 4) if h["score"] else None,
        })
    return json.dumps(results, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_paper_detail(paper_id: str) -> str:
    """
    Get full metadata for a specific paper by its ID.

    Args:
        paper_id: The paper's unique ID (returned from search_papers)

    Returns:
        JSON string with paper metadata: title, authors, abstract, year, journal, tags.
    """
    paper = db_get_paper(paper_id)
    if not paper:
        return json.dumps({"error": "Paper not found"})
    # 去掉可能冗余的字段
    safe = {
        "id": paper.get("id"),
        "title": paper.get("title"),
        "authors": paper.get("authors", []),
        "abstract": paper.get("abstract", ""),
        "year": paper.get("year"),
        "journal": paper.get("journal", ""),
        "doi": paper.get("doi", ""),
        "tags": paper.get("tags", []),
        "page_count": paper.get("page_count", 0),
        "filename": paper.get("filename", ""),
    }
    return json.dumps(safe, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_paper_fulltext(paper_id: str) -> str:
    """
    Get the full parsed markdown text of a paper.

    Args:
        paper_id: The paper's unique ID

    Returns:
        Full markdown text of the paper.
    """
    paper = db_get_paper(paper_id)
    if not paper:
        return json.dumps({"error": "Paper not found"})
    parsed_path = paper.get("parsed_path", "")
    if not parsed_path:
        return json.dumps({"error": "Paper has no parsed markdown"})
    try:
        with open(parsed_path, encoding="utf-8") as f:
            text = f.read()
        # 截断到安全长度（MCP 工具返回不能太大）
        max_len = 50000
        if len(text) > max_len:
            text = text[:max_len] + "\n\n... [truncated]"
        return text
    except FileNotFoundError:
        return json.dumps({"error": "Parsed file not found on disk"})


@mcp.tool()
async def list_papers(
    page: int = 1,
    tag: str = "",
    search: str = "",
) -> str:
    """
    List papers in your library.

    Args:
        page: Page number (default 1, 50 per page)
        tag: Filter by tag (fuzzy match)
        search: Search in title and abstract

    Returns:
        JSON string with paper list and pagination info.
    """
    result = db_list_papers(
        page=page,
        page_size=50,
        tag=tag if tag else None,
        search=search if search else None,
    )
    papers = []
    for p in result["papers"]:
        papers.append({
            "id": p.get("id"),
            "title": p.get("title"),
            "authors": p.get("authors", []),
            "year": p.get("year"),
            "journal": p.get("journal", ""),
            "tags": p.get("tags", []),
        })
    return json.dumps({
        "total": result["total"],
        "page": result["page"],
        "papers": papers,
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def add_paper_to_library(file_path: str) -> str:
    """
    Add a new paper to the library from a local file path.

    NOTE: This tool expects the file to already exist on the server's filesystem.
    To upload a file, use the web UI or the HTTP API directly.

    Args:
        file_path: Absolute path to the PDF/DOCX/Markdown file on the server

    Returns:
        JSON with paper_id, title, and status.
    """
    # 这只是一个信息性提示 — 实际上传需要通过 HTTP API
    return json.dumps({
        "error": "add_paper_by_file_path requires the file on the server. "
                 "Use the web UI at http://<host>:<port> to upload files, "
                 "or call POST /api/papers/upload directly."
    })
