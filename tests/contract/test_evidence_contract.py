"""Teste de contrato do Agente de Evidências (Seção 9.4, regra 3).

Um State de exemplo fixo entra; a saída precisa validar no schema Evidence da
Seção 3.3. Roda contra o stub e contra o agente real (com busca e NLI
simulados). Rodar a partir da raiz do repositório:

    python -m pytest tests/contract/test_evidence_contract.py
"""

import pytest

from src.agents import evidence as agent
from src.state import Evidence, PipelineState, initial_state
from src.stubs import evidence_stub
from tests.evidence_fakes import EVIDENCE_FIELDS, fachin_fakes, mamao_fakes, patch_agent


def _agente_fachin(monkeypatch):
    state, search, classify, leads, texts = fachin_fakes()
    patch_agent(monkeypatch, agent, search, classify, leads, texts)
    return state, agent.run(state)


def _agente_mamao(monkeypatch):
    state, search, classify, _ = mamao_fakes()
    patch_agent(monkeypatch, agent, search, classify)
    return state, agent.run(state)


def _stub(monkeypatch):
    state, *_ = mamao_fakes()
    return state, evidence_stub.run(state)


@pytest.mark.parametrize("produce", [_agente_fachin, _agente_mamao, _stub], ids=["agente_fachin", "agente_mamao", "stub"])
def test_saida_respeita_o_contrato(produce, monkeypatch):
    state, output = produce(monkeypatch)
    segment_ids = {s["id"] for s in state.segments}

    assert set(output) <= {"evidence", "warnings"}, "o agente só escreve os próprios campos"
    assert isinstance(output["evidence"], list) and output["evidence"]

    for item in output["evidence"]:
        assert set(item) == EVIDENCE_FIELDS
        Evidence.model_validate(item)
        assert item["stance"] in {"apoia", "contradiz", "insuficiente"}
        assert item["source_url"].startswith(("http://", "https://")), "citação obrigatória"
        assert item["excerpt"].strip()
        assert item["segment_id"] in segment_ids

    # A saída entra no PipelineState estrito (Seção 3.3) sem erro.
    merged = PipelineState(**initial_state("x", segments=state.segments, **output))
    assert len(merged.evidence) == len(output["evidence"])


def test_stub_expoe_o_nome_usado_pelo_grafo():
    assert evidence_stub.evidence_node is evidence_stub.run


def test_falha_devolve_none_e_aviso(monkeypatch):
    state, search, classify, _ = mamao_fakes()
    patch_agent(monkeypatch, agent, search, classify)

    def broken_search(texts, k=None):
        raise RuntimeError("índice ausente")

    monkeypatch.setattr(agent, "search", broken_search)
    output = agent.run(state)
    assert output["evidence"] is None
    assert set(output) == {"evidence", "warnings"} and all(isinstance(w, str) for w in output["warnings"])
