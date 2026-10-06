"""Timeout por nó e degradação graciosa (Manual §3.4 e §4.7, linha "Sistema")."""
import json
import threading
import time
from pathlib import Path

import pytest

from src import protecao

FIXTURE_TIMEOUT = Path(__file__).resolve().parents[1] / "fixtures" / "bordas" / "sistema_timeout_ramo.json"


def test_saida_do_agente_passa_sem_mudanca():
    saida = {"text_report": None, "warnings": ["texto: saída inválida após 1 retry"]}
    no = protecao.proteger("texto", lambda state: saida, 1, {"text_report": None})

    assert no(object()) == saida


def test_timeout_devolve_a_saida_da_fixture_sem_esperar_o_agente():
    liberar = threading.Event()

    def socratico_travado(state):
        liberar.wait(5)
        return {"socratic_questions": ["nunca chega a tempo"]}

    no = protecao.proteger("socratico", socratico_travado, 0.1, {"socratic_questions": None})
    inicio = time.monotonic()
    try:
        saida = no(object())
    finally:
        liberar.set()

    assert time.monotonic() - inicio < 1, "o nó não pode esperar a thread travada"
    assert saida == json.loads(FIXTURE_TIMEOUT.read_text(encoding="utf-8"))["saida_esperada"]


def test_excecao_vira_aviso():
    def quebra(state):
        raise ValueError("índice corrompido")

    no = protecao.proteger("evidencias", quebra, 1, {"evidence": None})

    assert no(object()) == {"evidence": None, "warnings": ["evidencias: ValueError: índice corrompido"]}


def test_saida_de_falha_e_uma_copia_nova_a_cada_chamada():
    def quebra(state):
        raise RuntimeError("x")

    no = protecao.proteger("ingestor", quebra, 1, protecao.FALHA_INGESTOR)
    primeira = no(object())
    primeira["segments"].append("lixo")

    assert no(object())["segments"] == []
    assert protecao.FALHA_INGESTOR["segments"] == []


def test_timeout_lido_da_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("GRAFO_TIMEOUT_RAMO", "12.5")
    assert protecao.ler_timeout("GRAFO_TIMEOUT_RAMO", 240) == 12.5

    monkeypatch.delenv("GRAFO_TIMEOUT_RAMO")
    assert protecao.ler_timeout("GRAFO_TIMEOUT_RAMO", 240) == 240


@pytest.mark.parametrize("valor", ["abc", "", "0", "-5", "inf", "nan"])
def test_timeout_invalido_usa_o_padrao(monkeypatch, valor):
    monkeypatch.setenv("GRAFO_TIMEOUT_RAMO", valor)

    assert protecao.ler_timeout("GRAFO_TIMEOUT_RAMO", 240) == 240


def test_timeouts_padrao():
    assert (protecao.TIMEOUT_INGESTOR_S, protecao.TIMEOUT_RAMO_S, protecao.TIMEOUT_SINTETIZADOR_S) == (60, 240, 180)


def test_timeout_usa_recuperar_para_montar_a_saida():
    # O Sintetizador estourou o tempo esperando o LLM: o dossiê sai montado sem o modelo
    liberar = threading.Event()

    def lento(state):
        liberar.wait(5)
        return {"dossier": "atrasado"}

    def recuperar(state):
        return {"dossier": f"sem modelo: {state}", "warnings": ["sintetizador: citação removida"]}

    no = protecao.proteger("sintetizador", lento, 0.1, {"dossier": "indisponível"}, recuperar=recuperar)
    try:
        saida = no("estado")
    finally:
        liberar.set()

    assert saida == {"dossier": "sem modelo: estado",
                     "warnings": ["sintetizador: timeout", "sintetizador: citação removida"]}


def test_recuperar_que_falha_cai_na_saida_fixa():
    def quebra(state):
        raise RuntimeError("a")

    def recuperar_quebrado(state):
        raise ValueError("b")

    no = protecao.proteger("sintetizador", quebra, 1, {"dossier": "indisponível"}, recuperar=recuperar_quebrado)

    assert no(None) == {"dossier": "indisponível", "warnings": ["sintetizador: RuntimeError: a"]}


def test_timeout_enorme_e_limitado_ao_maximo_da_plataforma(monkeypatch):
    # "1e10" passaria no isfinite, mas futuro.result(timeout=1e10) levanta OverflowError em todo nó
    monkeypatch.setenv("GRAFO_TIMEOUT_RAMO", "1e10")

    assert protecao.ler_timeout("GRAFO_TIMEOUT_RAMO", 240) == threading.TIMEOUT_MAX


def test_proteger_aceita_o_timeout_maximo():
    no = protecao.proteger("texto", lambda state: {"text_report": None}, threading.TIMEOUT_MAX, {"text_report": None})

    assert no(None) == {"text_report": None}
