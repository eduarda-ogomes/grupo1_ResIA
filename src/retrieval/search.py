"""Busca vetorial no índice de checagens."""

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
    """Para cada frase, devolve até k trechos, do mais para o menos similar.

    Não aplica limiar: o filtro por similaridade fica no agente, para que a
    avaliação possa medir Recall@k sobre a lista completa.
    """
    from src.retrieval.chroma_client import get_collection
    from src.retrieval.embeddings import embed_queries

    if not texts:
        return []
    k = k or config.TOP_K
    collection = get_collection()
    if collection.count() == 0:
        return [[] for _ in texts]

    query = {
        "query_embeddings": embed_queries(list(texts)),
        "n_results": min(k, collection.count()),
        "include": ["documents", "metadatas", "distances"],
    }
    if config.FILTER_RUMOR_CHUNKS:
        query["where"] = {"describes_rumor": False}
    result = collection.query(**query)

    hits: list[list[Hit]] = []
    for ids, docs, metas, dists in zip(
        result["ids"], result["documents"], result["metadatas"], result["distances"]
    ):
        hits.append(
            [
                Hit(chunk_id=i, text=d, similarity=1.0 - float(dist), metadata=dict(m or {}))
                for i, d, m, dist in zip(ids, docs, metas, dists)
            ]
        )
    return hits
