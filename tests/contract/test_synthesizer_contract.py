"""Contrato do Sintetizador (Manual §9.4, regra 3): a saída mesclada valida no PipelineState."""
from src.agents.synthesizer import WARN_MODELO_INDISPONIVEL, sintetizador_node
from src.state import PipelineState
from tests import modelos_falsos as falsos


def mesclar(state: PipelineState, resultado: dict) -> PipelineState:
    return PipelineState(**{**state.model_dump(), **resultado})


def test_contrato_com_o_7b_falso(monkeypatch):
    falsos.SintetizadorFalso().instalar(monkeypatch)
    state = PipelineState(**falsos.carregar_mamao("05_sintetizador_entrada.json"))

    resultado = sintetizador_node(state)

    assert set(resultado) == {"dossier"}
    assert mesclar(state, resultado).dossier


def test_contrato_com_o_modelo_desligado():
    # o tests/conftest.py desliga o modelo: o dossiê sai assim mesmo, com aviso próprio
    state = PipelineState(**falsos.carregar_mamao("05_sintetizador_entrada.json"))

    resultado = sintetizador_node(state)

    assert set(resultado) == {"dossier", "warnings"}
    assert resultado["warnings"] == [WARN_MODELO_INDISPONIVEL]
    assert mesclar(state, resultado).dossier
