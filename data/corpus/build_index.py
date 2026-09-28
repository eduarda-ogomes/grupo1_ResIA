"""Constrói o índice de checagens no ChromaDB.

Junta os metadados da API (factcheck_api.jsonl) com os textos completos
(articles.jsonl), divide cada checagem em trechos, calcula os embeddings e
grava na coleção do modelo de embedding atual (config.collection_name()).

Cada checagem ganha também um trecho com o TÍTULO (chunk_kind "titulo",
chunk_index -1), mesmo quando o texto não pôde ser baixado. O título é a
conclusão da agência, escrita por ela; assim as checagens da AFP Checamos (que
recusa o download) entram no índice, e o modo "alegacao" usa o título como
excerpt.

Metadados de cada trecho: source_url, source_name, agency_verdict,
review_date, claim_reviewed, review_title, chunk_index, chunk_kind.
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
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrieval import config  # noqa: E402
from src.retrieval.chunking import build_chunks  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def chunk_id(url: str, index: int | str) -> str:
    """"<sha1 da URL>-000", "-001"...; o trecho de título usa o sufixo "tit"."""
    suffix = index if isinstance(index, str) else f"{index:03d}"
    return f"{hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]}-{suffix}"


def build_records(claims: list[dict], articles: list[dict]) -> list[dict]:
    """Um registro por trecho: id, texto e metadados (só str/int/bool, exigência do Chroma).

    Toda checagem com título gera um trecho de título; as que têm texto baixado
    geram também os trechos do texto.
    """
    meta_by_url: dict[str, dict] = {}
    for claim in claims:
        meta_by_url.setdefault(claim["source_url"], claim)
    text_by_url = {a["source_url"]: a.get("text", "") for a in articles}

    records = []
    for url in dict.fromkeys([*meta_by_url, *text_by_url]):
        meta = meta_by_url.get(url, {})
        title = " ".join(str(meta.get("review_title") or "").split())
        base = {
            "source_url": url,
            "source_name": meta.get("source_name") or meta.get("publisher_site") or "",
            "agency_verdict": meta.get("agency_verdict") or "",
            "review_date": meta.get("review_date") or "",
            "claim_reviewed": meta.get("claim_reviewed") or "",
            "review_title": title,
        }
        if title:
            records.append({
                "id": chunk_id(url, "tit"),
                "text": title,
                "metadata": {**base, "chunk_index": -1, "chunk_kind": "titulo"},
            })
        for i, chunk in enumerate(build_chunks(text_by_url.get(url, ""))):
            records.append({
                "id": chunk_id(url, i),
                "text": chunk,
                "metadata": {**base, "chunk_index": i, "chunk_kind": "texto"},
            })
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
    if not claims and not articles:
        sys.exit(f"Nada em {args.claims} nem em {args.articles}. Rode antes collect_factcheck_api.py.")

    records = build_records(claims, articles)
    urls = {r["metadata"]["source_url"] for r in records}
    with_text = {r["metadata"]["source_url"] for r in records if r["metadata"]["chunk_kind"] == "texto"}
    no_verdict = len({r["metadata"]["source_url"] for r in records if not r["metadata"]["agency_verdict"]})
    by_agency = Counter(r["metadata"]["source_name"] for r in records if r["metadata"]["chunk_kind"] == "titulo")
    print(
        f"{len(urls)} checagens ({len(with_text)} com texto, {len(urls) - len(with_text)} só com título) "
        f"-> {len(records)} trechos ({no_verdict} checagens sem veredito da agência)."
    )
    print("Checagens por agência:", dict(by_agency.most_common()))
    print(f"Modelo: {config.EMBEDDING_MODEL} | coleção: {config.collection_name()} | caminho: {config.CHROMA_PATH}")
    total = index_records(records, reset=args.reset)
    print(f"Coleção com {total} trechos.")


if __name__ == "__main__":
    main()
