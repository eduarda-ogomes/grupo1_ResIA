"""Diagnóstico do Agente de Evidências sobre o índice real.

Para cada frase, mostra os trechos recuperados (similaridade, marcação de
boato, agência, veredito), a etapa "mesma alegação" (entailment nas duas
direções) e as evidências que o agente emitiria em cada modo. Serve para
calibrar os limiares e para a análise de erros.

Uso, a partir da raiz do repositório:
    python data/corpus/diagnostico.py --frases "Fachin apontou o dedo para Moraes no STF." "Outra frase."
    python data/corpus/diagnostico.py --arquivo minhas_frases.txt      (uma frase por linha; # comenta)
    python data/corpus/diagnostico.py --vereditos                      (rótulos do corpus e stance de cada um)
    python data/corpus/diagnostico.py --amostra-boato 20               (parágrafos marcados como boato)

Os limiares e o modo vêm das mesmas variáveis de ambiente do agente
(EVIDENCE_SIM_THRESHOLD, EVIDENCE_CLAIM_MATCH_MIN_PROB etc.).
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrieval import config  # noqa: E402


def _short(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def diagnose_sentences(sentences: list[str], k: int) -> None:
    from src.agents import evidence as agent
    from src.retrieval.nli import classify
    from src.retrieval.search import search
    from src.retrieval.verdicts import display_verdict, stance_from_verdict

    from src.retrieval.claim_match import key_terms, key_terms_present, normalize_claim
    from src.retrieval.search import get_checagem_texts

    print(f"limiar de similaridade={config.SIM_THRESHOLD} | mínimo da etapa 2={config.CLAIM_MATCH_MIN_PROB} "
          f"| termos-chave={'ligada' if config.KEY_TERM_CHECK else 'desligada'} "
          f"| normalização={'ligada' if config.CLAIM_NORMALIZE else 'desligada'} "
          f"| proteção contra boato={'ligada' if config.FILTER_RUMOR_CHUNKS else 'desligada'} | k={k}")
    hits_per_sentence = search(sentences, k=k)
    for sentence, hits in zip(sentences, hits_per_sentence):
        print("\n" + "=" * 100)
        print(f"FRASE: {sentence}")
        print(f"termos-chave da frase: {key_terms(sentence) or '(nenhum)'}")
        print("-" * 100)
        print(" sim   boato  agência          veredito (stance)            trecho")
        for h in hits:
            m = h.metadata
            mark = "✓" if h.similarity >= config.SIM_THRESHOLD else " "
            verdict = f"{display_verdict(m.get('agency_verdict')) or '-'} ({stance_from_verdict(m.get('agency_verdict'))})"
            print(f"{mark}{h.similarity:.3f}  {'sim ' if m.get('describes_rumor') else 'não '}  "
                  f"{_short(m.get('source_name', ''), 15):15s}  {_short(verdict, 27):27s}  {_short(h.text, 70)}")

        groups = agent.group_hits_by_url(hits)
        claims = [(g[0].metadata.get("source_url"), str(g[0].metadata.get("claim_reviewed") or ""),
                   str(g[0].metadata.get("review_title") or "")) for g in groups]
        claims = [(url, c, t) for url, c, t in claims if c]
        if claims:
            pairs = []
            for _, c, _ in claims:
                for claim in (c, normalize_claim(c)):
                    pairs += [(claim, sentence), (sentence, claim)]
            probs = classify(pairs)
            print("\n Etapa 'mesma alegação' (checagens acima do limiar):")
            for i, (url, claim, title) in enumerate(claims):
                raw = agent.claim_match_score(probs[4 * i], probs[4 * i + 1])
                norm = agent.claim_match_score(probs[4 * i + 2], probs[4 * i + 3])
                terms = key_terms_present(sentence, [claim, title, *get_checagem_texts(url)], claim)
                print(f"   alegação: {_short(claim, 85)}")
                print(f"   título:   {_short(title, 85) or '-'}")
                if terms.ok:
                    status = "ok" + (f" (ausentes sem troca: {terms.missing})" if terms.missing else "")
                else:
                    status = f"TROCA: faltam {terms.missing}, alegação tem {terms.substitutes}"
                print(f"   entailment: original={raw:.2f} normalizada={norm:.2f} | termos-chave: {status}")
                print(f"   {url}\n")
        else:
            print("\n Nenhuma checagem acima do limiar com claim_reviewed.")

        for mode in config.STANCE_MODES:
            original = config.STANCE_MODE
            config.STANCE_MODE = mode
            try:
                output = agent.run(SimpleNamespace(segments=[{"id": "s01", "text": sentence}]))
            finally:
                config.STANCE_MODE = original
            evidence = output["evidence"]
            label = f" Agente no modo {mode}{' (padrão)' if mode == original else ''}:"
            if evidence is None:
                print(f"{label} FALHOU {output.get('warnings')}")
            elif not evidence:
                print(f"{label} nenhuma evidência")
            else:
                print(label)
                for e in evidence:
                    print(f"   {e['stance']:12s} {e['source_name']}: {e['agency_verdict']} | {_short(e['excerpt'], 70)}")


def list_verdicts(path: Path) -> None:
    from src.retrieval.verdicts import display_verdict, stance_from_verdict

    rows = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
    counts = collections.Counter((display_verdict(r.get("agency_verdict")), stance_from_verdict(r.get("agency_verdict")))
                                 for r in rows)
    print(f"{len(rows)} checagens em {path}\n")
    print(" qtd  stance        veredito (como exibido)")
    for (shown, stance), n in counts.most_common():
        print(f"{n:5d}  {stance:12s}  {_short(shown or '-', 80)}")
    print("\nPor stance:", dict(collections.Counter(stance_from_verdict(r.get("agency_verdict")) for r in rows)))
    print("Por agência:", dict(collections.Counter(r.get("source_name") for r in rows)))


def sample_rumor(path: Path, n: int, seed: int) -> None:
    from src.retrieval.chunking import describes_rumor, split_paragraphs

    articles = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
    paragraphs = [p for a in articles for p in split_paragraphs(a.get("text", ""))]
    flagged = [p for p in paragraphs if describes_rumor(p)]
    print(f"{len(flagged)} de {len(paragraphs)} parágrafos marcados como 'descreve o boato'. Amostra:\n")
    for p in random.Random(seed).sample(flagged, min(n, len(flagged))):
        print(f" * {_short(p, 200)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--frases", nargs="+", default=[])
    parser.add_argument("--arquivo", type=Path)
    parser.add_argument("--k", type=int, default=config.SEARCH_K)
    parser.add_argument("--vereditos", action="store_true")
    parser.add_argument("--amostra-boato", type=int, default=0)
    parser.add_argument("--semente", type=int, default=0)
    args = parser.parse_args()

    sentences = list(args.frases)
    if args.arquivo:
        sentences += [line.strip() for line in args.arquivo.open(encoding="utf-8")
                      if line.strip() and not line.lstrip().startswith("#")]

    if not (sentences or args.vereditos or args.amostra_boato):
        parser.print_help()
        return
    if args.vereditos:
        list_verdicts(config.RAW_DIR / "factcheck_api.jsonl")
    if args.amostra_boato:
        sample_rumor(config.RAW_DIR / "articles.jsonl", args.amostra_boato, args.semente)
    if sentences:
        diagnose_sentences(sentences, args.k)


if __name__ == "__main__":
    main()
