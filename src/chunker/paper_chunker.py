"""
论文章节感知分块器。
按章节语义边界切分，长章节用滑动窗口 + 重叠切分。
"""

import logging
from pathlib import Path
from typing import Iterator

from ..config import CHUNK_MIN_SIZE, CHUNK_MAX_SIZE, CHUNK_OVERLAP

logger = logging.getLogger(__name__)

# 通用 token 估算：中文约 1.5 字符/token，英文约 4 字符/token
# 取中位数近似
_CHARS_PER_TOKEN_ESTIMATE = 3.0


class TextChunk:
    """一个分块的表示."""
    __slots__ = ("id", "text", "section_category", "section_title",
                 "paper_id", "paper_title", "authors", "chunk_index",
                 "token_estimate")

    def __init__(self, id: str, text: str, section_category: str,
                 section_title: str, paper_id: str, paper_title: str,
                 authors: list[str], chunk_index: int):
        self.id = id
        self.text = text
        self.section_category = section_category
        self.section_title = section_title
        self.paper_id = paper_id
        self.paper_title = paper_title
        self.authors = authors
        self.chunk_index = chunk_index
        self.token_estimate = int(len(text) / _CHARS_PER_TOKEN_ESTIMATE)

    def to_payload(self) -> dict:
        """转为 Qdrant payload."""
        return {
            "paper_id": self.paper_id,
            "paper_title": self.paper_title,
            "authors": self.authors,
            "section_category": self.section_category,
            "section_title": self.section_title,
            "chunk_index": self.chunk_index,
            "text": self.text,
        }


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / _CHARS_PER_TOKEN_ESTIMATE))


def _sliding_window_chunk(
    lines: list[str],
    section: dict,
    paper_id: str,
    paper_title: str,
    authors: list[str],
    chunk_index: int,
    start_line: int,
    end_line: int,
) -> list[TextChunk]:
    """
    对单个章节做滑动窗口分块。

    策略：
    1. 如果章节总 token 数 < CHUNK_MAX_SIZE，作为一个 chunk
    2. 否则用滑动窗口切分，窗口大小 CHUNK_MAX_SIZE，步长 CHUNK_MAX_SIZE - CHUNK_OVERLAP
    3. 短于 CHUNK_MIN_SIZE 的末尾片段合并到前一个 chunk
    """
    section_text = "".join(lines[start_line:end_line]).strip()
    if not section_text:
        return []

    total_tokens = _estimate_tokens(section_text)
    chunks = []

    # 小章节直接做一块
    if total_tokens <= CHUNK_MAX_SIZE:
        chunk = TextChunk(
            id=f"{paper_id}:{chunk_index}",
            text=section_text,
            section_category=section.get("category", "body"),
            section_title=section.get("title", ""),
            paper_id=paper_id,
            paper_title=paper_title,
            authors=authors,
            chunk_index=chunk_index,
        )
        return [chunk]

    # 大章节滑动窗口
    step = CHUNK_MAX_SIZE - CHUNK_OVERLAP
    step_chars = int(step * _CHARS_PER_TOKEN_ESTIMATE)
    overlap_chars = int(CHUNK_OVERLAP * _CHARS_PER_TOKEN_ESTIMATE)

    pos = 0
    while pos < len(section_text):
        # 按 token 目标截取，但在自然断点处断开（换行或句号）
        end_pos = pos + step_chars
        if end_pos < len(section_text):
            # 找到最近的句子边界
            search_start = max(pos + step_chars - 200, pos)
            for sep in ["\n\n", "\n", ". ", "。 ", "; ", "；", " "]:
                idx = section_text.find(sep, search_start, end_pos + 200)
                if idx != -1:
                    end_pos = idx + len(sep)
                    break

        chunk_text = section_text[pos:min(end_pos, len(section_text))].strip()
        if not chunk_text:
            pos = end_pos
            continue

        # 最后一块太小则跳过（已被重叠覆盖）
        if end_pos >= len(section_text) and _estimate_tokens(chunk_text) < CHUNK_MIN_SIZE:
            break

        chunks.append(TextChunk(
            id=f"{paper_id}:{chunk_index + len(chunks)}",
            text=chunk_text,
            section_category=section.get("category", "body"),
            section_title=section.get("title", ""),
            paper_id=paper_id,
            paper_title=paper_title,
            authors=authors,
            chunk_index=chunk_index + len(chunks),
        ))

        pos = end_pos - overlap_chars if end_pos < len(section_text) - overlap_chars else end_pos

    return chunks


def chunk_paper(
    md_path: Path | str,
    paper_id: str,
    paper_title: str = "",
    authors: list[str] | None = None,
    sections: list[dict] | None = None,
) -> list[TextChunk]:
    """
    对一篇论文的 Markdown 文本按章节 + 滑动窗口分块。

    参数:
        md_path: Markdown 文件路径
        paper_id: 论文唯一 ID
        paper_title: 论文标题
        authors: 作者列表
        sections: 章节信息列表 [{"title", "level", "category", "line_start"}, ...]

    返回:
        TextChunk 列表
    """
    if authors is None:
        authors = []
    if sections is None:
        sections = []

    md_path = Path(md_path) if isinstance(md_path, str) else md_path

    with open(md_path, encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        return []

    # 如果没有传入章节信息，按标题行自行检测
    if not sections:
        from ..parser.structure import extract_metadata_from_markdown
        meta = extract_metadata_from_markdown(md_path)
        sections = meta["sections"]

    # 按章节分割
    if sections:
        boundaries = sorted(sections, key=lambda s: s["line_start"])
        all_chunks = []
        chunk_base_index = 0

        for idx, section in enumerate(boundaries):
            start_line = section["line_start"]
            end_line = (boundaries[idx + 1]["line_start"]
                        if idx + 1 < len(boundaries)
                        else len(lines))
            chunks = _sliding_window_chunk(
                lines, section, paper_id, paper_title, authors,
                chunk_base_index, start_line, end_line,
            )
            all_chunks.extend(chunks)
            chunk_base_index += len(chunks)

        return all_chunks
    else:
        # 没有检测到章节，整篇论文按一个体对待
        return _sliding_window_chunk(
            lines,
            {"title": "Full Paper", "category": "body"},
            paper_id, paper_title, authors, 0, 0, len(lines),
        )
