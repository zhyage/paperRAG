"""
SQLite 元数据管理。
存储论文信息：标题、作者、摘要、年份、标签等。

表结构在 config.PAPER_TABLE_SCHEMA 中定义。
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import METADATA_DB, PAPER_TABLE_SCHEMA

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(METADATA_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """初始化数据库（幂等）."""
    conn = _get_conn()
    conn.execute(PAPER_TABLE_SCHEMA)
    conn.commit()
    conn.close()


def add_paper(paper: dict) -> dict:
    """
    添加一篇论文的元数据。

    参数:
        {
            "file_id": str,       # SHA256 hash
            "title": str,
            "authors": list[str],
            "abstract": str,
            "year": int | None,
            "journal": str,
            "doi": str,
            "tags": list[str],
            "filename": str,
            "file_path": str,
            "parsed_path": str,
            "page_count": int,
        }

    返回:
        写入的 dict。
    """
    conn = _get_conn()
    now = datetime.utcnow().isoformat()

    paper["tags"] = json.dumps(paper.get("tags", []))
    paper["authors"] = json.dumps(paper.get("authors", []))
    paper["created_at"] = now
    paper["updated_at"] = now

    conn.execute("""
        INSERT OR REPLACE INTO papers
        (id, title, authors, abstract, year, journal, doi, tags,
         filename, file_path, parsed_path, page_count, updated_at)
        VALUES (:file_id, :title, :authors, :abstract, :year, :journal, :doi,
                :tags, :filename, :file_path, :parsed_path, :page_count, :updated_at)
    """, paper)
    conn.commit()
    conn.close()
    return paper


def get_paper(paper_id: str) -> Optional[dict]:
    """按 ID 检索一篇论文."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_dict(row)


def list_papers(
    page: int = 1,
    page_size: int = 50,
    tag: Optional[str] = None,
    year: Optional[int] = None,
    search: Optional[str] = None,
) -> dict:
    """列出论文，支持分页和过滤."""
    conn = _get_conn()
    conditions = []
    params = []

    if tag:
        conditions.append("tags LIKE ?")
        params.append(f"%{tag}%")
    if year is not None:
        conditions.append("year = ?")
        params.append(year)
    if search:
        conditions.append("(title LIKE ? OR abstract LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    count_sql = f"SELECT COUNT(*) FROM papers{where}"
    total = conn.execute(count_sql, params).fetchone()[0]

    offset = (page - 1) * page_size
    sql = f"SELECT * FROM papers{where} ORDER BY updated_at DESC LIMIT ? OFFSET ?"
    rows = conn.execute(sql, params + [page_size, offset]).fetchall()
    conn.close()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "papers": [_row_to_dict(r) for r in rows],
    }


def delete_paper(paper_id: str) -> bool:
    """删除论文元数据."""
    conn = _get_conn()
    conn.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    conn.commit()
    conn.close()
    return True


def update_paper_tags(paper_id: str, tags: list[str]) -> Optional[dict]:
    """更新论文标签."""
    conn = _get_conn()
    conn.execute(
        "UPDATE papers SET tags = ?, updated_at = ? WHERE id = ?",
        (json.dumps(tags), datetime.utcnow().isoformat(), paper_id),
    )
    conn.commit()
    conn.close()
    return get_paper(paper_id)


def get_all_paper_ids() -> list[str]:
    """获取所有论文 ID."""
    conn = _get_conn()
    rows = conn.execute("SELECT id FROM papers").fetchall()
    conn.close()
    return [r["id"] for r in rows]


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for field in ["tags", "authors"]:
        if isinstance(d.get(field), str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                d[field] = []
    return d
