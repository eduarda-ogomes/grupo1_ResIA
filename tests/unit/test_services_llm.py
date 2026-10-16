import pytest

from src.services import llm as servicos


@pytest.mark.parametrize("nome", ["llm_sintetizador", "llm_socratico", "llm_texto"])
def test_clientes_tem_timeout_e_nao_repetem_a_chamada(nome):
    # Sem timeout, uma chamada abandonada pelo grafo (src/pipeline/protecao.py) ocuparia o LM Studio indefinidamente
    cliente = getattr(servicos, nome)

    assert cliente.request_timeout == 120
    assert cliente.max_retries == 0


def test_valores_dos_clientes():
    # Temperatura e teto de tokens por agente (spec de desempenho): o teto evita geração longa demais
    assert (servicos.llm_texto.temperature, servicos.llm_texto.max_tokens) == (0, 1000)
    assert (servicos.llm_sintetizador.temperature, servicos.llm_sintetizador.max_tokens) == (0, 400)
    assert (servicos.llm_socratico.temperature, servicos.llm_socratico.max_tokens) == (0.2, 300)


def test_cliente_nao_envia_draft_model():
    # O LM Studio recusa `draft_model` por requisição: o rascunho só vale configurado ao carregar o modelo
    assert not servicos._cliente(0, 100).extra_body
    assert not hasattr(servicos, "modelo_rascunho")


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
