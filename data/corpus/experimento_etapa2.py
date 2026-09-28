"""Experimento: qual variante da etapa "mesma alegação" usar no modo alegacao.

Roda o NLI real nos pares de data/corpus/pares_etapa2.json (alegações reais do
corpus + frases escritas para o teste) e compara:

  A  NLI entre a frase e a alegação checada (como está hoje, sem termos-chave)
  B  NLI com a alegação normalizada (sem "Foto/Vídeo mostra")
  C  A + termos-chave (troca de nome próprio, número ou doença entre frase e alegação)
  D  B + termos-chave
  E  só termos-chave, sem NLI (referência)

O erro mais grave é CASAR o que não é a mesma alegação (o agente citaria a
checagem errada); rejeitar uma paráfrase só faz perder evidência.

Não precisa do índice: usa os dados brutos (títulos e textos) de data/corpus/raw/.

Uso, a partir da raiz do repositório:
    python data/corpus/experimento_etapa2.py
    python data/corpus/experimento_etapa2.py --limiares 0.5 0.7 0.9
Salva a tabela completa em data/corpus/raw/experimento_etapa2.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrieval import config  # noqa: E402
from src.retrieval.claim_match import key_terms_present, normalize_claim  # noqa: E402

PAIRS_FILE = Path(__file__).resolve().parent / "pares_etapa2.json"
VARIANTS = {
    "A": "NLI",
    "B": "NLI + normalização",
    "C": "NLI + termos-chave",
    "D": "NLI + normalização + termos-chave",
    "E": "só termos-chave",
}
TYPES = ["parafrase", "parafrase_midia", "troca_nome", "troca_numero", "outro_fato", "negacao"]


def load_references(raw_dir: Path) -> tuple[dict[str, dict], dict[str, str]]:
    claims: dict[str, dict] = {}
    texts: dict[str, str] = {}
    path = raw_dir / "factcheck_api.jsonl"
    if path.exists():
        for line in path.open(encoding="utf-8"):
            if line.strip():
                row = json.loads(line)
                claims.setdefault(row["source_url"], row)
    path = raw_dir / "articles.jsonl"
    if path.exists():
        for line in path.open(encoding="utf-8"):
            if line.strip():
                row = json.loads(line)
                texts[row["source_url"]] = row.get("text", "")
    return claims, texts


def score_pairs(pairs: list[dict], classify) -> list[dict]:
    """Entailment máximo (2 direções) com a alegação original e com a normalizada."""
    nli_inputs: list[tuple[str, str]] = []
    for p in pairs:
        p["alegacao_normalizada"] = normalize_claim(p["alegacao"])
        for claim in (p["alegacao"], p["alegacao_normalizada"]):
            nli_inputs += [(claim, p["frase"]), (p["frase"], claim)]
    probs = classify(nli_inputs)
    for i, p in enumerate(pairs):
        f_raw, b_raw, f_norm, b_norm = probs[4 * i: 4 * i + 4]
        p["ent_original"] = max(f_raw["entailment"], b_raw["entailment"])
        p["ent_normalizada"] = max(f_norm["entailment"], b_norm["entailment"])
    return pairs


def add_key_terms(pairs: list[dict], claims: dict[str, dict], texts: dict[str, str]) -> list[dict]:
    for p in pairs:
        meta = claims.get(p["source_url"], {})
        refs = [p["alegacao"], meta.get("review_title", ""), texts.get(p["source_url"], "")]
        result = key_terms_present(p["frase"], refs, p["alegacao"])
        p["termos_ok"] = result.ok
        p["termos_ausentes"] = " ".join(result.missing)
        p["termos_substitutos"] = " ".join(result.substitutes)
        p["checagem_tem_texto"] = bool(texts.get(p["source_url"]))
    return pairs


def decide(p: dict, variant: str, threshold: float) -> bool:
    nli_raw = p["ent_original"] >= threshold
    nli_norm = p["ent_normalizada"] >= threshold
    return {
        "A": nli_raw,
        "B": nli_norm,
        "C": nli_raw and p["termos_ok"],
        "D": nli_norm and p["termos_ok"],
        "E": p["termos_ok"],
    }[variant]


def summarize(pairs: list[dict], variant: str, threshold: float) -> dict:
    by_type = Counter()
    total_by_type = Counter(p["tipo"] for p in pairs)
    wrong_matches = []
    lost = []
    for p in pairs:
        matched = decide(p, variant, threshold)
        if matched == p["mesma_alegacao"]:
            by_type[p["tipo"]] += 1
        elif matched:
            wrong_matches.append(p["id"])
        else:
            lost.append(p["id"])
    return {
        "acertos": sum(by_type.values()),
        "total": len(pairs),
        "por_tipo": {t: f"{by_type[t]}/{total_by_type[t]}" for t in TYPES if total_by_type[t]},
        "casou_errado": wrong_matches,
        "paráfrases_perdidas": lost,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pares", type=Path, default=PAIRS_FILE)
    parser.add_argument("--limiares", type=float, nargs="+", default=[config.CLAIM_MATCH_MIN_PROB, 0.7, 0.9])
    parser.add_argument("--csv", type=Path, default=config.RAW_DIR / "experimento_etapa2.csv")
    args = parser.parse_args()

    from src.retrieval.nli import classify

    pairs = json.loads(args.pares.read_text(encoding="utf-8"))["pares"]
    claims, texts = load_references(config.RAW_DIR)
    if not claims:
        print(f"Aviso: {config.RAW_DIR / 'factcheck_api.jsonl'} não encontrado; termos-chave usarão só a alegação.")
    pairs = add_key_terms(score_pairs(pairs, classify), claims, texts)

    print(f"{len(pairs)} pares | tipos: {dict(Counter(p['tipo'] for p in pairs))}\n")
    print("Por par (limiar da etapa 2 = %.2f):" % args.limiares[0])
    print(f"{'id':34s} {'esperado':8s} {'ent orig':>8s} {'ent norm':>8s} {'termos':6s} " + " ".join(VARIANTS))
    for p in pairs:
        marks = " ".join(
            ("✓" if decide(p, v, args.limiares[0]) == p["mesma_alegacao"] else "✗") for v in VARIANTS
        )
        print(f"{p['id']:34s} {'casar' if p['mesma_alegacao'] else 'rejeitar':8s} "
              f"{p['ent_original']:8.3f} {p['ent_normalizada']:8.3f} {'ok' if p['termos_ok'] else 'falta':6s} {marks}"
              + (f"   (troca: falta {p['termos_ausentes']}, alegação tem {p['termos_substitutos']})"
                 if not p["termos_ok"] else
                 (f"   (ausente sem troca: {p['termos_ausentes']})" if p["termos_ausentes"] else "")))

    print("\nResumo (casou_errado = erro grave; paráfrases_perdidas = evidência perdida):")
    for threshold in args.limiares:
        print(f"\n  limiar {threshold:.2f}")
        for v, name in VARIANTS.items():
            if v == "E" and threshold != args.limiares[0]:
                continue
            s = summarize(pairs, v, threshold)
            print(f"   {v} {name:34s} {s['acertos']:2d}/{s['total']}  casou errado: {len(s['casou_errado'])}  "
                  f"paráfrases perdidas: {len(s['paráfrases_perdidas'])}  {s['por_tipo']}")
            if s["casou_errado"]:
                print(f"      casou errado: {', '.join(s['casou_errado'])}")

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    fields = ["id", "tipo", "mesma_alegacao", "alegacao", "alegacao_normalizada", "frase", "ent_original",
              "ent_normalizada", "termos_ok", "termos_ausentes", "termos_substitutos", "checagem_tem_texto", "source_url"]
    with args.csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(pairs)
    print(f"\nTabela completa em {args.csv}")


if __name__ == "__main__":
    main()
