"""Acesso ao índice de checagens no ChromaDB.

- Caminho relativo à raiz do repositório (não depende da pasta de onde se roda).
- Distância de cosseno: similaridade = 1 - distância.
- Uma coleção por modelo de embedding (config.collection_name).
- Os embeddings são sempre passados explicitamente (src/retrieval/embeddings.py).
"""

from __future__ import annotations

from src.retrieval import config

_client = None


def get_client():
    global _client
    if _client is None:
        import chromadb

        config.CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(config.CHROMA_PATH))
    return _client


def get_collection(name: str | None = None, *, create: bool = False):
    """Devolve a coleção do modelo de embedding atual.

    Com create=False, levanta erro se a coleção não existir: índice ausente é
    uma falha do agente, e não "nenhuma checagem encontrada".
    """
    client = get_client()
    name = name or config.collection_name()
    if create:
        return client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine", "embedding_model": config.EMBEDDING_MODEL},
            embedding_function=None,
        )
    return client.get_collection(name=name, embedding_function=None)


def reset_collection(name: str | None = None):
    client = get_client()
    name = name or config.collection_name()
    try:
        client.delete_collection(name)
    except Exception:
        pass
    return get_collection(name, create=True)
