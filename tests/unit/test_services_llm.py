import pytest

from src.services import llm as servicos


@pytest.mark.parametrize("nome", ["llm_sintetizador", "llm_socratico", "llm_texto"])
def test_clientes_tem_timeout_e_nao_repetem_a_chamada(nome):
    # Sem timeout, uma chamada abandonada pelo grafo (src/protecao.py) ocuparia o LM Studio indefinidamente
    cliente = getattr(servicos, nome)

    assert cliente.request_timeout == 120
    assert cliente.max_retries == 0


def test_valores_dos_clientes():
    # Temperatura e teto de tokens por agente (spec de desempenho): o teto evita geração longa demais
    assert (servicos.llm_texto.temperature, servicos.llm_texto.max_tokens) == (0, 1000)
    assert (servicos.llm_sintetizador.temperature, servicos.llm_sintetizador.max_tokens) == (0, 400)
    assert (servicos.llm_socratico.temperature, servicos.llm_socratico.max_tokens) == (0.2, 300)


def test_sem_rascunho_nao_envia_draft_model(monkeypatch):
    monkeypatch.delenv("LLM_DRAFT_MODEL", raising=False)
    assert not (servicos._cliente(0, 100).extra_body or {}).get("draft_model")


@pytest.mark.parametrize("valor", ["", "   "])
def test_rascunho_vazio_nao_envia_draft_model(monkeypatch, valor):
    monkeypatch.setenv("LLM_DRAFT_MODEL", valor)
    assert servicos.modelo_rascunho() is None
    assert not (servicos._cliente(0, 100).extra_body or {}).get("draft_model")


def test_com_rascunho_envia_draft_model(monkeypatch):
    monkeypatch.setenv("LLM_DRAFT_MODEL", " qwen2.5-0.5b-instruct ")
    assert servicos._cliente(0, 100).extra_body == {"draft_model": "qwen2.5-0.5b-instruct"}


def test_draft_model_sobrevive_ao_bind(monkeypatch):
    # Os agentes chamam .bind(response_format=...).invoke(...): o rascunho precisa seguir na requisição
    monkeypatch.setenv("LLM_DRAFT_MODEL", "qwen2.5-0.5b-instruct")
    ligado = servicos._cliente(0, 100).bind(response_format={"type": "json_object"})
    assert ligado.bound.extra_body == {"draft_model": "qwen2.5-0.5b-instruct"}


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
