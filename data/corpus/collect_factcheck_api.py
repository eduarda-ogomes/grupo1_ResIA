"""Coleta de checagens pela Google Fact Check Tools API (claims:search).

Para cada site de agência, lista as checagens em português e grava uma linha
por checagem (URL única) em data/corpus/raw/factcheck_api.jsonl.

A API devolve erro 503 depois de ~500-600 resultados de uma mesma busca
(observado em 26-27/09/2026). Para contornar, cada site é coletado em várias
buscas menores: uma sem palavra-chave e uma para cada palavra de QUERIES.
Uma busca que falha não interrompe as outras, e rodar de novo só acrescenta
o que ainda não foi coletado.

Requer uma chave de API do Google Cloud com a Fact Check Tools API ativada:
    $env:FACTCHECK_API_KEY = "..."   (Windows, PowerShell)
    export FACTCHECK_API_KEY=...     (macOS/Linux)

Uso, a partir da raiz do repositório:
    python data/corpus/collect_factcheck_api.py
    python data/corpus/collect_factcheck_api.py --sites checamos.afp.com --delay 3
    python data/corpus/collect_factcheck_api.py --queries vacina eleição --max-age-days 0
    python data/corpus/collect_factcheck_api.py --sem-queries

Documentação: https://developers.google.com/fact-check/tools/api/reference/rest/v1alpha1/claims/search
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrieval import config  # noqa: E402

ENDPOINT = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

# Domínios como a API os registra (conferido em 27/09/2026 listando os
# publishers de uma busca). A Lupa não apareceu na API com nenhum domínio
# testado (agencialupa.org, lupa.uol.com.br); ver documento de decisões.
DEFAULT_SITES = [
    "aosfatos.org",            # Aos Fatos
    "projetocomprova.com.br",  # Projeto Comprova
    "checamos.afp.com",        # AFP Checamos
    "estadao.com.br",          # Estadão Verifica
    "noticias.uol.com.br",     # UOL Confere
]

# Palavras-chave para dividir a coleta em buscas menores. Temas recorrentes de
# desinformação no Brasil; a lista pode ser ampliada à vontade.
QUERIES = [
    "Lula", "Bolsonaro", "Moraes", "STF", "TSE", "eleição", "urna", "governo",
    "Congresso", "PIX", "imposto", "INSS", "aposentadoria", "Bolsa Família", "salário",
    "vacina", "covid", "dengue", "saúde", "remédio", "câncer",
    "vídeo", "foto", "inteligência artificial", "golpe", "polícia", "facção",
    "enchente", "clima", "Amazônia", "Israel", "Trump", "Estados Unidos", "China",
    "igreja", "escola", "morte", "prisão",
    # Ampliação de 07/10/2026: mais pessoas, órgãos e temas recorrentes.
    "Lewandowski", "Haddad", "Tarcísio", "Marçal", "Janja", "Michelle", "Dino", "Barroso",
    "Anvisa", "SUS", "Petrobras", "Correios", "Receita Federal", "FGTS", "CNH", "Banco Central",
    "Ucrânia", "Rússia", "Venezuela", "Gaza", "Argentina", "Milei",
    "aborto", "LGBT", "indígena", "MST", "agro", "queimada", "seca", "terremoto",
    "WhatsApp", "deepfake", "celebridade", "futebol", "papa", "militares", "ditadura",
    "gasolina", "inflação", "dólar", "auxílio", "criança", "mulher", "armas", "drogas",
]


def fetch_page(params: dict, retries: int = 4) -> dict:
    url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:200]
            if exc.code in {429, 500, 502, 503} and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"HTTP {exc.code}: {' '.join(body.split())}") from exc
        except urllib.error.URLError:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise
    return {}


def iter_reviews(site: str, api_key: str, max_age_days: int | None, page_size: int,
                 delay: float, query: str | None = None):
    params = {
        "key": api_key,
        "languageCode": "pt",
        "reviewPublisherSiteFilter": site,
        "pageSize": page_size,
    }
    if query:
        params["query"] = query
    if max_age_days:
        params["maxAgeDays"] = max_age_days
    token = None
    while True:
        if token:
            params["pageToken"] = token
        data = fetch_page(params)
        for claim in data.get("claims", []):
            for review in claim.get("claimReview", []):
                yield {
                    "source_url": review.get("url", ""),
                    "source_name": (review.get("publisher") or {}).get("name", ""),
                    "publisher_site": (review.get("publisher") or {}).get("site", site),
                    "review_title": review.get("title", ""),
                    "review_date": review.get("reviewDate", ""),
                    "agency_verdict": review.get("textualRating", ""),
                    "language": review.get("languageCode", ""),
                    "claim_reviewed": claim.get("text", ""),
                    "claimant": claim.get("claimant", ""),
                    "claim_date": claim.get("claimDate", ""),
                    "query_site": site,
                    "query": query or "",
                }
        token = data.get("nextPageToken")
        if not token:
            break
        time.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sites", nargs="+", default=DEFAULT_SITES)
    parser.add_argument("--queries", nargs="+", default=QUERIES, help="palavras-chave (padrão: lista QUERIES)")
    parser.add_argument("--sem-queries", action="store_true", help="só a busca sem palavra-chave")
    parser.add_argument("--api-key", default=os.getenv("FACTCHECK_API_KEY"))
    parser.add_argument("--max-age-days", type=int, default=730, help="0 = sem limite (padrão: 24 meses)")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--delay", type=float, default=1.0, help="pausa entre páginas e buscas, em segundos")
    parser.add_argument("--out", type=Path, default=config.RAW_DIR / "factcheck_api.jsonl")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Defina FACTCHECK_API_KEY ou passe --api-key.")

    queries: list[str | None] = [None] + ([] if args.sem_queries else list(args.queries))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    if args.out.exists():
        with args.out.open(encoding="utf-8") as f:
            seen = {json.loads(line)["source_url"] for line in f if line.strip()}
        print(f"{len(seen)} checagens já coletadas em {args.out}; só as novas serão adicionadas.")

    with args.out.open("a", encoding="utf-8") as out:
        for site in args.sites:
            site_new = site_total = errors = 0
            for query in queries:
                new = total = 0
                try:
                    for review in iter_reviews(site, args.api_key, args.max_age_days or None,
                                               args.page_size, args.delay, query):
                        total += 1
                        url = review["source_url"].strip()
                        if not url or url in seen:
                            continue
                        seen.add(url)
                        out.write(json.dumps(review, ensure_ascii=False) + "\n")
                        new += 1
                except Exception as exc:  # uma busca com erro não interrompe as outras
                    errors += 1
                    print(f"  [{site}] busca {query or '(sem palavra-chave)'!r}: erro depois de {total} "
                          f"resultados ({str(exc)[:80]})")
                out.flush()
                site_new += new
                site_total += total
                if new:
                    print(f"  [{site}] busca {query or '(sem palavra-chave)'!r}: {total} resultados, {new} novos")
                time.sleep(args.delay)
            print(f"[{site}] {site_total} resultados em {len(queries)} buscas, {site_new} checagens novas, "
                  f"{errors} buscas com erro")

    print(f"Total de URLs únicas em {args.out}: {len(seen)}")


if __name__ == "__main__":
    main()
