"""Diagnóstico do Agente de Evidências sobre o índice real.

Para cada frase, mostra os trechos recuperados, as checagens candidatas com o
resultado de cada passo (termos-chave e NLI) e as evidências que o agente
devolve. Serve para calibrar os limiares e para a análise de erros.

Uso, a partir da raiz do repositório:
    python data/corpus/diagnostico.py --frases "Fachin apontou o dedo para Moraes no STF." "Outra frase."
    python data/corpus/diagnostico.py --arquivo minhas_frases.txt      (uma frase por linha; # comenta)
    python data/corpus/diagnostico.py --vereditos                      (rótulos do corpus e stance de cada um)
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrieval import config  # noqa: E402


def _short(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def diagnose(sentences: list[str]) -> None:
    from src.agents import evidence as agent
    from src.retrieval.claim_match import key_terms, key_terms_present, normalize_claim
    from src.retrieval.nli import classify
    from src.retrieval.search import get_checagem_texts, search
    from src.retrieval.verdicts import display_verdict, stance_from_verdict

    print(f"limiar de similaridade={config.SIM_THRESHOLD} | mínimo da etapa 2={config.CLAIM_MATCH_MIN_PROB} "
          f"| candidatas={config.CLAIM_CANDIDATES} | evidências por frase={config.MAX_EVIDENCE_PER_SEGMENT}")
    for sentence, hits in zip(sentences, search(sentences)):
        print("\n" + "=" * 100)
        print(f"FRASE: {sentence}")
        print(f"termos-chave: {key_terms(sentence) or '(nenhum)'}")
        print("-" * 100)
        print(" sim    agência          veredito (stance)            trecho")
        for h in hits:
            m = h.metadata
            mark = "✓" if h.similarity >= config.SIM_THRESHOLD else " "
            verdict = f"{display_verdict(m.get('agency_verdict')) or '-'} ({stance_from_verdict(m.get('agency_verdict'))})"
            print(f"{mark}{h.similarity:.3f}  {_short(m.get('source_name', ''), 15):15s}  "
                  f"{_short(verdict, 27):27s}  {_short(h.text, 70)}")

        candidates = agent._candidates(hits)
        if not candidates:
            print("\n Nenhuma checagem candidata (acima do limiar e com alegação checada).")
        else:
            claims = [agent._meta(g, "claim_reviewed") for g in candidates]
            pairs = [p for c in claims for p in ((normalize_claim(c), sentence), (sentence, normalize_claim(c)))]
            probs = classify(pairs)
            print("\n Checagens candidatas:")
            for i, (group, claim) in enumerate(zip(candidates, claims)):
                url, title = agent._meta(group, "source_url"), agent._meta(group, "review_title")
                terms = key_terms_present(sentence, [claim, title, *get_checagem_texts(url)], claim)
                score = agent.claim_match_score(probs[2 * i], probs[2 * i + 1])
                if not terms.ok:
                    result = f"REJEITADA: troca de termo (frase tem {terms.missing}, alegação tem {terms.substitutes})"
                elif score < config.CLAIM_MATCH_MIN_PROB:
                    result = f"REJEITADA: NLI {score:.2f} (não é a mesma alegação)"
                else:
                    result = f"ACEITA: NLI {score:.2f}"
                print(f"   alegação: {_short(claim, 85)}")
                print(f"   título:   {_short(title, 85) or '-'}")
                print(f"   {result}")
                print(f"   {url}\n")

        evidence = agent.run(SimpleNamespace(segments=[{"id": "s01", "text": sentence}]))["evidence"]
        if not evidence:
            print(" Evidências do agente: nenhuma")
        else:
            print(" Evidências do agente:")
            for e in evidence:
                print(f"   {e['stance']:12s} {e['source_name']}: {e['agency_verdict']} | {_short(e['excerpt'], 70)}")


def list_verdicts(path: Path) -> None:
    from src.retrieval.verdicts import display_verdict, stance_from_verdict

    rows = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
    counts = collections.Counter((display_verdict(r.get("agency_verdict")), stance_from_verdict(r.get("agency_verdict")))
                                 for r in rows)
    print(f"{len(rows)} checagens em {path}\n\n qtd  stance        veredito (como exibido)")
    for (shown, stance), n in counts.most_common():
        print(f"{n:5d}  {stance:12s}  {_short(shown or '-', 80)}")
    print("\nPor stance:", dict(collections.Counter(stance_from_verdict(r.get("agency_verdict")) for r in rows)))
    print("Por agência:", dict(collections.Counter(r.get("source_name") for r in rows)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frases", nargs="+", default=[])
    parser.add_argument("--arquivo", type=Path)
    parser.add_argument("--vereditos", action="store_true")
    args = parser.parse_args()

    sentences = list(args.frases)
    if args.arquivo:
        sentences += [line.strip() for line in args.arquivo.open(encoding="utf-8")
                      if line.strip() and not line.lstrip().startswith("#")]
    if not (sentences or args.vereditos):
        parser.print_help()
        return
    if args.vereditos:
        list_verdicts(config.RAW_DIR / "factcheck_api.jsonl")
    if sentences:
        diagnose(sentences)


if __name__ == "__main__":
    main()
