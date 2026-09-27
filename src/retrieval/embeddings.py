"""Embeddings multilíngues usados na indexação e na busca.

O mesmo modelo precisa ser usado nos dois lados. Os embeddings são calculados
aqui (e não pela embedding_function do Chroma) para controlar dispositivo,
precisão e os prefixos exigidos pela família e5.
"""

from __future__ import annotations

from typing import Sequence

from src.retrieval import config

_model = None


def _uses_e5_prefixes(model_name: str) -> bool:
    return "e5" in model_name.lower()


def _prefix(kind: str) -> str:
    if not _uses_e5_prefixes(config.EMBEDDING_MODEL):
        return ""
    return "query: " if kind == "query" else "passage: "


def get_embedder():
    """Carrega o modelo uma única vez por processo."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        device = config.pick_device()
        _model = SentenceTransformer(config.EMBEDDING_MODEL, device=device)
        if config.EMBEDDING_FP16 and device in {"cuda", "mps"}:
            _model = _model.half()
    return _model


def _encode(texts: Sequence[str], kind: str) -> list[list[float]]:
    if not texts:
        return []
    prefix = _prefix(kind)
    vectors = get_embedder().encode(
        [prefix + t for t in texts],
        batch_size=config.BATCH_SIZE,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vectors.astype("float32").tolist()


def embed_queries(texts: Sequence[str]) -> list[list[float]]:
    """Frases da notícia."""
    return _encode(texts, "query")


def embed_passages(texts: Sequence[str]) -> list[list[float]]:
    """Trechos das checagens."""
    return _encode(texts, "passage")
