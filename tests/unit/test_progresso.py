"""Progresso da análise para a sala dos agentes: quem espera, quem trabalha, quem terminou."""
import json

import pytest

from src.pipeline.graph import ORDEM_NOS
from src.pipeline.progresso import AGENTES, NOS_DO_AGENTE, Progresso


def estados(p):
    return {a["id"]: a["estado"] for a in p.para_a_sala()["agentes"]}


def test_agentes_na_ordem_do_grafo():
    assert AGENTES == ("ingestor", "agente_evidencias", "agente_texto", "agente_socratico", "sintetizador")


def test_no_inicio_so_o_ingestor_trabalha():
    assert estados(Progresso("a1")) == {
        "ingestor": "trabalhando", "agente_evidencias": "aguardando", "agente_texto": "aguardando",
        "agente_socratico": "aguardando", "sintetizador": "aguardando"}


def test_personagens_cobrem_todos_os_nos_do_grafo():
    nos = [no for a in AGENTES for no in NOS_DO_AGENTE[a]]
    assert sorted(nos) == sorted(ORDEM_NOS)
    assert NOS_DO_AGENTE["sintetizador"] == ("agente_argumento", "sintetizador")


def test_fim_do_ingestor_libera_evidencias_e_texto():
    p = Progresso("a1")
    p.terminou("ingestor", 0.1, [])

    assert estados(p) == {
        "ingestor": "concluido", "agente_evidencias": "trabalhando", "agente_texto": "trabalhando",
        "agente_socratico": "aguardando", "sintetizador": "aguardando"}


def test_fim_do_texto_libera_socratico_e_sintetizador():
    # o Sintetizador desenha o agente_argumento, que começa junto com o Socrático
    p = Progresso("a1")
    p.terminou("ingestor", 0.1, [])
    p.terminou("agente_texto", 9.0, [])

    assert estados(p) == {
        "ingestor": "concluido", "agente_evidencias": "trabalhando", "agente_texto": "concluido",
        "agente_socratico": "trabalhando", "sintetizador": "trabalhando"}


def test_sintetizador_trabalha_do_argumento_ate_o_fim_do_no_sintetizador():
    p = Progresso("a1")
    p.terminou("ingestor", 0.1, [])
    p.terminou("agente_evidencias", 0.8, [])
    p.terminou("agente_texto", 9.0, [])
    p.terminou("agente_argumento", 14.0, [])
    assert estados(p)["sintetizador"] == "trabalhando"
    assert p.para_a_sala()["concluida"] is False

    p.terminou("agente_socratico", 15.0, [])
    assert estados(p)["sintetizador"] == "trabalhando"

    p.terminou("sintetizador", 15.1, [])
    assert set(estados(p).values()) == {"concluido"}
    assert p.para_a_sala()["concluida"] is True


def test_duracao_de_cada_agente_respeita_o_paralelismo():
    p = Progresso("a1")
    p.terminou("ingestor", 1.0, [])
    p.terminou("agente_texto", 9.0, [])
    p.terminou("agente_socratico", 12.0, [])

    segundos = {a["id"]: a["segundos"] for a in p.para_a_sala()["agentes"]}
    assert segundos == {"ingestor": 1.0, "agente_evidencias": None, "agente_texto": 8.0,
                        "agente_socratico": 3.0, "sintetizador": None}


def test_tempo_do_sintetizador_soma_argumento_e_sintetizador():
    p = Progresso("a1")
    for no, fim in [("ingestor", 1.0), ("agente_evidencias", 2.0), ("agente_texto", 10.0),
                    ("agente_argumento", 15.0), ("agente_socratico", 14.0), ("sintetizador", 15.1)]:
        p.terminou(no, fim, [])

    segundos = {a["id"]: a["segundos"] for a in p.para_a_sala()["agentes"]}
    # argumento 5,0 s (depois do texto) + sintetizador 0,1 s (depois do último dos três)
    assert segundos["sintetizador"] == pytest.approx(5.1)
    assert segundos["agente_socratico"] == pytest.approx(4.0)


def test_tempo_do_sintetizador_so_com_o_argumento():
    p = Progresso("a1")
    p.terminou("ingestor", 1.0, [])
    p.terminou("agente_texto", 10.0, [])
    p.terminou("agente_argumento", 15.0, [])

    sintetizador = p.para_a_sala()["agentes"][-1]
    assert sintetizador["estado"] == "trabalhando"
    assert sintetizador["segundos"] == pytest.approx(5.0)


def test_avisos_ficam_com_o_agente_que_os_deu():
    p = Progresso("a1")
    p.terminou("ingestor", 0.1, [])
    p.terminou("agente_texto", 5.0, ["texto: falha ao chamar o modelo"])

    agentes = {a["id"]: a for a in p.para_a_sala()["agentes"]}
    assert agentes["agente_texto"]["avisos"] == ["texto: falha ao chamar o modelo"]
    assert agentes["agente_evidencias"]["avisos"] == []


def test_avisos_do_argumento_e_do_sintetizador_vao_para_o_sintetizador():
    p = Progresso("a1")
    p.terminou("ingestor", 0.1, [])
    p.terminou("agente_texto", 5.0, [])
    p.terminou("agente_argumento", 9.0, ["argumento: tempo esgotado"])
    p.terminou("sintetizador", 9.1, ["sintetizador: z"])

    agentes = {a["id"]: a for a in p.para_a_sala()["agentes"]}
    assert agentes["sintetizador"]["avisos"] == ["argumento: tempo esgotado", "sintetizador: z"]


def test_interrompida_para_quem_ainda_trabalhava():
    p = Progresso("a1")
    p.terminou("ingestor", 0.1, [])
    p.terminou("agente_evidencias", 0.8, [])
    p.interromper()

    sala = p.para_a_sala()
    assert sala["interrompida"] is True
    assert estados(p) == {
        "ingestor": "concluido", "agente_evidencias": "concluido", "agente_texto": "interrompido",
        "agente_socratico": "aguardando", "sintetizador": "aguardando"}


def test_interrompida_depois_do_texto_para_socratico_e_sintetizador():
    p = Progresso("a1")
    p.terminou("ingestor", 0.1, [])
    p.terminou("agente_evidencias", 0.8, [])
    p.terminou("agente_texto", 9.0, [])
    p.interromper()

    assert estados(p)["agente_socratico"] == "interrompido"
    assert estados(p)["sintetizador"] == "interrompido"


def test_dados_da_sala_sao_json_e_levam_o_id_da_analise():
    p = Progresso("analise-42")
    p.terminou("ingestor", 0.1, ["ingestor: paywall"])

    sala = json.loads(json.dumps(p.para_a_sala()))
    assert sala["analise"] == "analise-42"
    assert sala["concluida"] is False and sala["interrompida"] is False
    assert [a["id"] for a in sala["agentes"]] == list(AGENTES)
