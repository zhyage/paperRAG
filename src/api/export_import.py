"""
Export / Import / Reset — 数据迁移模块。

导出：将全部论文数据打包为 tar.gz
导入：从 tar.gz 恢复数据（不走 Marker、不走 embedding）
重置：清空全部数据（需确认令牌）
"""

import io
import json
import logging
import os
import shutil
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile

from ..config import PROJECT_ROOT, PAPERS_DIR, PARSED_DIR, METADATA_DB, QDRANT_COLLECTION
from ..db.metadata import _get_conn, PAPER_TABLE_SCHEMA, _row_to_dict

logger = logging.getLogger(__name__)

VERSION = "1"
CONFIRM_TOKEN = "DELETE_ALL_MY_PAPERS"
BATCH_SIZE = 200


# ═══════════════════════════════════════════════════════════════
# Export
# ═══════════════════════════════════════════════════════════════

async def build_export_tarball() -> io.BytesIO:
    """构建导出 tar.gz，返回内存中的 BytesIO 对象。"""
    buf = io.BytesIO()
    tf = tarfile.open(mode="w:gz", fileobj=buf)

    metadata_lines = _export_metadata_jsonl()
    vector_lines = _export_vectors_jsonl()
    manifest = json.dumps(_build_manifest(metadata_lines, vector_lines), indent=2)

    _add_string_to_tar(tf, "metadata.jsonl", "".join(metadata_lines))
    _add_string_to_tar(tf, "vectors.jsonl", "".join(vector_lines))
    _add_string_to_tar(tf, "manifest.json", manifest)

    _add_dir_to_tar(tf, PAPERS_DIR, "papers")
    _add_dir_to_tar(tf, PARSED_DIR, "parsed")

    tf.close()
    buf.seek(0)
    return buf


def _export_metadata_jsonl() -> list[str]:
    """从 SQLite 导出全部论文为 JSONL 行列表。"""
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM papers ORDER BY created_at").fetchall()
    conn.close()
    lines = []
    for row in rows:
        d = _row_to_dict(row)
        lines.append(json.dumps(d, ensure_ascii=False) + "\n")
    logger.info("Exported %d papers metadata", len(lines))
    return lines


def _export_vectors_jsonl() -> list[str]:
    """从 Qdrant scroll 导出全部 point 为 JSONL 行列表。"""
    try:
        from ..retriever.qdrant_store import get_client
    except Exception:
        logger.warning("Qdrant client unavailable, exporting empty vectors")
        return []

    try:
        client = get_client()
    except Exception as e:
        logger.warning("Qdrant connect failed: %s, exporting empty vectors", e)
        return []

    lines = []
    offset = None

    try:
        while True:
            pts, next_offset = client.scroll(
                collection_name=QDRANT_COLLECTION,
                limit=BATCH_SIZE,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            for p in pts:
                obj = {
                    "id": p.id,
                    "vector": p.vector,
                    "payload": p.payload,
                }
                lines.append(json.dumps(obj, ensure_ascii=False) + "\n")

            if next_offset is None:
                break
            offset = next_offset
    except Exception as e:
        logger.warning("Qdrant scroll failed: %s, exported %d chunks so far", e, len(lines))

    logger.info("Exported %d chunks from Qdrant", len(lines))
    return lines


def _build_manifest(metadata_lines: list[str], vector_lines: list[str]) -> dict:
    return {
        "version": VERSION,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "paper_count": len(metadata_lines),
        "chunk_count": len(vector_lines),
    }


def _add_string_to_tar(tf: tarfile.TarFile, name: str, content: str):
    ti = tarfile.TarInfo(name=name)
    data = content.encode("utf-8")
    ti.size = len(data)
    tf.addfile(ti, io.BytesIO(data))


def _add_dir_to_tar(tf: tarfile.TarFile, src_dir: Path, arcname: str):
    """递归添加目录到 tar，忽略不存在的路径。"""
    if not src_dir.exists():
        return
    for root, dirs, files in os.walk(src_dir):
        for fname in files:
            fpath = Path(root) / fname
            rel = fpath.relative_to(src_dir.parent)
            tf.add(str(fpath), arcname=str(rel))


# ═══════════════════════════════════════════════════════════════
# Import
# ═══════════════════════════════════════════════════════════════

async def restore_from_tarball(uploaded_file: UploadFile) -> dict:
    """从上传的 tar.gz 恢复数据。"""
    tmpdir = tempfile.mkdtemp(prefix="paper-rag-import-")

    try:
        content = await uploaded_file.read()
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tf:
            tf.extractall(tmpdir)

        tmp = Path(tmpdir)

        manifest_path = tmp / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            logger.info("Importing package v%s: %d papers, %d chunks",
                        manifest.get("version"), manifest.get("paper_count"), manifest.get("chunk_count"))

        # 恢复文件
        _copy_tree_if_exists(tmp / "papers", PAPERS_DIR)
        _copy_tree_if_exists(tmp / "parsed", PARSED_DIR)

        # 恢复元数据
        metadata_path = tmp / "metadata.jsonl"
        papers_count = _import_metadata_jsonl(metadata_path) if metadata_path.exists() else 0

        # 恢复向量
        vectors_path = tmp / "vectors.jsonl"
        chunks_count = _import_vectors_jsonl(vectors_path) if vectors_path.exists() else 0

        return {"status": "ok", "papers_imported": papers_count, "chunks_upserted": chunks_count}

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _copy_tree_if_exists(src: Path, dst: Path):
    """将 src 下所有文件复制到 dst（如果 src 存在）。"""
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src):
        for fname in files:
            fpath = Path(root) / fname
            rel = fpath.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fpath, target)


def _import_metadata_jsonl(path: Path) -> int:
    """从 JSONL 文件恢复元数据到 SQLite。"""
    conn = _get_conn()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(PAPER_TABLE_SCHEMA)
    count = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            paper = json.loads(line)
            paper["authors"] = json.dumps(paper.get("authors", []))
            paper["tags"] = json.dumps(paper.get("tags", []))
            conn.execute("""
                INSERT OR REPLACE INTO papers
                (id, title, authors, abstract, year, journal, doi, tags,
                 filename, file_path, parsed_path, page_count, created_at, updated_at)
                VALUES (:id, :title, :authors, :abstract, :year, :journal, :doi,
                        :tags, :filename, :file_path, :parsed_path, :page_count,
                        :created_at, :updated_at)
            """, paper)
            count += 1
    conn.commit()
    conn.close()
    logger.info("Imported %d papers to SQLite", count)
    return count


def _import_vectors_jsonl(path: Path) -> int:
    """从 JSONL 文件恢复向量到 Qdrant，批量 upsert。"""
    from qdrant_client.models import PointStruct

    # 文件为空则跳过
    if path.stat().st_size == 0:
        logger.info("vectors.jsonl is empty, skipping Qdrant import")
        return 0

    try:
        from ..retriever.qdrant_store import get_client, ensure_collection
    except Exception as e:
        logger.warning("Qdrant client unavailable, skipping vector import: %s", e)
        return 0

    try:
        client = get_client()
        ensure_collection()
    except Exception as e:
        logger.warning("Qdrant connect failed, skipping vector import: %s", e)
        return 0

    batch = []
    total = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                batch.append(PointStruct(id=obj["id"], vector=obj["vector"], payload=obj["payload"]))
                if len(batch) >= BATCH_SIZE:
                    client.upsert(collection_name=QDRANT_COLLECTION, points=batch, wait=True)
                    total += len(batch)
                    batch.clear()

        if batch:
            client.upsert(collection_name=QDRANT_COLLECTION, points=batch, wait=True)
            total += len(batch)
    except Exception as e:
        logger.warning("Qdrant upsert failed: %s, imported %d chunks", e, total)
        return total

    logger.info("Upserted %d chunks to Qdrant", total)
    return total


# ═══════════════════════════════════════════════════════════════
# Reset
# ═══════════════════════════════════════════════════════════════

def get_reset_dry_run_info() -> dict:
    """返回如果执行 reset 会删除哪些数据的统计信息。"""
    conn = _get_conn()
    paper_count = conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
    conn.close()

    chunk_count = 0
    try:
        from ..retriever.qdrant_store import get_client
        info = get_client().get_collection(QDRANT_COLLECTION)
        chunk_count = info.points_count or 0
    except Exception:
        pass

    return {
        "papers": paper_count,
        "chunks": chunk_count,
        "files": ["data/papers/", "data/parsed/"],
    }


def execute_reset() -> dict:
    """执行清空：删除 Qdrant collection、SQLite 表、文件。"""
    # Qdrant — 删除并重建 collection
    try:
        from ..retriever.qdrant_store import delete_collection, ensure_collection
        delete_collection()
        ensure_collection()
    except Exception as e:
        logger.warning("Qdrant reset warning: %s", e)

    # SQLite — 删除并重建表
    conn = _get_conn()
    conn.execute("DROP TABLE IF EXISTS papers")
    conn.execute(PAPER_TABLE_SCHEMA)
    conn.commit()
    conn.close()
    logger.info("SQLite papers table recreated")

    # 文件 — 清空 papers/ 和 parsed/
    paper_count = 0
    for data_dir in [PAPERS_DIR, PARSED_DIR]:
        if data_dir.exists():
            count = sum(1 for _ in data_dir.rglob("*") if _.is_file())
            paper_count += count
            shutil.rmtree(data_dir)
            data_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Reset complete: removed %d files", paper_count)
    return {"status": "ok", "files_removed": paper_count}
