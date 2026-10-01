"""Teste de contrato do Agente Socrático (Manual §9.4, regra 3).

Valida que a saída do stub e do agente real respeitam o schema do PipelineState.
"""
import json
import pytest

from src.agents import socratic as agent
from src.stubs import socratic_stub as stub
from src.state import PipelineState, initial_state


def _agente_real_simulado(monkeypatch):
    saida = {
        "socratic_questions": [
            "Quais estudos o texto apresenta para sustentar as afirmações?",
            "Quem é a fonte das informações citadas no artigo?",
        ]
    }
    monkeypatch.setattr(agent, "chamar_modelo", lambda msgs: json.dumps(saida))
    with open("tests/fixtures/caso_mamao_dengue/01_ingestor_saida.json", "r", encoding="utf-8") as f:
        ingestor_saida = json.load(f)
    state = PipelineState(**initial_state("test", **ingestor_saida))
    return state, agent.run(state)


def _stub(monkeypatch):
    with open("tests/fixtures/caso_mamao_dengue/01_ingestor_saida.json", "r", encoding="utf-8") as f:
        ingestor_saida = json.load(f)
    state = PipelineState(**initial_state("test", **ingestor_saida))
    return state, stub.run(state)


@pytest.mark.parametrize("produce", [_agente_real_simulado, _stub], ids=["agente_real", "stub"])
def test_saida_socratico_respeita_o_contrato(produce, monkeypatch):
    state, output = produce(monkeypatch)

    assert set(output) <= {"socratic_questions", "warnings"}, "o agente só escreve os próprios campos"
    assert isinstance(output["socratic_questions"], list)
    assert 2 <= len(output["socratic_questions"]) <= 3

    for q in output["socratic_questions"]:
        assert isinstance(q, str)
        assert len(q.strip()) > 0

    # Valida que cabe no PipelineState estrito sem erros
    dump = state.model_dump()
    dump.update(output)
    merged = PipelineState(**dump)
    assert merged.socratic_questions == output["socratic_questions"]


def test_stub_expoe_run_e_socratic_node():
    assert stub.socratic_node is stub.run


def test_agente_expoe_run_e_socratic_node():
    assert agent.socratic_node is agent.run
