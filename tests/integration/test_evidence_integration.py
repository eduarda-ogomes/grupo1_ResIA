"""Diagnóstico com o modelo NLI real (baixa o mDeBERTa na primeira execução).

Não roda por padrão, para não pesar no CI. Para rodar, a partir da raiz:

    $env:EVIDENCE_INTEGRATION = "1"     (Windows, PowerShell)
    export EVIDENCE_INTEGRATION=1       (macOS/Linux)
    python -m pytest tests/integration/test_evidence_integration.py -v

Cobre os dois riscos que o manual trata como mais graves para este agente.
Se um destes testes falhar, é um achado para a análise de erros, não um bug
de código: ele mostra que o modelo erra nesse tipo de par.
"""

import os

import pytest

from src.agents.evidence import stance_from_probs
from tests.evidence_fakes import load_fixture

pytestmark = pytest.mark.skipif(
    os.getenv("EVIDENCE_INTEGRATION") != "1",
    reason="defina EVIDENCE_INTEGRATION=1 para rodar com os modelos reais",
)


@pytest.mark.parametrize("fixture", ["evidencias_fato_parecido", "evidencias_boato_citado"])
def test_nli_real_nao_produz_stance_proibida(fixture):
    from src.retrieval.nli import classify

    case = load_fixture(f"bordas/{fixture}.json")
    [probs] = classify([(case["premissa"], case["hipotese"])])
    stance = stance_from_probs(probs)
    print(f"\n{fixture}: probs={probs} -> {stance}")
    assert stance != case["stance_proibida"], case["_caso"]


def test_indice_seed_encontra_o_caso_do_mamao():
    """Requer `python data/corpus/seed_db.py` antes."""
    from src.agents.evidence import run
    from tests.evidence_fakes import make_state

    segments = load_fixture("caso_mamao_dengue/segments.json")["segments"]
    output = run(make_state(segments))
    assert output["evidence"] is not None, output.get("warnings")
    for item in output["evidence"]:
        print(f"\n{item['segment_id']} -> {item['stance']} | {item['source_name']} | {item['excerpt'][:60]}")
