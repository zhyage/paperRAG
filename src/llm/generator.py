"""
LLM 生成模块 — 基于检索结果调用 DeepSeek API 生成回答。
"""

import json
import logging
from typing import Optional

import httpx

from ..config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a research assistant specialized in statistical analysis and academic writing.
Answer the user's question based on the provided paper excerpts.

Guidelines:
- Answer in the same language as the user's question.
- Cite specific papers by title and section when using their content.
- If the provided excerpts don't contain enough information to answer, say so honestly.
- Be precise: quote key findings, equations, or statistics when relevant.
- Format mathematical expressions in LaTeX (inline $...$ or block $$...$$).
- Suggest follow-up questions that the user might ask if appropriate.

Provided paper excerpts (each with paper title, section, and text):
---
{context}
---

User question: {question}
"""


async def generate_answer(
    question: str,
    context_chunks: list[dict],
    conversation_history: Optional[list[dict]] = None,
    stream: bool = False,
):
    """
    基于检索到的上下文生成回答。

    参数:
        question: 用户问题
        context_chunks: [{"paper_title", "section_title", "section_category", "text", "authors"}, ...]
        conversation_history: [{"role": "user|assistant", "content": "..."}, ...]
        stream: 是否流式返回

    返回:
        如果 stream=False: str
        如果 stream=True: async generator yielding str chunks
    """
    if not LLM_API_KEY:
        raise ValueError("DEEPSEEK_API_KEY or OPENAI_API_KEY not set")

    # 构建上下文
    context_lines = []
    for i, chunk in enumerate(context_chunks, 1):
        title = chunk.get("paper_title", "Unknown")
        section = chunk.get("section_title", chunk.get("section_category", ""))
        authors = chunk.get("authors", [])
        author_str = ", ".join(authors) if authors else ""
        context_lines.append(
            f"[{i}] Paper: {title}\n"
            f"    Authors: {author_str}\n"
            f"    Section: {section}\n"
            f"    Text: {chunk.get('text', '')[:2000]}"
        )
    context = "\n\n".join(context_lines)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT.format(
            context=context, question=question
        )},
    ]

    if conversation_history:
        messages[1:1] = conversation_history
    messages.append({"role": "user", "content": question})

    async with httpx.AsyncClient(timeout=120.0) as client:
        if stream:
            return _stream_response(client, messages)
        else:
            return await _complete_response(client, messages)


async def _complete_response(client: httpx.AsyncClient, messages: list[dict]) -> str:
    """非流式调用."""
    response = await client.post(
        f"{LLM_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": LLM_MODEL,
            "messages": messages,
            "max_tokens": LLM_MAX_TOKENS,
            "temperature": LLM_TEMPERATURE,
        },
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]["content"]


async def _stream_response(client: httpx.AsyncClient, messages: list[dict]):
    """流式调用，yield 文本块."""
    async with client.stream(
        "POST",
        f"{LLM_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": LLM_MODEL,
            "messages": messages,
            "max_tokens": LLM_MAX_TOKENS,
            "temperature": LLM_TEMPERATURE,
            "stream": True,
        },
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
