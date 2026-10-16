"""Importa as checagens da Agência Lupa direto do site, pelo sitemap.

A Lupa não aparece na Fact Check Tools API: as páginas dela não têm a marcação
ClaimReview. Até aqui, só as checagens de 2018–2019 entravam, pelo FACTCK.BR.

Como funciona:
1. Lê os sitemaps de posts (robots.txt da Lupa os declara e permite o acesso).
2. Escolhe as páginas que são checagens pelo endereço: as seções /verificacao/,
   /checagem/ e /eleicoes/, e na seção antiga /jornalismo/ os endereços com cara
   de checagem ("verificamos-...", "e-falso-que-...", "e-verdade-que-...").
3. Baixa cada página (pausa entre downloads; desiste depois de N falhas seguidas,
   sem contornar bloqueio, ADR 2) e extrai título e texto com trafilatura.
4. A página não traz rótulo estruturado nem a alegação separada. Os dois saem do
   título, quando ele segue o padrão da Lupa "É <rótulo> que <alegação>":
   "É falso que OMS mudou a classificação de jovens" -> veredito "Falso",
   alegação "OMS mudou a classificação de jovens". O agente precisa da alegação
   (evidence.py descarta checagem sem claim_reviewed, e o NLI compara a frase com
   ela). Título fora do padrão ("É golpe mensagem que...") fica de fora.

Grava, no formato que o build_index.py lê (como o FACTCK.BR):
    data/corpus/raw/lupa_claims.jsonl      checagens aceitas
    data/corpus/raw/lupa_articles.jsonl    textos das aceitas
    data/corpus/raw/lupa_descartes.jsonl   páginas baixadas e descartadas, com o motivo
    data/corpus/raw/lupa_falhas.jsonl      downloads que falharam (tentados de novo na próxima vez)

Pode ser interrompido e retomado: páginas já aceitas ou descartadas são puladas, e
as do FACTCK.BR também (mesma URL).

Uso, a partir da raiz do repositório:
    python data/corpus/import_lupa.py --limit 50 --semente 1   (piloto, amostra de todos os anos)
    python data/corpus/import_lupa.py --delay 2
    python data/corpus/build_index.py --apenas-novos      (indexa só os trechos novos)
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrieval import config  # noqa: E402
from import_factckbr import veredito_contradiz_titulo  # noqa: E402

SITEMAP_INDEX = "https://www.agencialupa.org/wp-content/sitemaps/posts/post-sitemap-index.xml"
# O cliente padrão do Python recebe 403 da Lupa (filtro automático de robôs; o robots.txt
# permite o acesso, ADR 2). Este User-Agent se identifica como pesquisa e é aceito.
USER_AGENT = "Mozilla/5.0 (pesquisa academica; grupo1_ResIA, checagem de fatos)"

CLAIMS_PATH = config.RAW_DIR / "lupa_claims.jsonl"
ARTICLES_PATH = config.RAW_DIR / "lupa_articles.jsonl"
DESCARTES_PATH = config.RAW_DIR / "lupa_descartes.jsonl"
FALHAS_PATH = config.RAW_DIR / "lupa_falhas.jsonl"
FACTCKBR_PATH = config.RAW_DIR / "factckbr_claims.jsonl"

_SECOES_CHECAGEM = {"verificacao", "checagem", "eleicoes"}
_SLUG_CHECAGEM = re.compile(r"^(verificamos|e-falso|e-verdade|e-enganoso|e-exagerado|e-montagem|falso|verdadeiro)")
_URL = re.compile(r"^https?://(www\.)?agencialupa\.org/([^/]+)/(\d{4})/(\d{2})/(\d{2})/([^/?#]+)")
_VERIFICAMOS = re.compile(r"^#Verificamos\w*:\s*", re.IGNORECASE)
_TITULO = re.compile(
    r"^É\s+(falso|falsa|verdade|verdadeiro|verdadeira|enganoso|enganosa|exagerado|exagerada|montagem)"
    r"\s+que\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def eh_candidata(url: str) -> bool:
    """Página de checagem, pelo endereço (seção e começo do slug)."""
    m = _URL.match(url or "")
    if not m:
        return False
    secao, slug = m.group(2), m.group(6)
    return secao in _SECOES_CHECAGEM or (secao == "jornalismo" and bool(_SLUG_CHECAGEM.match(slug)))


def data_da_url(url: str) -> str:
    m = _URL.match(url or "")
    return f"{m.group(3)}-{m.group(4)}-{m.group(5)}" if m else ""


def limpar_titulo(titulo: str) -> str:
    titulo = " ".join((titulo or "").split())
    titulo = _VERIFICAMOS.sub("", titulo)
    titulo = re.sub(r"\s*[•|\-–]\s*(Agência )?Lupa$", "", titulo)
    return titulo.strip()


def alegacao_do_titulo(titulo: str) -> tuple[str, str] | None:
    """(veredito, alegação) de um título "É <rótulo> que <alegação>"; None fora do padrão."""
    m = _TITULO.match(limpar_titulo(titulo))
    if not m:
        return None
    alegacao = m.group(2).strip().rstrip(".!;").strip()
    if len(alegacao.split()) < 2:
        return None
    return m.group(1).capitalize(), alegacao[0].upper() + alegacao[1:]


def montar(url: str, titulo_bruto: str, texto: str) -> tuple[dict | None, dict | None, str | None]:
    """(checagem, texto, None) no formato do corpus, ou (None, None, motivo do descarte)."""
    titulo = limpar_titulo(titulo_bruto)
    par = alegacao_do_titulo(titulo)
    if not par:
        return None, None, "título sem 'É <rótulo> que'"
    veredito, alegacao = par
    if veredito_contradiz_titulo(veredito, alegacao):
        return None, None, "veredito verdadeiro com título que desmente"
    texto = (texto or "").strip()
    if not texto:
        return None, None, "sem texto"
    checagem = {
        "source_url": url,
        "source_name": "Agência Lupa",          # o build_index.py acrescenta o ano se for antes de 2024
        "review_title": titulo,
        "review_date": data_da_url(url),
        "agency_verdict": veredito,
        "claim_reviewed": alegacao,
        "language": "pt",
        "corpus": "lupa",
    }
    return checagem, {"source_url": url, "title": titulo, "text": texto, "corpus": "lupa"}, None


def _sem_barra(url: str) -> str:
    return url.strip().rstrip("/")


def pendentes(urls: list[str], ja_vistas: set[str]) -> list[str]:
    """URLs ainda não processadas (compara sem a barra final)."""
    vistas = {_sem_barra(u) for u in ja_vistas}
    return [u for u in dict.fromkeys(urls) if _sem_barra(u) not in vistas]


# --- Rede ------------------------------------------------------------------------

def _get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def listar_urls(delay: float) -> list[str]:
    """Todas as URLs dos sitemaps de posts."""
    urls = []
    for loc in re.findall(r"<loc>([^<]+)</loc>", _get(SITEMAP_INDEX)):
        urls += re.findall(r"<loc>([^<]+)</loc>", _get(loc.strip()))
        time.sleep(delay)
    return [u.strip() for u in urls]


def baixar(url: str, retries: int) -> tuple[str, str]:
    """(título, texto) da página. O título vem do og:title (o da página, sem cortes)."""
    import html as html_lib

    import trafilatura

    ultimo = "download falhou"
    for tentativa in range(1, retries + 1):
        try:
            html = _get(url)
        except Exception as exc:   # HTTP 403/404/5xx, tempo esgotado
            ultimo = f"download falhou ({getattr(exc, 'code', type(exc).__name__)})"
            time.sleep(2 ** tentativa)
            continue
        m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', html) or \
            re.search(r"<title>(.*?)</title>", html, re.S)
        titulo = html_lib.unescape(m.group(1)) if m else ""
        extraido = trafilatura.extract(html, output_format="json", include_comments=False,
                                       include_tables=False, favor_precision=True)
        texto = json.loads(extraido).get("text", "") if extraido else ""
        return titulo, texto
    raise RuntimeError(ultimo)


def _ler_urls(caminho: Path) -> set[str]:
    if not caminho.exists():
        return set()
    with caminho.open(encoding="utf-8") as f:
        return {json.loads(l)["source_url"] for l in f if l.strip()}


def _gravar(f, registro: dict) -> None:
    f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    f.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--delay", type=float, default=2.0, help="pausa entre downloads, em segundos")
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0, help="0 = todas as pendentes")
    parser.add_argument("--semente", type=int, default=None,
                        help="embaralha a fila com esta semente (piloto representativo de todos os anos)")
    parser.add_argument("--max-falhas-seguidas", type=int, default=20,
                        help="desiste depois de N falhas seguidas (bloqueio não é contornado)")
    args = parser.parse_args(argv)

    todas = listar_urls(delay=0.5)
    candidatas = [u for u in todas if eh_candidata(u)]
    ja = _ler_urls(CLAIMS_PATH) | _ler_urls(DESCARTES_PATH) | _ler_urls(FACTCKBR_PATH)
    fila = pendentes(candidatas, ja)
    if args.semente is not None:
        random.Random(args.semente).shuffle(fila)
    if args.limit:
        fila = fila[: args.limit]
    print(f"{len(todas)} páginas nos sitemaps; {len(candidatas)} candidatas a checagem; "
          f"{len(fila)} pendentes nesta execução.", flush=True)

    contagem: Counter = Counter()
    seguidas = 0
    with CLAIMS_PATH.open("a", encoding="utf-8") as fc, ARTICLES_PATH.open("a", encoding="utf-8") as fa, \
            DESCARTES_PATH.open("a", encoding="utf-8") as fd, FALHAS_PATH.open("a", encoding="utf-8") as ff:
        for i, url in enumerate(fila, 1):
            try:
                titulo, texto = baixar(url, args.retries)
                seguidas = 0
            except Exception as exc:
                _gravar(ff, {"source_url": url, "erro": str(exc),
                             "em": datetime.now(timezone.utc).isoformat()})
                contagem["falha no download"] += 1
                seguidas += 1
                if args.max_falhas_seguidas and seguidas >= args.max_falhas_seguidas:
                    print(f"{seguidas} falhas seguidas: o site pode estar recusando o download. "
                          "Parando sem contornar (ADR 2).", flush=True)
                    break
                time.sleep(args.delay)
                continue
            checagem, artigo, motivo = montar(url, titulo, texto)
            if motivo:
                _gravar(fd, {"source_url": url, "titulo": limpar_titulo(titulo), "motivo": motivo})
                contagem[motivo] += 1
            else:
                _gravar(fc, checagem)
                _gravar(fa, artigo)
                contagem["aceita"] += 1
            if i % 50 == 0:
                print(f"  {i}/{len(fila)} {dict(contagem)}", flush=True)
            time.sleep(args.delay)

    print(f"Concluído: {dict(contagem)}", flush=True)
    print("Próximo passo: python data/corpus/build_index.py --apenas-novos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
