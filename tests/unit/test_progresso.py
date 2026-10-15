"""Progresso da análise para a sala dos agentes: quem espera, quem trabalha, quem terminou."""
import json

import pytest

from src.pipeline.graph import ORDEM_NOS
from src.pipeline.progresso import AGENTES, Progresso


def estados(p):
    return {a["id"]: a["estado"] for a in p.para_a_sala()["agentes"]}


def test_agentes_na_ordem_do_grafo():
    assert AGENTES == ("ingestor", "agente_evidencias", "agente_texto", "agente_socratico", "sintetizador")


def test_no_inicio_so_o_ingestor_trabalha():
    assert estados(Progresso("a1")) == {
        "ingestor": "trabalhando", "agente_evidencias": "aguardando", "agente_texto": "aguardando",
        "agente_socratico": "aguardando", "sintetizador": "aguardando"}


def test_um_personagem_por_no_do_grafo():
    assert AGENTES == ORDEM_NOS


def test_fim_do_ingestor_libera_os_tres_ramos():
    p = Progresso("a1")
    p.terminou("ingestor", 0.1, [])

    assert estados(p) == {
        "ingestor": "concluido", "agente_evidencias": "trabalhando", "agente_texto": "trabalhando",
        "agente_socratico": "trabalhando", "sintetizador": "aguardando"}


def test_sintetizador_espera_os_tres_ramos():
    p = Progresso("a1")
    p.terminou("ingestor", 0.1, [])
    p.terminou("agente_evidencias", 0.8, [])
    p.terminou("agente_socratico", 7.0, [])
    assert estados(p)["sintetizador"] == "aguardando"

    p.terminou("agente_texto", 15.0, [])
    assert estados(p)["sintetizador"] == "trabalhando"
    assert p.para_a_sala()["concluida"] is False

    p.terminou("sintetizador", 15.1, [])
    assert set(estados(p).values()) == {"concluido"}
    assert p.para_a_sala()["concluida"] is True


def test_duracao_de_cada_agente_respeita_o_paralelismo():
    p = Progresso("a1")
    for no, fim in [("ingestor", 1.0), ("agente_evidencias", 2.0), ("agente_socratico", 8.0),
                    ("agente_texto", 15.0), ("sintetizador", 15.1)]:
        p.terminou(no, fim, [])

    segundos = {a["id"]: a["segundos"] for a in p.para_a_sala()["agentes"]}
    assert segundos == pytest.approx({"ingestor": 1.0, "agente_evidencias": 1.0, "agente_texto": 14.0,
                                      "agente_socratico": 7.0, "sintetizador": 0.1})


def test_avisos_ficam_com_o_agente_que_os_deu():
    p = Progresso("a1")
    p.terminou("ingestor", 0.1, [])
    p.terminou("agente_texto", 5.0, ["texto: falha ao chamar o modelo"])

    agentes = {a["id"]: a for a in p.para_a_sala()["agentes"]}
    assert agentes["agente_texto"]["avisos"] == ["texto: falha ao chamar o modelo"]
    assert agentes["agente_evidencias"]["avisos"] == []


def test_interrompida_para_quem_ainda_trabalhava():
    p = Progresso("a1")
    p.terminou("ingestor", 0.1, [])
    p.terminou("agente_evidencias", 0.8, [])
    p.interromper()

    sala = p.para_a_sala()
    assert sala["interrompida"] is True
    assert estados(p) == {
        "ingestor": "concluido", "agente_evidencias": "concluido", "agente_texto": "interrompido",
        "agente_socratico": "interrompido", "sintetizador": "aguardando"}


def test_interrompida_com_os_tres_ramos_prontos_para_o_sintetizador():
    p = Progresso("a1")
    for no in ("ingestor", "agente_evidencias", "agente_texto", "agente_socratico"):
        p.terminou(no, 1.0, [])
    p.interromper()

    assert estados(p)["sintetizador"] == "interrompido"


def test_dados_da_sala_sao_json_e_levam_o_id_da_analise():
    p = Progresso("analise-42")
    p.terminou("ingestor", 0.1, ["ingestor: paywall"])

    sala = json.loads(json.dumps(p.para_a_sala()))
    assert sala["analise"] == "analise-42"
    assert sala["concluida"] is False and sala["interrompida"] is False
    assert [a["id"] for a in sala["agentes"]] == list(AGENTES)
