"""O grafo do Manual §3.1 com os cinco agentes reais e a proteção do §3.4."""
import threading

import pytest

from src import graph, protecao
from src.agents import dossie, evidence, ingestor, socratic, synthesizer, text_analysis
from src.state import PipelineState, initial_state
from tests import modelos_falsos as falsos
from tests.evidence_fakes import mamao_fakes, patch_agent

TIMEOUT_CURTO = 1.0


def test_topologia_do_manual():
    arestas = {(a.source, a.target) for a in graph.sistema_multiagente.get_graph().edges}

    assert arestas == {
        ("__start__", "ingestor"),
        ("ingestor", "agente_evidencias"),
        ("ingestor", "agente_texto"),
        ("ingestor", "agente_socratico"),
        ("agente_evidencias", "sintetizador"),
        ("agente_texto", "sintetizador"),
        ("agente_socratico", "sintetizador"),
        ("sintetizador", "__end__"),
    }


def test_grafo_usa_os_agentes_reais_e_termina_com_todos_os_modelos_desligados():
    # o tests/conftest.py desliga os quatro modelos; sem text_report, o Sintetizador nem chama o dele
    out = graph.sistema_multiagente.invoke(initial_state(falsos.TEXTO_LIVRE))

    assert out["segments"]
    assert out["evidence"] is None
    assert out["text_report"] is None
    assert out["socratic_questions"] is None
    for ausencia in (dossie.SEM_BANCO, dossie.SEM_ESTRUTURA, dossie.SEM_PERGUNTAS):
        assert ausencia in out["dossier"]
    assert sorted(w.split(":")[0] for w in out["warnings"]) == ["evidencias", "socrático", "texto"]


def test_grafo_com_modelos_falsos_termina_sem_avisos(monkeypatch):
    falsos.ligar_falsos(monkeypatch)

    out = graph.sistema_multiagente.invoke(initial_state(falsos.TEXTO_LIVRE))

    assert out["warnings"] == []
    assert out["evidence"] == []
    assert out["text_report"].statements[0].kind == "factual"
    assert out["socratic_questions"] == falsos.PERGUNTAS_TEXTO_LIVRE
    assert falsos.RESPOSTA_SINTETIZADOR in out["dossier"]
    assert dossie.SEM_CHECAGEM in out["dossier"]


def test_caso_do_mamao_de_ponta_a_ponta(monkeypatch):
    perguntas = falsos.carregar_mamao("04_socratico_saida.json")["socratic_questions"]
    sintetizador = falsos.ligar_falsos(
        monkeypatch,
        relatorio=falsos.carregar_mamao("03_texto_saida.json")["text_report"],
        perguntas=perguntas,
    )
    _, search, classify, esperado = mamao_fakes()
    patch_agent(monkeypatch, evidence, search, classify)

    out = graph.sistema_multiagente.invoke(initial_state(falsos.carregar_mamao("00_entrada.json")["raw_input"]))

    assert search.calls, "o grafo precisa rodar o Agente de Evidências real, não o stub"
    assert out["warnings"] == []
    # o invoke devolve as saídas cruas dos nós (o Evidências devolve dicts): valida como o app.py faz
    estado = PipelineState.model_validate(out)
    assert [s.model_dump() for s in estado.segments] == falsos.carregar_mamao("01_ingestor_saida.json")["segments"]
    assert [e.model_dump() for e in estado.evidence] == esperado["evidence"]
    assert len(out["text_report"].markers) == 6
    assert out["socratic_questions"] == perguntas
    for ev in esperado["evidence"]:
        assert f'{ev["source_name"]}: {ev["agency_verdict"]}' in out["dossier"]
        assert ev["source_url"] in out["dossier"]
    for pergunta in perguntas:
        assert pergunta in out["dossier"]
    assert falsos.RESPOSTA_SINTETIZADOR in out["dossier"]
    assert len(sintetizador.prompts) == 1


def test_url_com_paywall_passa_pelo_grafo_inteiro(monkeypatch):
    sintetizador = falsos.ligar_falsos(monkeypatch)
    monkeypatch.setattr(ingestor, "fetch_page", lambda url: None)

    out = graph.sistema_multiagente.invoke(initial_state("https://exemplo-jornal.com.br/materia-fechada"))

    assert out["segments"] == []
    assert out["warnings"] == [ingestor.WARN_PAYWALL]
    assert out["evidence"] == []
    assert out["text_report"] is None
    assert out["socratic_questions"] == []
    assert out["dossier"] == dossie.SEM_TEXTO
    assert sintetizador.prompts == []


CASOS_TIMEOUT = {
    "evidencias": (evidence, "search", falsos.busca_vazia, "evidence", dossie.SEM_BANCO),
    "texto": (text_analysis, "chamar_modelo", falsos.texto_falso(falsos.RELATORIO_TEXTO_LIVRE), "text_report",
              dossie.SEM_ESTRUTURA),
    "socratico": (socratic, "chamar_modelo", falsos.socratico_falso(falsos.PERGUNTAS_TEXTO_LIVRE),
                  "socratic_questions", dossie.SEM_PERGUNTAS),
}


@pytest.mark.parametrize("ramo", sorted(CASOS_TIMEOUT))
def test_ramo_que_estoura_o_tempo_vira_aviso_e_o_dossie_sai(monkeypatch, ramo):
    falsos.ligar_falsos(monkeypatch)
    modulo, atributo, resposta, campo, ausencia = CASOS_TIMEOUT[ramo]
    liberar = threading.Event()

    def travado(*args, **kwargs):
        liberar.wait(5)
        return resposta(*args, **kwargs)

    monkeypatch.setattr(modulo, atributo, travado)
    grafo = graph.construir_grafo(timeout_ramo=TIMEOUT_CURTO)
    try:
        out = grafo.invoke(initial_state(falsos.TEXTO_LIVRE))
    finally:
        liberar.set()

    assert out[campo] is None
    assert out["warnings"] == [f"{ramo}: timeout"]
    assert ausencia in out["dossier"]   # Manual §4.7: o dossiê segue e avisa


def test_excecao_nao_prevista_num_agente_vira_aviso(monkeypatch):
    falsos.ligar_falsos(monkeypatch)

    def quebra(*args, **kwargs):
        raise ValueError("bug no lote")

    # o texto_node só trata LoteInvalido, ValidationError e ModeloIndisponivel: um ValueError escaparia
    monkeypatch.setattr(text_analysis, "dividir_em_lotes", quebra)

    out = graph.sistema_multiagente.invoke(initial_state(falsos.TEXTO_LIVRE))

    assert out["text_report"] is None
    assert out["warnings"] == ["texto: ValueError: bug no lote"]
    assert dossie.SEM_ESTRUTURA in out["dossier"]


def test_sintetizador_travado_ainda_entrega_um_dossie(monkeypatch):
    falsos.ligar_falsos(monkeypatch)   # s02 é "valor": o Sintetizador chama o modelo
    liberar = threading.Event()

    def travado(mensagens):
        liberar.wait(5)
        return falsos.RESPOSTA_SINTETIZADOR

    monkeypatch.setattr(synthesizer, "chamar_modelo", travado)
    grafo = graph.construir_grafo(timeout_sintetizador=TIMEOUT_CURTO)
    try:
        out = grafo.invoke(initial_state(falsos.TEXTO_LIVRE))
    finally:
        liberar.set()

    # spec: timeout do modelo -> fallback determinístico no argumento, não um dossiê vazio
    assert out["warnings"] == ["sintetizador: timeout"]
    assert out["dossier"] != protecao.DOSSIE_INDISPONIVEL
    assert out["dossier"].startswith(dossie.TITULO_CHECAGENS)
    assert '- Juízo de valor: "Isso não tem comprovação." é uma opinião e não foi checada.' in out["dossier"]
