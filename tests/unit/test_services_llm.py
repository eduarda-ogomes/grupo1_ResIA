import pytest

from src.services import llm as servicos


@pytest.mark.parametrize("nome", ["llm", "llm_socratico", "llm_texto"])
def test_clientes_tem_timeout_e_nao_repetem_a_chamada(nome):
    # Sem timeout, uma chamada abandonada pelo grafo (src/protecao.py) ocuparia o LM Studio indefinidamente
    cliente = getattr(servicos, nome)

    assert cliente.request_timeout == 120
    assert cliente.max_retries == 0


def test_temperaturas():
    assert (servicos.llm.temperature, servicos.llm_socratico.temperature, servicos.llm_texto.temperature) == (0, 0.7, 0)
