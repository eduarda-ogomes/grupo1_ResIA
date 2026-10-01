"""Baixa o texto completo de cada checagem coletada pela API.

Lê data/corpus/raw/factcheck_api.jsonl, baixa cada URL com trafilatura e grava
data/corpus/raw/articles.jsonl. Pode ser interrompido e retomado: URLs já
baixadas são puladas. Falhas vão para data/corpus/raw/fetch_failures.jsonl.

Se um site falhar muitas vezes seguidas (padrão: 20), o script desiste das
URLs restantes daquele site nesta execução. Observado em 27/09/2026: a AFP
Checamos recusa o download (515 de 515 falhas). As checagens desse site
continuam no índice pelo título que a API fornece (ver build_index.py).

Uso, a partir da raiz do repositório:
    python data/corpus/fetch_articles.py
    python data/corpus/fetch_articles.py --limit 50 --delay 2
    python data/corpus/fetch_articles.py --pular-sites checamos.afp.com
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrieval import config  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _site(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def fetch_text(url: str, retries: int) -> tuple[str, str]:
    import trafilatura

    last_error = "sem conteúdo"
    for attempt in range(1, retries + 1):
        html = trafilatura.fetch_url(url)
        if html:
            extracted = trafilatura.extract(
                html,
                output_format="json",
                include_comments=False,
                include_tables=False,
                favor_precision=True,
            )
            if extracted:
                data = json.loads(extracted)
                if data.get("text"):
                    return data["text"], data.get("title") or ""
            last_error = "extração vazia"
        else:
            last_error = "download falhou"
        time.sleep(2 ** attempt)
    raise RuntimeError(last_error)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--claims", type=Path, default=config.RAW_DIR / "factcheck_api.jsonl")
    parser.add_argument("--out", type=Path, default=config.RAW_DIR / "articles.jsonl")
    parser.add_argument("--failures", type=Path, default=config.RAW_DIR / "fetch_failures.jsonl")
    parser.add_argument("--delay", type=float, default=1.0, help="pausa entre downloads, em segundos")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0, help="0 = todas")
    parser.add_argument("--max-falhas-seguidas", type=int, default=20,
                        help="desiste de um site depois de N falhas seguidas (0 = nunca)")
    parser.add_argument("--pular-sites", nargs="+", default=[], help="domínios a não tentar baixar")
    args = parser.parse_args()

    claims = load_jsonl(args.claims)
    if not claims:
        sys.exit(f"Nada em {args.claims}. Rode antes collect_factcheck_api.py.")

    done = {a["source_url"] for a in load_jsonl(args.out)}
    skip_sites = set(args.pular_sites)
    pending, queued = [], set()
    for claim in claims:
        url = claim["source_url"]
        if url in done or url in queued or _site(url) in skip_sites:
            continue
        queued.add(url)
        pending.append(claim)
    if args.limit:
        pending = pending[: args.limit]
    print(f"{len(done)} já baixadas; {len(pending)} pendentes.")

    ok = failed = skipped = 0
    streak: Counter = Counter()      # falhas seguidas por site
    given_up: set[str] = set()
    with args.out.open("a", encoding="utf-8") as out, args.failures.open("a", encoding="utf-8") as fail:
        for i, claim in enumerate(pending, 1):
            url = claim["source_url"]
            site = _site(url)
            if site in given_up:
                skipped += 1
                continue
            try:
                text, title = fetch_text(url, args.retries)
                out.write(
                    json.dumps(
                        {
                            "source_url": url,
                            "title": title,
                            "text": text,
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                out.flush()
                ok += 1
                streak[site] = 0
            except Exception as exc:
                fail.write(json.dumps({"source_url": url, "error": str(exc)}, ensure_ascii=False) + "\n")
                fail.flush()
                failed += 1
                streak[site] += 1
                if args.max_falhas_seguidas and streak[site] >= args.max_falhas_seguidas:
                    given_up.add(site)
                    print(f"  [{site}] {streak[site]} falhas seguidas: desistindo das URLs restantes deste site.")
            if i % 25 == 0:
                print(f"  {i}/{len(pending)} (ok={ok}, falhas={failed}, puladas={skipped})")
            if site not in given_up:
                time.sleep(args.delay)

    if given_up:
        print(f"Sites abandonados nesta execução: {', '.join(sorted(given_up))} ({skipped} URLs puladas).")
    print(f"Concluído: {ok} baixadas, {failed} falhas (ver {args.failures}).")


if __name__ == "__main__":
    main()
