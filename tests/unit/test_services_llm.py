import pytest

from src.services import llm as servicos


@pytest.mark.parametrize("nome", ["llm_sintetizador", "llm_socratico", "llm_texto"])
def test_clientes_tem_timeout_e_nao_repetem_a_chamada(nome):
    # Sem timeout, uma chamada abandonada pelo grafo (src/protecao.py) ocuparia o LM Studio indefinidamente
    cliente = getattr(servicos, nome)

    assert cliente.request_timeout == 120
    assert cliente.max_retries == 0


def test_temperaturas():
    assert (servicos.llm_sintetizador.temperature, servicos.llm_socratico.temperature, servicos.llm_texto.temperature) == (0, 0.7, 0)


def test_nome_do_modelo_vem_de_llm_model(monkeypatch):
    # Cada máquina baixa o modelo com um nome no LM Studio (ex.: "qwen/qwen2.5-vl-7b")
    monkeypatch.setenv("LLM_MODEL", "qwen/qwen2.5-7b-instruct")
    assert servicos.modelo_local() == "qwen/qwen2.5-7b-instruct"


@pytest.mark.parametrize("valor", [None, "", "   "])
def test_sem_llm_model_usa_o_padrao(monkeypatch, valor):
    if valor is None:
        monkeypatch.delenv("LLM_MODEL", raising=False)
    else:
        monkeypatch.setenv("LLM_MODEL", valor)
    assert servicos.modelo_local() == "qwen2.5-7b"
