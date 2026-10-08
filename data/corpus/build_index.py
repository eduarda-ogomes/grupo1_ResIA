"""Constrói o índice de checagens no ChromaDB.

Junta os metadados da API (factcheck_api.jsonl) com os textos completos
(articles.jsonl), divide cada checagem em trechos (parágrafos agrupados até
800 caracteres, com sobreposição de 1 parágrafo), calcula os embeddings e grava
na coleção do modelo de embedding atual (config.collection_name()).

Cada checagem ganha também um trecho com o TÍTULO (chunk_kind "titulo",
chunk_index -1), mesmo quando o texto não pôde ser baixado. O título é a
conclusão da agência, escrita por ela; assim as checagens da AFP Checamos (que
recusa o download) entram no índice, e o agente usa o título como excerpt.

Metadados de cada trecho: source_url, source_name, agency_verdict,
review_date, claim_reviewed, review_title, chunk_index, chunk_kind.
IDs determinísticos: rodar de novo atualiza em vez de duplicar.

Também grava data/corpus/nomes_proprios.txt: as palavras que o corpus usa como
nome próprio (com maiúscula no meio de uma alegação ou título). O agente usa a
lista para decidir se a primeira palavra de uma frase é nome. O arquivo é
versionado no Git; regenere-o sempre que o corpus mudar.

Uso, a partir da raiz do repositório:
    python data/corpus/build_index.py
    python data/corpus/build_index.py --reset
    python data/corpus/build_index.py --so-nomes      (só regenera nomes_proprios.txt, sem índice)
    python data/corpus/build_index.py --apenas-novos  (só calcula embeddings dos trechos que faltam)

Fontes: factcheck_api.jsonl + articles.jsonl (Fact Check Tools API) e, se existirem,
factckbr_claims.jsonl + factckbr_articles.jsonl (FACTCK.BR, gerados pelo
import_factckbr.py). O metadado "corpus" diz de qual fonte veio cada trecho.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrieval import config  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --- Divisão do texto em trechos --------------------------------------------------
# Parágrafos consecutivos agrupados até CHUNK_MAX_CHARS, com sobreposição de
# CHUNK_OVERLAP_PARAGRAPHS parágrafo; parágrafos curtos (menus, legendas) descartados.

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


def chunk_id(url: str, index: int | str) -> str:
    """"<sha1 da URL>-000", "-001"...; o trecho de título usa o sufixo "tit"."""
    suffix = index if isinstance(index, str) else f"{index:03d}"
    return f"{hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]}-{suffix}"


def source_name_with_year(name: str, review_date: str) -> str:
    """Acrescenta o ano ao nome da agência quando a checagem é anterior a SOURCE_YEAR_BEFORE.

    Nome que já traz o ano (o FACTCK.BR, "Agência Lupa (2018)") e checagem sem data ficam como estão.
    """
    m = re.match(r"(\d{4})", review_date or "")
    if not name or not m or name.endswith(")") or int(m.group(1)) >= config.SOURCE_YEAR_BEFORE:
        return name
    return f"{name} ({m.group(1)})"


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
            "source_name": source_name_with_year(meta.get("source_name") or meta.get("publisher_site") or "",
                                                 meta.get("review_date") or ""),
            "agency_verdict": meta.get("agency_verdict") or "",
            "review_date": meta.get("review_date") or "",
            "claim_reviewed": meta.get("claim_reviewed") or "",
            "review_title": title,
            "corpus": meta.get("corpus") or "factcheck_api",
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


def write_name_vocabulary(claims: list[dict], path: Path | None = None) -> int:
    """Grava o vocabulário de nomes próprios das alegações e títulos (uma palavra por linha)."""
    from src.retrieval.etapa2 import NAME_VOCABULARY_PATH, build_name_vocabulary

    path = path or NAME_VOCABULARY_PATH
    texts = [t for c in claims for t in (c.get("claim_reviewed"), c.get("review_title")) if t]
    vocabulary = sorted(build_name_vocabulary(texts))
    path.write_text("\n".join(vocabulary) + "\n", encoding="utf-8")
    return len(vocabulary)


def only_new(records: list[dict], existing_ids: set[str]) -> list[dict]:
    """Trechos cujo id ainda não está no índice (os ids são determinísticos)."""
    return [r for r in records if r["id"] not in existing_ids]


def index_records(records: list[dict], reset: bool = False, batch_size: int = 64,
                  apenas_novos: bool = False) -> int:
    from src.retrieval.indice import embed_passages, get_collection

    collection = get_collection(create=True, reset=reset)
    if apenas_novos and not reset:
        existing = set(collection.get(include=[])["ids"])
        records = only_new(records, existing)
        print(f"  {len(existing)} trechos já no índice; {len(records)} novos para indexar.")
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
    parser.add_argument("--factckbr-claims", type=Path, default=config.RAW_DIR / "factckbr_claims.jsonl")
    parser.add_argument("--factckbr-articles", type=Path, default=config.RAW_DIR / "factckbr_articles.jsonl")
    parser.add_argument("--sem-factckbr", action="store_true", help="não inclui o FACTCK.BR, mesmo que exista")
    parser.add_argument("--apenas-novos", action="store_true",
                        help="só calcula embeddings dos trechos que ainda não estão no índice")
    parser.add_argument("--so-nomes", action="store_true",
                        help="só regenera data/corpus/nomes_proprios.txt, sem mexer no índice")
    args = parser.parse_args()

    claims = load_jsonl(args.claims)
    articles = load_jsonl(args.articles)
    if not args.sem_factckbr:
        fk_claims, fk_articles = load_jsonl(args.factckbr_claims), load_jsonl(args.factckbr_articles)
        if fk_claims:
            print(f"FACTCK.BR: {len(fk_claims)} checagens ({len(fk_articles)} com texto).")
        claims, articles = claims + fk_claims, articles + fk_articles
    if not claims and not articles:
        sys.exit(f"Nada em {args.claims} nem em {args.articles}. Rode antes collect_factcheck_api.py.")

    n_nomes = write_name_vocabulary(claims)
    print(f"Vocabulário de nomes próprios: {n_nomes} palavras em data/corpus/nomes_proprios.txt")
    if args.so_nomes:
        return

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
    total = index_records(records, reset=args.reset, apenas_novos=args.apenas_novos)
    print(f"Coleção com {total} trechos.")


if __name__ == "__main__":
    main()
