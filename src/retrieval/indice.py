"""Tudo o que fala com o índice de checagens (ChromaDB).

- Embeddings: o mesmo modelo multilíngue na indexação e na busca.
- Coleção: uma por modelo de embedding, com distância de cosseno
  (similaridade = 1 - distância).
- Consultas: busca por frase e leitura dos trechos de uma checagem.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Sequence

from src.retrieval import config

_client = None
_model = None
_carga_modelo = threading.Lock()  # uma análise abandonada por timeout pode estar carregando ao mesmo tempo


# --- Coleção -----------------------------------------------------------------

def get_collection(*, create: bool = False, reset: bool = False):
    """Coleção do modelo de embedding atual.

    Sem create, levanta erro se ela não existir: índice ausente é uma falha do
    agente, e não "nenhuma checagem encontrada". Com reset, apaga e recria.
    """
    global _client
    if _client is None:
        import chromadb

        config.CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(config.CHROMA_PATH))
    name = config.collection_name()
    if reset:
        try:
            _client.delete_collection(name)
        except Exception:
            pass
    if create or reset:
        return _client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine", "embedding_model": config.EMBEDDING_MODEL},
            embedding_function=None,
        )
    return _client.get_collection(name=name, embedding_function=None)


# --- Embeddings ----------------------------------------------------------------

def get_embedding_model():
    """Carrega o modelo de embedding uma única vez por processo, mesmo com várias threads."""
    global _model
    if _model is None:
        with _carga_modelo:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                device = config.pick_device()
                modelo = SentenceTransformer(config.EMBEDDING_MODEL, device=device)
                if config.EMBEDDING_FP16 and device in {"cuda", "mps"}:
                    modelo = modelo.half()
                _model = modelo
    return _model


def _embed(texts: Sequence[str], kind: str) -> list[list[float]]:
    """kind = "query" (frases da notícia) ou "passage" (trechos das checagens)."""
    if not texts:
        return []
    modelo = get_embedding_model()
    # A família e5 exige prefixos; o BGE-M3 (padrão) não usa.
    prefix = f"{kind}: " if "e5" in config.EMBEDDING_MODEL.lower() else ""
    vectors = modelo.encode([prefix + t for t in texts], batch_size=config.BATCH_SIZE,
                            normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    return vectors.astype("float32").tolist()


def embed_passages(texts: Sequence[str]) -> list[list[float]]:
    return _embed(texts, "passage")


# --- Consultas -------------------------------------------------------------------

@dataclass
class Hit:
    """Um trecho de checagem recuperado para uma frase."""

    chunk_id: str
    text: str
    similarity: float
    metadata: dict[str, Any] = field(default_factory=dict)


def search(texts: Sequence[str], k: int | None = None) -> list[list[Hit]]:
    """Para cada frase, até k trechos, do mais para o menos similar (sem limiar)."""
    if not texts:
        return []
    collection = get_collection()
    if collection.count() == 0:
        return [[] for _ in texts]
    result = collection.query(
        query_embeddings=_embed(list(texts), "query"),
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
    result = get_collection().get(where={"source_url": {"$eq": source_url}}, include=["documents"])
    return [d for d in (result.get("documents") or []) if d]


def get_lead_text(source_url: str) -> str | None:
    """Primeiro trecho do texto de uma checagem (o parágrafo de abertura)."""
    result = get_collection().get(
        where={"$and": [{"source_url": {"$eq": source_url}}, {"chunk_index": {"$eq": 0}}]},
        include=["documents"],
    )
    documents = result.get("documents") or []
    return documents[0] if documents else None
