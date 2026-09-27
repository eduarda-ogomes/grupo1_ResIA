"""Teste de contrato do Agente de Evidências (Seção 9.4, regra 3).

Um State de exemplo fixo entra; a saída precisa validar no schema Evidence da
Seção 3.3. Roda contra o stub e contra o agente real (com busca e NLI
simulados). Rodar a partir da raiz do repositório:

    python -m pytest tests/contract/test_evidence_contract.py
"""

import pytest

from src.agents import evidence as agent
from src.agents.evidence_schema import Evidence
from src.stubs import evidence_stub
from tests.evidence_fakes import EVIDENCE_FIELDS, mamao_fakes


def _state_evidence_class():
    """Quando o state.py da Seção 3.3 chegar na main, valida também contra ele."""
    try:
        from src.state import Evidence as StateEvidence
    except Exception:
        return None
    return StateEvidence if "segment_id" in StateEvidence.model_fields else None


def _real_agent_output(monkeypatch):
    state, search, classify, _ = mamao_fakes()
    monkeypatch.setattr(agent, "search", search)
    monkeypatch.setattr(agent, "classify", classify)
    return state, agent.run(state)


def _stub_output(monkeypatch):
    state, *_ = mamao_fakes()
    return state, evidence_stub.run(state)


@pytest.mark.parametrize("produce", [_real_agent_output, _stub_output], ids=["agente_real", "stub"])
def test_saida_respeita_o_contrato(produce, monkeypatch):
    state, output = produce(monkeypatch)
    segment_ids = {s["id"] for s in state.segments}

    assert isinstance(output, dict)
    assert set(output) <= {"evidence", "warnings"}, "o agente só escreve os próprios campos"
    assert isinstance(output["evidence"], list)
    assert output["evidence"], "o caso do mamão deve produzir evidências"

    state_evidence = _state_evidence_class()
    for item in output["evidence"]:
        assert set(item) == EVIDENCE_FIELDS
        Evidence.model_validate(item)
        if state_evidence is not None:
            state_evidence.model_validate(item)
        assert item["stance"] in {"apoia", "contradiz", "insuficiente"}
        assert item["source_url"].startswith(("http://", "https://")), "citação obrigatória"
        assert item["excerpt"].strip()
        assert item["segment_id"] in segment_ids


def test_falha_devolve_none_e_aviso(monkeypatch):
    state, *_ = mamao_fakes()

    def broken_search(texts, k=None):
        raise RuntimeError("índice ausente")

    monkeypatch.setattr(agent, "search", broken_search)
    output = agent.run(state)
    assert output["evidence"] is None
    assert output["warnings"] and all(isinstance(w, str) for w in output["warnings"])
    assert set(output) == {"evidence", "warnings"}
