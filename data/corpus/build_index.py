"""Constrói o índice de checagens no ChromaDB.

Junta os metadados da API (factcheck_api.jsonl) com os textos completos
(articles.jsonl), divide cada checagem em trechos, calcula os embeddings e
grava na coleção do modelo de embedding atual (config.collection_name()).

Metadados de cada trecho: source_url, source_name, agency_verdict,
review_date, claim_reviewed, chunk_index, describes_rumor.
IDs determinísticos: rodar de novo atualiza em vez de duplicar.

Uso, a partir da raiz do repositório:
    python data/corpus/build_index.py
    python data/corpus/build_index.py --reset
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrieval import config  # noqa: E402
from src.retrieval.chunking import build_chunks  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def chunk_id(url: str, index: int) -> str:
    return f"{hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]}-{index:03d}"


def build_records(claims: list[dict], articles: list[dict]) -> list[dict]:
    """Um registro por trecho: id, texto e metadados (só str/int/bool, exigência do Chroma)."""
    meta_by_url = {c["source_url"]: c for c in claims}
    records = []
    for article in articles:
        url = article["source_url"]
        meta = meta_by_url.get(url, {})
        for i, chunk in enumerate(build_chunks(article.get("text", ""))):
            records.append(
                {
                    "id": chunk_id(url, i),
                    "text": chunk.text,
                    "metadata": {
                        "source_url": url,
                        "source_name": meta.get("source_name") or meta.get("publisher_site") or "",
                        "agency_verdict": meta.get("agency_verdict") or "",
                        "review_date": meta.get("review_date") or "",
                        "claim_reviewed": meta.get("claim_reviewed") or "",
                        "chunk_index": i,
                        "describes_rumor": chunk.describes_rumor,
                    },
                }
            )
    return records


def index_records(records: list[dict], reset: bool = False, batch_size: int = 64) -> int:
    from src.retrieval.chroma_client import get_collection, reset_collection
    from src.retrieval.embeddings import embed_passages

    collection = reset_collection() if reset else get_collection(create=True)
    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        collection.upsert(
            ids=[r["id"] for r in batch],
            documents=[r["text"] for r in batch],
            metadatas=[r["metadata"] for r in batch],
            embeddings=embed_passages([r["text"] for r in batch]),
        )
        print(f"  {min(start + batch_size, len(records))}/{len(records)} trechos indexados")
    return collection.count()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--claims", type=Path, default=config.RAW_DIR / "factcheck_api.jsonl")
    parser.add_argument("--articles", type=Path, default=config.RAW_DIR / "articles.jsonl")
    parser.add_argument("--reset", action="store_true", help="apaga a coleção antes de indexar")
    args = parser.parse_args()

    claims = load_jsonl(args.claims)
    articles = load_jsonl(args.articles)
    if not articles:
        sys.exit(f"Nada em {args.articles}. Rode antes fetch_articles.py.")

    records = build_records(claims, articles)
    rumor = sum(r["metadata"]["describes_rumor"] for r in records)
    no_verdict = sum(not r["metadata"]["agency_verdict"] for r in records)
    print(
        f"{len(articles)} checagens -> {len(records)} trechos "
        f"({rumor} marcados como 'descreve o boato', {no_verdict} sem veredito da agência)."
    )
    print(f"Modelo: {config.EMBEDDING_MODEL} | coleção: {config.collection_name()} | caminho: {config.CHROMA_PATH}")
    total = index_records(records, reset=args.reset)
    print(f"Coleção com {total} trechos.")


if __name__ == "__main__":
    main()
