"""Testes com os modelos reais e o corpus coletado (não rodam por padrão).

Para rodar, a partir da raiz:

    $env:EVIDENCE_INTEGRATION = "1"     (Windows, PowerShell)
    export EVIDENCE_INTEGRATION=1       (macOS/Linux)
    python -m pytest tests/integration -v -s
"""

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.retrieval import config

pytestmark = pytest.mark.skipif(
    os.getenv("EVIDENCE_INTEGRATION") != "1",
    reason="defina EVIDENCE_INTEGRATION=1 para rodar com os modelos reais",
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data" / "corpus"))


def test_etapa2_nao_casa_nenhuma_alegacao_errada_nos_pares():
    """Os 37 pares do experimento com o NLI real: zero casamentos errados (variante D, a do agente)."""
    import experimento_etapa2 as ex
    from src.retrieval.nli import classify

    if not (config.RAW_DIR / "factcheck_api.jsonl").exists():
        pytest.skip("dados brutos do corpus ausentes")
    pairs = ex.json.loads(ex.PAIRS_FILE.read_text(encoding="utf-8"))["pares"]
    claims, texts = ex.load_references(config.RAW_DIR)
    pairs = ex.add_key_terms(ex.score_pairs(pairs, classify), claims, texts)
    summary = ex.summarize(pairs, "D", config.CLAIM_MATCH_MIN_PROB)
    print(f"\n{summary['acertos']}/{summary['total']} | perdidas: {summary['paráfrases_perdidas']}")
    assert summary["casou_errado"] == []


def test_agente_no_indice_real():
    """Frase do caso Fachin no índice real: o agente roda e cita a checagem do UOL/BOL."""
    from src.agents.evidence import run

    frase = "Fachin apontou o dedo para Moraes durante uma discussão acalorada no STF."
    output = run(SimpleNamespace(segments=[{"id": "s01", "text": frase}]))
    assert output["evidence"] is not None, output.get("warnings")
    for item in output["evidence"]:
        print(f"\n{item['stance']} | {item['source_name']}: {item['agency_verdict']} | {item['excerpt']}")
    assert any(e["stance"] == "contradiz" for e in output["evidence"])
