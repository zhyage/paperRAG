"""
论文章节结构提取。
从 Marker 输出的 Markdown 中提取标题、作者、摘要、章节。
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 常见学论文章节标题（中英文）────────────────────────────
SECTION_PATTERNS = [
    # 英文
    r"^#+\s*abstract\b",
    r"^#+\s*introduction\b",
    r"^#+\s*(related\s+)?(work|literature)\b",
    r"^#+\s*(method|approach|methodology|model|framework)\b",
    r"^#+\s*(experiment|evaluation|result)\b",
    r"^#+\s*(discussion|analysis)\b",
    r"^#+\s*(conclusion|summary|future\s+work)\b",
    r"^#+\s*(appendix|supplementary)\b",
    r"^#+\s*(reference|bibliography)\b",
    # 中文
    r"^#+\s*摘要\b",
    r"^#+\s*(引言|绪论|前言)\b",
    r"^#+\s*(相关)?(工作|研究|文献)\b",
    r"^#+\s*(方法|模型|框架|算法|实验)\b",
    r"^#+\s*(结果|分析|评价)\b",
    r"^#+\s*(讨论|结论|总结)\b",
    r"^#+\s*(附录|参考)\b",
]


def _normalize_section_title(title: str) -> str:
    """标准化章节标题到粗粒度类别."""
    title_lower = title.lower().strip("# *")
    for label in ["abstract", "摘要"]:
        if label in title_lower:
            return "abstract"
    for label in ["introduction", "引言", "绪论", "前言"]:
        if label in title_lower:
            return "introduction"
    for label in ["related work", "related", "相关工作", "文献综述"]:
        if label in title_lower:
            return "related_work"
    for label in ["method", "approach", "methodology", "model", "framework",
                  "方法", "模型", "框架", "算法"]:
        if label in title_lower:
            return "methods"
    for label in ["experiment", "evaluation", "result", "实验", "结果", "评价"]:
        if label in title_lower:
            return "results"
    for label in ["discussion", "analysis", "讨论", "分析"]:
        if label in title_lower:
            return "discussion"
    for label in ["conclusion", "summary", "future work", "结论", "总结"]:
        if label in title_lower:
            return "conclusion"
    for label in ["appendix", "supplementary", "附录"]:
        if label in title_lower:
            return "appendix"
    for label in ["reference", "bibliography", "参考"]:
        if label in title_lower:
            return "references"
    return "body"


def extract_metadata_from_markdown(md_path: Path) -> dict:
    """
    从 Markdown 文件中提取论文元数据。

    返回:
        {
            "title": str | None,
            "authors": list[str],
            "abstract": str | None,
            "sections": list[{"title": str, "level": int, "category": str, "line_start": int}],
        }
    """
    with open(md_path, encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        return _empty_result()

    title = None
    authors = []
    abstract = None
    sections = []

    # 第一行非空非标题行视为论文标题
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            title = stripped
            break
        elif stripped.startswith("# "):
            title = stripped.lstrip("# ").strip()
            break

    # 提取作者（通常在标题后面，"Authors:" 或中文 "作者：" 标记）
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^(authors?|作者)[：:]", stripped, re.IGNORECASE):
            author_line = re.sub(r"^(authors?|作者)[：:]\s*", "", stripped, flags=re.IGNORECASE)
            authors = [a.strip() for a in re.split(r"[,;，；]", author_line) if a.strip()]
            break

    # 提取摘要：Abstract 或 摘要 标记后的段落
    in_abstract = False
    abstract_lines = []
    for line in lines:
        stripped = line.strip()
        if re.match(r"^#+\s*(abstract|摘要)", stripped, re.IGNORECASE):
            in_abstract = True
            continue
        if in_abstract:
            if stripped.startswith("#") or (
                abstract_lines and not stripped
                and len(abstract_lines) > 5
            ):
                break
            if stripped:
                abstract_lines.append(stripped)
    if abstract_lines:
        abstract = " ".join(abstract_lines)

    # 提取章节结构
    for i, line in enumerate(lines):
        stripped = line.strip()
        match = re.match(r"^(#{1,4})\s+(.+)", stripped)
        if match:
            level = len(match.group(1))
            section_title = match.group(2).strip()
            section_title = re.sub(r"\[\d+\]$", "", section_title).strip()
            category = _normalize_section_title(section_title)
            sections.append({
                "title": section_title,
                "level": level,
                "category": category,
                "line_start": i,
            })

    return {
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "sections": sections,
    }


def extract_title_from_meta(meta_path: Optional[Path]) -> str:
    """从 Marker 输出的 meta.json 中提取标题."""
    if not meta_path or not meta_path.exists():
        return ""
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        if isinstance(meta, dict):
            return meta.get("title", "") or meta.get("pdf_title", "") or ""
    except Exception:
        pass
    return ""


def _empty_result() -> dict:
    return {"title": None, "authors": [], "abstract": None, "sections": []}
