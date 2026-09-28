"""Divisão do texto das checagens em trechos para o índice.

Parágrafos consecutivos são agrupados até CHUNK_MAX_CHARS caracteres, com
sobreposição de CHUNK_OVERLAP_PARAGRAPHS parágrafo; parágrafos muito curtos
(menus, legendas) são descartados.
"""

from __future__ import annotations

import re

from src.retrieval import config


def split_paragraphs(text: str, min_chars: int | None = None) -> list[str]:
    min_chars = config.MIN_PARAGRAPH_CHARS if min_chars is None else min_chars
    paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n+", text or "")]
    return [p for p in paragraphs if len(p) >= min_chars]


def build_chunks(text: str, max_chars: int | None = None, overlap: int | None = None,
                 min_chars: int | None = None) -> list[str]:
    max_chars = config.CHUNK_MAX_CHARS if max_chars is None else max_chars
    overlap = config.CHUNK_OVERLAP_PARAGRAPHS if overlap is None else overlap

    chunks: list[str] = []
    current: list[str] = []
    for paragraph in split_paragraphs(text, min_chars):
        if current and len("\n".join(current + [paragraph])) > max_chars:
            chunks.append("\n".join(current))
            carry = current[-overlap:] if overlap else []
            current = carry if len("\n".join(carry + [paragraph])) <= max_chars else []
        current.append(paragraph)
    if current:
        chunks.append("\n".join(current))
    return chunks
