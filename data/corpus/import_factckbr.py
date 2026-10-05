"""Converte o FACTCK.BR enriquecido (factckbr_com_texto.csv) para o formato do corpus.

O FACTCK.BR (https://github.com/jghm-f/FACTCK.BR, licença MIT) reúne 1.312
checagens de 2016 a 2019 da Agência Lupa, do Aos Fatos e do Truco. O arquivo
factckbr_com_texto.csv é a versão tratada pelo R2 (notebook AnaliseFACTCKbr), com
o texto completo de cada checagem. Os autores pedem que o artigo
seja citado: WebMedia '19, https://doi.org/10.1145/3323503.3361698

Grava dois arquivos no formato que o build_index.py já lê:
    data/corpus/raw/factckbr_claims.jsonl     (como factcheck_api.jsonl)
    data/corpus/raw/factckbr_articles.jsonl   (como articles.jsonl)

Regras (decisões no ADR 2 de docs/agents/evidencias_decisoes.md):
- Só Lupa e Aos Fatos. O Truco fica para depois: checa falas de políticos, que
  envelhecem rápido, e os títulos dele não trazem a conclusão.
- Só páginas com UMA alegação. O índice e o agente supõem uma alegação por URL; numa
  página com várias (até 27, com rótulos diferentes), o veredito sairia trocado.
- Fora: linhas sem alegação e alegações com mais de 60 palavras (texto da matéria
  colado no campo, erro da coleta original).
- Fora: veredito "verdadeiro" com título que desmente ("É falso que...", "não é",
  "desmente", "boato"). Em 4 checagens o rótulo da coleta original contradiz a própria
  página; mantê-las faria o agente dar `apoia` a um boato desmentido.
- source_name leva o ano ("Agência Lupa (2019)"): o Evidence não tem campo de data, e
  uma checagem de 2018 não pode parecer atual no dossiê.
- Títulos (são o excerpt do agente): tira o "#Verificamos:" e o " | Aos Fatos" do fim;
  quando a coleta original perdeu o "É" inicial ("#Verificamos:  falso que..."), ele é
  restaurado, como está na página da Lupa.
- URLs da Lupa passam do domínio antigo (piaui.folha.uol.com.br/lupa/...) para o atual
  (www.agencialupa.org/jornalismo/...), que é o link citado no dossiê.

Uso, a partir da raiz do repositório (o CSV fica fora do Git, em data/corpus/raw/):
    python data/corpus/import_factckbr.py
    python data/corpus/import_factckbr.py --csv caminho/factckbr_com_texto.csv
    python data/corpus/build_index.py --apenas-novos      (indexa só os trechos novos)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrieval import config  # noqa: E402
from src.retrieval.etapa2 import stance_from_verdict  # noqa: E402

CSV_PATH = config.RAW_DIR / "factckbr_com_texto.csv"
CLAIMS_PATH = config.RAW_DIR / "factckbr_claims.jsonl"
ARTICLES_PATH = config.RAW_DIR / "factckbr_articles.jsonl"

AGENCIAS = {"Lupa": "Agência Lupa", "Aos Fatos": "Aos Fatos"}   # Truco fica para depois
MAX_PALAVRAS_ALEGACAO = 60

_LUPA_ANTIGA = re.compile(r"/lupa/(\d{4}/\d{2}/\d{2}/[^/?#]+)")
_VERIFICAMOS = re.compile(r"^#Verificamos\w*:(\s+)", re.IGNORECASE)
_SUFIXOS = (" | Aos Fatos", " - Agência Pública", " • Lupa")
_ASPAS = "'\"“”‘’ "
_TITULO_QUE_DESMENTE = re.compile(r"\b(falso|falsa|não|desmente|boato)\b", re.IGNORECASE)


def url_atual(url: str, agencia: str) -> str:
    """Link que funciona hoje: Lupa no domínio atual; Aos Fatos com www."""
    url = (url or "").strip()
    if agencia == "Lupa":
        m = _LUPA_ANTIGA.search(url)
        if m:
            return f"https://www.agencialupa.org/jornalismo/{m.group(1)}/"
    if agencia == "Aos Fatos":
        return re.sub(r"^https?://(www\.)?aosfatos\.org", "https://www.aosfatos.org", url)
    return url


def limpar_titulo(titulo: str) -> str:
    """Tira o "#Verificamos:" e o nome do site; restaura o "É" que a coleta perdeu.

    Na Lupa, "#Verificamos:  falso que..." (dois espaços) é "#Verificamos: É falso que..."
    sem o "É": o caractere se perdeu na coleta original do FACTCK.BR.
    """
    titulo = titulo or ""
    m = _VERIFICAMOS.match(titulo)
    if m:
        resto = titulo[m.end():].strip()
        if len(m.group(1)) >= 2 and resto and resto[0].islower():
            resto = "É " + resto
        titulo = resto
    for sufixo in _SUFIXOS:
        if titulo.endswith(sufixo):
            titulo = titulo[: -len(sufixo)]
    titulo = " ".join(titulo.split())
    return titulo[:1].upper() + titulo[1:] if titulo else ""


def veredito_contradiz_titulo(veredito: str, titulo: str) -> bool:
    """Veredito "verdadeiro" (stance apoia) num título que desmente: rótulo trocado na coleta."""
    return stance_from_verdict(veredito) == "apoia" and bool(_TITULO_QUE_DESMENTE.search(titulo))


def _ano(data: str) -> str:
    m = re.match(r"(\d{4})", data or "")
    return m.group(1) if m else ""


def ler_csv(caminho: Path) -> list[dict]:
    csv.field_size_limit(2**31 - 1)   # textos longos; sys.maxsize estoura no Windows
    with Path(caminho).open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def converter(linhas: list[dict]) -> tuple[list[dict], list[dict], Counter]:
    """Filtra e converte; devolve (checagens, textos, motivos de descarte)."""
    por_url = Counter(l.get("URL", "").strip() for l in linhas)
    descartes: Counter = Counter()
    checagens, textos, vistos = [], [], set()
    for l in linhas:
        agencia = (l.get("agencia") or "").strip()
        alegacao = (l.get("claimReviewed") or "").strip().strip(_ASPAS)
        if agencia not in AGENCIAS:
            descartes[f"agência {agencia or '?'} (fica para depois)"] += 1
            continue
        if por_url[l.get("URL", "").strip()] > 1:
            descartes["página com várias alegações"] += 1
            continue
        if not alegacao:
            descartes["sem alegação"] += 1
            continue
        if len(alegacao.split()) > MAX_PALAVRAS_ALEGACAO:
            descartes[f"alegação com mais de {MAX_PALAVRAS_ALEGACAO} palavras"] += 1
            continue
        url = url_atual(l.get("URL", ""), agencia)
        if url in vistos:
            descartes["URL repetida"] += 1
            continue
        vistos.add(url)
        ano = _ano(l.get("data") or l.get("datePublished") or "")
        titulo = limpar_titulo(l.get("title") or "")
        veredito = (l.get("alternativeName") or "").strip()
        if veredito_contradiz_titulo(veredito, titulo):
            descartes["veredito verdadeiro com título que desmente"] += 1
            continue
        checagens.append({
            "source_url": url,
            "source_name": f"{AGENCIAS[agencia]} ({ano})" if ano else AGENCIAS[agencia],
            "review_title": titulo,
            "review_date": (l.get("data") or "")[:10],
            "agency_verdict": veredito,
            "claim_reviewed": alegacao,
            "language": "pt",
            "corpus": "factckbr",
            "url_original": l.get("URL", "").strip(),
        })
        texto = (l.get("texto_completo") or "").strip()
        if texto:
            textos.append({"source_url": url, "title": titulo, "text": texto, "corpus": "factckbr"})
    return checagens, textos, descartes


def _gravar_jsonl(caminho: Path, registros: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as f:
        for r in registros:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    parser.add_argument("--claims", type=Path, default=CLAIMS_PATH)
    parser.add_argument("--articles", type=Path, default=ARTICLES_PATH)
    args = parser.parse_args(argv)

    if not args.csv.exists():
        print(f"CSV não encontrado em {args.csv}. Copie o factckbr_com_texto.csv para lá ou use --csv.")
        return 1
    linhas = ler_csv(args.csv)
    checagens, textos, descartes = converter(linhas)
    _gravar_jsonl(args.claims, checagens)
    _gravar_jsonl(args.articles, textos)
    print(f"{len(linhas)} linhas no CSV -> {len(checagens)} checagens ({len(textos)} com texto).")
    print("Por agência:", dict(Counter(c["source_name"].split(" (")[0] for c in checagens)))
    print("Descartadas:", dict(descartes))
    print(f"Gravado em {args.claims} e {args.articles}.")
    print("Próximo passo: python data/corpus/build_index.py --apenas-novos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
