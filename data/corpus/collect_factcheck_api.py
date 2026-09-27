"""Coleta de checagens pela Google Fact Check Tools API (claims:search).

Para cada site de agência, lista as checagens em português, seguindo a
paginação, e grava uma linha por checagem (URL única) em
data/corpus/raw/factcheck_api.jsonl.

Requer uma chave de API do Google Cloud com a Fact Check Tools API ativada:
    $env:FACTCHECK_API_KEY = "..."   (Windows, PowerShell)
    export FACTCHECK_API_KEY=...     (macOS/Linux)

Uso, a partir da raiz do repositório:
    python data/corpus/collect_factcheck_api.py
    python data/corpus/collect_factcheck_api.py --sites aosfatos.org --max-age-days 730

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

# Confira quais domínios a API reconhece: o script mostra quantas checagens
# cada site devolveu. A Lupa já publicou em mais de um domínio.
DEFAULT_SITES = [
    "aosfatos.org",
    "agencialupa.org",
    "lupa.uol.com.br",
    "projetocomprova.com.br",
]


def fetch_page(params: dict, retries: int = 3) -> dict:
    url = f"{ENDPOINT}?{urllib.parse.urlencode(params)}"
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:300]
            if exc.code in {429, 500, 502, 503} and attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError:
            if attempt < retries:
                time.sleep(2 ** attempt)
                continue
            raise
    return {}


def iter_reviews(site: str, api_key: str, max_age_days: int | None, page_size: int, delay: float):
    params = {
        "key": api_key,
        "languageCode": "pt",
        "reviewPublisherSiteFilter": site,
        "pageSize": page_size,
    }
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
                }
        token = data.get("nextPageToken")
        if not token:
            break
        time.sleep(delay)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sites", nargs="+", default=DEFAULT_SITES)
    parser.add_argument("--api-key", default=os.getenv("FACTCHECK_API_KEY"))
    parser.add_argument("--max-age-days", type=int, default=730, help="0 = sem limite (padrão: 24 meses)")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--delay", type=float, default=0.5, help="pausa entre páginas, em segundos")
    parser.add_argument("--out", type=Path, default=config.RAW_DIR / "factcheck_api.jsonl")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("Defina FACTCHECK_API_KEY ou passe --api-key.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    if args.out.exists():
        with args.out.open(encoding="utf-8") as f:
            seen = {json.loads(line)["source_url"] for line in f if line.strip()}
        print(f"{len(seen)} checagens já coletadas em {args.out}; só as novas serão adicionadas.")

    with args.out.open("a", encoding="utf-8") as out:
        for site in args.sites:
            new = total = 0
            try:
                for review in iter_reviews(site, args.api_key, args.max_age_days or None, args.page_size, args.delay):
                    total += 1
                    url = review["source_url"].strip()
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    out.write(json.dumps(review, ensure_ascii=False) + "\n")
                    new += 1
            except Exception as exc:  # um site com erro não interrompe os outros
                print(f"[{site}] erro: {exc}")
            print(f"[{site}] {total} checagens devolvidas pela API, {new} novas")

    print(f"Total de URLs únicas em {args.out}: {len(seen)}")


if __name__ == "__main__":
    main()
