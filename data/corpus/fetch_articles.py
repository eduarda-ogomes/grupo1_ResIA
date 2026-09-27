"""Baixa o texto completo de cada checagem coletada pela API.

Lê data/corpus/raw/factcheck_api.jsonl, baixa cada URL com trafilatura e grava
data/corpus/raw/articles.jsonl. Pode ser interrompido e retomado: URLs já
baixadas são puladas. Falhas vão para data/corpus/raw/fetch_failures.jsonl.

Uso, a partir da raiz do repositório:
    python data/corpus/fetch_articles.py
    python data/corpus/fetch_articles.py --limit 50 --delay 2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrieval import config  # noqa: E402


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


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
    args = parser.parse_args()

    claims = load_jsonl(args.claims)
    if not claims:
        sys.exit(f"Nada em {args.claims}. Rode antes collect_factcheck_api.py.")

    done = {a["source_url"] for a in load_jsonl(args.out)}
    pending = []
    for claim in claims:
        url = claim["source_url"]
        if url not in done and url not in {c["source_url"] for c in pending}:
            pending.append(claim)
    if args.limit:
        pending = pending[: args.limit]
    print(f"{len(done)} já baixadas; {len(pending)} pendentes.")

    ok = failed = 0
    with args.out.open("a", encoding="utf-8") as out, args.failures.open("a", encoding="utf-8") as fail:
        for i, claim in enumerate(pending, 1):
            url = claim["source_url"]
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
            except Exception as exc:
                fail.write(json.dumps({"source_url": url, "error": str(exc)}, ensure_ascii=False) + "\n")
                failed += 1
            if i % 25 == 0:
                print(f"  {i}/{len(pending)} (ok={ok}, falhas={failed})")
            time.sleep(args.delay)

    print(f"Concluído: {ok} baixadas, {failed} falhas (ver {args.failures}).")


if __name__ == "__main__":
    main()
