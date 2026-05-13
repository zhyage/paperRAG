"""Marker 文档解析封装。"""

import asyncio
import hashlib
import logging
import shutil
from pathlib import Path
from typing import Optional

from ..config import (
    MARKER_SCRIPT, MARKER_FORCE_OCR, MARKER_USE_LLM,
    PARSED_DIR, PAPERS_DIR,
)

logger = logging.getLogger(__name__)

_MARKER_PYTHON = str(Path.home() / ".deepseek/skills/tomarkdown/venv/bin/python3")
_SKIP_MARKER_EXT = {".md", ".txt", ".markdown"}


def _file_hash(file_path: Path) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


async def convert_paper(
    file_path: Path,
    force_ocr: Optional[bool] = None,
    use_llm: Optional[bool] = None,
    page_range: Optional[str] = None,
    disable_image_extraction: Optional[bool] = None,
) -> dict:
    if force_ocr is None:
        force_ocr = MARKER_FORCE_OCR
    if use_llm is None:
        use_llm = MARKER_USE_LLM

    file_id = _file_hash(file_path)
    output_dir = PARSED_DIR / file_id
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = file_path.stem
    ext = file_path.suffix.lower()
    expected_md = output_dir / f"{stem}.md"
    expected_meta = output_dir / f"{stem}_meta.json"

    if expected_md.exists():
        logger.info("Already parsed: %s", file_path.name)
        return {"file_id": file_id, "original_path": file_path,
                "parsed_md": expected_md, "parsed_meta": expected_meta,
                "success": True, "error": None}

    if ext in _SKIP_MARKER_EXT:
        shutil.copy2(file_path, expected_md)
        logger.info("Skipped Marker for %s, using as-is", file_path.name)
        return {"file_id": file_id, "original_path": file_path,
                "parsed_md": expected_md, "parsed_meta": None,
                "success": True, "error": None}

    cmd = [_MARKER_PYTHON, str(MARKER_SCRIPT), str(file_path), "-o", str(output_dir)]
    if force_ocr:
        cmd.append("--force-ocr")
    if use_llm:
        cmd.append("--use-llm")
    if page_range:
        cmd.append("--page-range")
        cmd.append(page_range)
    if disable_image_extraction:
        cmd.append("--disable-image-extraction")

    flags = []
    if force_ocr: flags.append("OCR")
    if use_llm: flags.append("LLM")
    if page_range: flags.append(f"p.{page_range}")
    logger.info("Marker converting: %s [%s]", file_path.name, ", ".join(flags) or "default")

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        error_msg = stderr.decode("utf-8", errors="replace")
        logger.error("Marker failed: %s", error_msg[:500])
        return {"file_id": file_id, "original_path": file_path,
                "parsed_md": None, "parsed_meta": None,
                "success": False, "error": error_msg[:1000]}

    if not expected_md.exists():
        return {"file_id": file_id, "original_path": file_path,
                "parsed_md": None, "parsed_meta": None,
                "success": False, "error": f"Output not found: {expected_md}"}

    logger.info("Converted: %s -> %s", file_path.name, expected_md)
    return {"file_id": file_id, "original_path": file_path,
            "parsed_md": expected_md,
            "parsed_meta": expected_meta if expected_meta.exists() else None,
            "success": True, "error": None}


async def copy_upload_to_papers(uploaded_file) -> Path:
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    content = await uploaded_file.read()
    h = hashlib.sha256(content).hexdigest()
    ext = Path(uploaded_file.filename).suffix.lower()
    dest_path = PAPERS_DIR / f"{h}{ext}"
    if not dest_path.exists():
        dest_path.write_bytes(content)
    return dest_path
