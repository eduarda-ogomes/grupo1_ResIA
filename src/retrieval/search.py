"""Consultas ao índice de checagens."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from src.retrieval import config


@dataclass
class Hit:
    """Um trecho de checagem recuperado para uma frase."""

    chunk_id: str
    text: str
    similarity: float
    metadata: dict[str, Any] = field(default_factory=dict)


def search(texts: Sequence[str], k: int | None = None) -> list[list[Hit]]:
    """Para cada frase, até k trechos, do mais para o menos similar (sem limiar)."""
    from src.retrieval.chroma_client import get_collection
    from src.retrieval.embeddings import embed_queries

    if not texts:
        return []
    collection = get_collection()
    if collection.count() == 0:
        return [[] for _ in texts]
    result = collection.query(
        query_embeddings=embed_queries(list(texts)),
        n_results=min(k or config.SEARCH_K, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    return [
        [Hit(i, d, 1.0 - float(dist), dict(m or {})) for i, d, m, dist in zip(ids, docs, metas, dists)]
        for ids, docs, metas, dists in zip(
            result["ids"], result["documents"], result["metadatas"], result["distances"]
        )
    ]


def get_checagem_texts(source_url: str) -> list[str]:
    """Todos os trechos indexados de uma checagem (título e texto)."""
    from src.retrieval.chroma_client import get_collection

    result = get_collection().get(where={"source_url": {"$eq": source_url}}, include=["documents"])
    return [d for d in (result.get("documents") or []) if d]


def get_lead_text(source_url: str) -> str | None:
    """Primeiro trecho do texto de uma checagem (o parágrafo de abertura)."""
    from src.retrieval.chroma_client import get_collection

    result = get_collection().get(
        where={"$and": [{"source_url": {"$eq": source_url}}, {"chunk_index": {"$eq": 0}}]},
        include=["documents"],
    )
    documents = result.get("documents") or []
    return documents[0] if documents else None
