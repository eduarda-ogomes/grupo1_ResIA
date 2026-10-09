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
IDs determinísticos: rodar de novo atualiza em vez de duplicar. Variantes de URL da mesma
página (UOL: .htm, .ghtm, .amp.htm) viram uma checagem só, e os trechos das que saem são
apagados do índice, como os dos domínios excluídos (config.DOMINIOS_EXCLUIDOS).

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
import_factckbr.py) e lupa_claims.jsonl + lupa_articles.jsonl (Agência Lupa, gerados
pelo import_lupa.py). O metadado "corpus" diz de qual fonte veio cada trecho.
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


def separar_excluidas(claims: list[dict], articles: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """Tira as checagens de domínios excluídos (config.DOMINIOS_EXCLUIDOS) e devolve as URLs delas."""
    excluidas = [r["source_url"] for r in [*claims, *articles] if config.url_excluida(r["source_url"])]
    claims = [c for c in claims if not config.url_excluida(c["source_url"])]
    articles = [a for a in articles if not config.url_excluida(a["source_url"])]
    return claims, articles, list(dict.fromkeys(excluidas))


# O UOL publica a mesma checagem em até três endereços (".htm", ".ghtm" e ".amp.htm"). Cada um
# virava uma checagem e ocupava uma vaga do top 5. Fica uma por página, nesta ordem de preferência.
_VARIANTE = re.compile(r"(\.amp)?\.g?htm$")
_PREFERENCIA = (".amp.htm", ".ghtm")   # sufixos menos preferidos; ".htm" simples vence


def url_canonica(url: str) -> str:
    """Endereço sem query, barra final e sufixo de variante (".htm", ".ghtm", ".amp.htm")."""
    return _VARIANTE.sub("", url.split("?")[0].strip().rstrip("/"))


def _ordem_variante(url: str) -> int:
    u = url.split("?")[0].rstrip("/")
    return next((i + 1 for i, s in enumerate(reversed(_PREFERENCIA)) if u.endswith(s)), 0)


def unificar_variantes(claims: list[dict], articles: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """Uma checagem por página: junta as variantes de URL e devolve as URLs que saem.

    Fica a variante preferida (.htm > .ghtm > .amp.htm); campos vazios dela são completados com
    os das outras variantes, e o texto baixado por outra variante passa para ela. A mesma URL vinda
    de duas fontes (API e FACTCK.BR) fica como antes: vale o primeiro registro, sem mistura.
    """
    grupos: dict[str, list[dict]] = {}
    for c in claims:
        grupos.setdefault(url_canonica(c["source_url"]), []).append(c)
    texto_por_url = {a["source_url"]: a for a in articles}

    claims_ok, removidas, nova_url = [], [], {}
    for grupo in grupos.values():
        grupo = sorted(grupo, key=lambda c: _ordem_variante(c["source_url"]))
        fica = dict(grupo[0])
        for outra in grupo[1:]:
            if outra["source_url"] == fica["source_url"]:
                continue   # mesma URL em duas fontes: vale a primeira (build_records fazia o mesmo)
            for campo, valor in outra.items():
                if campo in ("corpus", "url_original"):
                    continue   # dizem de onde veio o registro; não passam para outro
                if valor and not fica.get(campo):
                    fica[campo] = valor
            removidas.append(outra["source_url"])
            nova_url[outra["source_url"]] = fica["source_url"]
        claims_ok.append(fica)

    # Textos da mesma URL passam como estão (build_records usa o último, como antes); só o texto
    # de uma variante que sai muda de URL, e só se a que fica não tiver texto próprio.
    articles_ok, movidos = [], set()
    for a in articles:
        url = nova_url.get(a["source_url"], a["source_url"])
        if url != a["source_url"]:
            if url in texto_por_url or url in movidos:
                continue
            movidos.add(url)
        articles_ok.append({**a, "source_url": url})
    return claims_ok, articles_ok, list(dict.fromkeys(removidas))


def remove_urls(urls: list[str], batch_size: int = 200) -> None:
    """Apaga do índice os trechos dessas URLs (os que já tinham sido indexados)."""
    from src.retrieval.indice import get_collection

    collection = get_collection(create=True)
    antes = collection.count()
    for start in range(0, len(urls), batch_size):
        collection.delete(where={"source_url": {"$in": urls[start : start + batch_size]}})
    if antes - collection.count():
        print(f"  {antes - collection.count()} trechos de domínios excluídos e de variantes de URL apagados do índice.")


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
    parser.add_argument("--lupa-claims", type=Path, default=config.RAW_DIR / "lupa_claims.jsonl")
    parser.add_argument("--lupa-articles", type=Path, default=config.RAW_DIR / "lupa_articles.jsonl")
    parser.add_argument("--sem-lupa", action="store_true", help="não inclui a Lupa (import_lupa.py), mesmo que exista")
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
    if not args.sem_lupa:
        lp_claims, lp_articles = load_jsonl(args.lupa_claims), load_jsonl(args.lupa_articles)
        if lp_claims:
            print(f"Lupa: {len(lp_claims)} checagens ({len(lp_articles)} com texto).")
        claims, articles = claims + lp_claims, articles + lp_articles
    if not claims and not articles:
        sys.exit(f"Nada em {args.claims} nem em {args.articles}. Rode antes collect_factcheck_api.py.")
    claims, articles, excluidas = separar_excluidas(claims, articles)
    if excluidas:
        print(f"{len(excluidas)} checagens de domínios excluídos ({', '.join(config.DOMINIOS_EXCLUIDOS)}) ficam fora.")
    claims, articles, variantes = unificar_variantes(claims, articles)
    if variantes:
        print(f"{len(variantes)} variantes de URL da mesma página (.ghtm, .amp.htm) unificadas.")
    excluidas += variantes

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
    if excluidas and not args.reset:
        remove_urls(excluidas)
    total = index_records(records, reset=args.reset, apenas_novos=args.apenas_novos)
    print(f"Coleção com {total} trechos.")


if __name__ == "__main__":
    main()
