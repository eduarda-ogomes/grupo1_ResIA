"""Contrato do Sintetizador (Manual §9.4, regra 3): a saída mesclada valida no PipelineState."""
from src.agents.synthesizer import WARN_MODELO_INDISPONIVEL, argumento_node, sintetizador_node
from src.state import PipelineState
from tests import modelos_falsos as falsos


def mesclar(state: PipelineState, resultado: dict) -> PipelineState:
    return PipelineState(**{**state.model_dump(), **resultado})


def test_contrato_com_o_7b_falso(monkeypatch):
    falsos.SintetizadorFalso().instalar(monkeypatch)
    state = PipelineState(**falsos.carregar_mamao("05_sintetizador_entrada.json"))

    argumento = argumento_node(state)
    assert set(argumento) == {"argument"}
    com_argumento = mesclar(state, argumento)
    assert com_argumento.argument

    resultado = sintetizador_node(com_argumento)

    assert set(resultado) == {"dossier"}
    assert mesclar(com_argumento, resultado).dossier


def test_contrato_do_argumento_com_o_modelo_desligado():
    # o tests/conftest.py desliga o modelo: o argumento sai do fallback, com aviso próprio
    state = PipelineState(**falsos.carregar_mamao("05_sintetizador_entrada.json"))

    resultado = argumento_node(state)

    assert set(resultado) == {"argument", "warnings"}
    assert resultado["warnings"] == [WARN_MODELO_INDISPONIVEL]
    assert mesclar(state, resultado).argument


def test_sintetizador_nunca_chama_o_modelo_nem_avisa_sem_argumento():
    # argument None: monta com o fallback em código; o modelo desligado nem é consultado
    state = PipelineState(**falsos.carregar_mamao("05_sintetizador_entrada.json"))

    resultado = sintetizador_node(state)

    assert set(resultado) == {"dossier"}
    assert mesclar(state, resultado).dossier
