"""Diagnóstico com os modelos reais (baixa o mDeBERTa e o BGE-M3 na primeira execução).

Não roda por padrão, para não pesar no CI. Para rodar, a partir da raiz:

    $env:EVIDENCE_INTEGRATION = "1"     (Windows, PowerShell)
    export EVIDENCE_INTEGRATION=1       (macOS/Linux)
    python -m pytest tests/integration/test_evidence_integration.py -v -s

Se um teste de diagnóstico falhar, é um achado para a análise de erros, não um
bug de código: mostra que o modelo erra naquele tipo de par.
"""

import os

import pytest

from src.agents.evidence import claim_match_score, stance_from_probs
from src.retrieval import config
from tests.evidence_fakes import load_fixture, make_state

pytestmark = pytest.mark.skipif(
    os.getenv("EVIDENCE_INTEGRATION") != "1",
    reason="defina EVIDENCE_INTEGRATION=1 para rodar com os modelos reais",
)


# --- Modo "trecho" (Seção 4.2): falhas conhecidas -----------------------------
# Em 26/09, com o mDeBERTa real, os dois casos falharam: fato parecido -> contradiz
# (0,93) e boato citado -> apoia (0,99). Foi isso que motivou o modo "alegacao".
# Marcados como xfail: continuam rodando e mostram se algo mudar.

@pytest.mark.xfail(reason="Falha conhecida do modo trecho (ver documento de decisões, seção 4)", strict=False)
@pytest.mark.parametrize("fixture", ["evidencias_fato_parecido", "evidencias_boato_citado"])
def test_modo_trecho_nli_nao_produz_stance_proibida(fixture):
    from src.retrieval.nli import classify

    case = load_fixture(f"bordas/{fixture}.json")
    [probs] = classify([(case["premissa"], case["hipotese"])])
    stance = stance_from_probs(probs)
    print(f"\n{fixture}: probs={probs} -> {stance}")
    assert stance != case["stance_proibida"], case["_caso"]


# --- Modo "alegacao": etapa "mesma alegação" ---------------------------------

_PAIRS = load_fixture("bordas/evidencias_mesma_alegacao.json")["pares"]


@pytest.mark.parametrize("pair", _PAIRS, ids=[p["nome"] for p in _PAIRS])
def test_etapa_mesma_alegacao_com_nli_real(pair):
    from src.retrieval.nli import classify

    forward, backward = classify([(pair["alegacao"], pair["frase"]), (pair["frase"], pair["alegacao"])])
    score = claim_match_score(forward, backward)
    matched = score >= config.CLAIM_MATCH_MIN_PROB
    print(f"\n{pair['nome']}: entailment alegação->frase={forward['entailment']:.3f} "
          f"frase->alegação={backward['entailment']:.3f} -> mesma alegação={matched}")
    assert matched == pair["mesma_alegacao"]


# --- Índice do seed_db.py ------------------------------------------------------

def test_indice_seed_encontra_o_caso_do_mamao():
    """Requer `python data/corpus/seed_db.py` antes. Mostra o que o agente emite."""
    from src.agents.evidence import run

    segments = load_fixture("caso_mamao_dengue/segments.json")["segments"]
    output = run(make_state(segments))
    assert output["evidence"] is not None, output.get("warnings")
    print(f"\nmodo={config.STANCE_MODE} limiar={config.SIM_THRESHOLD}: {len(output['evidence'])} evidência(s)")
    for item in output["evidence"]:
        print(f"{item['segment_id']} -> {item['stance']} | {item['source_name']}: {item['agency_verdict']} "
              f"| {item['excerpt'][:70]}")
