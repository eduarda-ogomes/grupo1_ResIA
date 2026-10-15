import json
import re
from pathlib import Path

import pytest

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[2] / "app" / "app.py")


def pagina_analisar():
    at = AppTest.from_file(APP, default_timeout=120)
    at.query_params["page"] = "analisar"
    return at


def analisar(texto):
    at = pagina_analisar()
    at.run()
    at.text_area[0].set_value(texto)
    at.button[0].click()
    at.run()
    return at


def test_app_analisa_texto_sem_excecao():
    at = analisar("O suco de mamão cura a dengue. Isso não tem comprovação.")

    assert not at.exception
    assert any("Texto Inserido Manualmente" in m.value for m in at.markdown)
    assert any("Todas as frases analisadas" in e.label for e in at.expander)


def test_app_mostra_aviso_quando_ingestor_nao_extrai(monkeypatch):
    from src.agents import ingestor

    monkeypatch.setattr(ingestor, "fetch_page", lambda url: None)

    at = analisar("https://exemplo-jornal.com.br/materia-fechada")

    assert not at.exception
    assert any("paywall" in w.value for w in at.warning)
    assert any("não extraiu nenhum texto" in e.value for e in at.error)

def test_app_mostra_aviso_quando_o_agente_de_texto_falha():
    # o conftest deixa o modelo "desligado"
    at = analisar("O suco de mamão cura a dengue. Isso não tem comprovação.")

    assert not at.exception
    assert any("texto: falha ao chamar o modelo" in w.value for w in at.warning)


def test_app_mostra_o_aviso_de_cada_ramo_que_falhou():
    # o tests/conftest.py desliga os quatro modelos
    at = analisar("O suco de mamão cura a dengue. Isso não tem comprovação.")

    assert not at.exception
    avisos = " ".join(w.value for w in at.warning)
    for prefixo in ("evidencias:", "texto:", "socrático:"):
        assert prefixo in avisos


def test_app_cita_o_lm_studio_e_nao_o_ollama(monkeypatch):
    from src.pipeline import medicao

    def falha(*args, **kwargs):
        raise RuntimeError("modelo fora do ar")

    monkeypatch.setattr(medicao, "executar", falha)

    at = analisar("O suco de mamão cura a dengue. Isso não tem comprovação.")

    assert any("LM Studio" in i.value for i in at.info)
    textos = " ".join(m.value for m in [*at.markdown, *at.info, *at.error])
    assert "Ollama" not in textos


def test_perguntas_aparecem_uma_vez_so_dentro_do_dossie(monkeypatch):
    from tests import modelos_falsos as falsos

    falsos.ligar_falsos(monkeypatch)

    at = analisar(falsos.TEXTO_LIVRE)

    assert not at.exception
    for pergunta in falsos.PERGUNTAS_TEXTO_LIVRE:
        onde = [m.value for m in at.markdown if pergunta in m.value]
        assert len(onde) == 1, f"a pergunta aparece {len(onde)} vezes na tela"
        assert "## Perguntas para pensar antes de decidir" in onde[0]
    assert not any(s.value == "Perguntas Socráticas" for s in at.subheader)


# --- observabilidade: tempos por etapa e trace ---

def _tabela_de_tempos(at):
    return next(t.value for t in at.table if "nó" in t.value.columns)


def test_app_mostra_tempos_por_etapa(monkeypatch):
    from tests import modelos_falsos as falsos

    falsos.ligar_falsos(monkeypatch)

    at = analisar(falsos.TEXTO_LIVRE)

    assert not at.exception
    assert any(e.label == "Detalhes técnicos" for e in at.expander)
    assert list(_tabela_de_tempos(at)["nó"]) == [
        "ingestor", "agente_evidencias", "agente_texto", "agente_argumento", "agente_socratico", "sintetizador", "total"]


def test_app_mostra_tempos_sem_trace_quando_tracing_desligado(monkeypatch):
    from tests import modelos_falsos as falsos

    from src.pipeline import medicao

    falsos.ligar_falsos(monkeypatch)
    monkeypatch.delenv("PHOENIX_TRACING", raising=False)
    # Tracing desligado = contexto de span inválido = trace_id None. Simulado aqui porque outro
    # teste da sessão pode já ter registrado o provider global (fixture `spans`), que não se desfaz.
    monkeypatch.setattr(medicao, "trace_id_de", lambda contexto: None)

    at = analisar(falsos.TEXTO_LIVRE)

    assert any(e.label == "Detalhes técnicos" for e in at.expander)
    assert not any("Phoenix" in c.value for c in at.caption)


def test_app_mostra_o_trace_quando_ha_trace_id(monkeypatch):
    from src.pipeline import medicao
    from tests import modelos_falsos as falsos

    falsos.ligar_falsos(monkeypatch)
    monkeypatch.setattr(medicao, "trace_id_de", lambda contexto: "0af7651916cd43dd8448eb211c80319c")

    at = analisar(falsos.TEXTO_LIVRE)

    assert any("0af7651916cd43dd8448eb211c80319c" in c.value and "Phoenix" in c.value for c in at.caption)


def test_app_mostra_so_o_dossie_e_os_expanders():
    at = analisar("O suco de mamão cura a dengue. Isso não tem comprovação.")
    assert not at.exception
    assert [s.value for s in at.subheader] == []
    rotulos = [e.label for e in at.expander]
    assert any(r.startswith("Todas as frases analisadas (") for r in rotulos)
    assert "Detalhes técnicos" in rotulos


SEM_NOTICIA = "Nenhuma notícia enviada"


def test_dica_de_exemplo_aparece_antes_de_analisar():
    at = pagina_analisar()
    at.run()

    assert any(SEM_NOTICIA in m.value for m in at.markdown)


def test_dica_de_exemplo_some_ao_gerar_o_dossie():
    at = analisar("O suco de mamão cura a dengue. Isso não tem comprovação.")

    assert not at.exception
    assert not any(SEM_NOTICIA in m.value for m in at.markdown)


# --- sala dos agentes (app/sala/) ---

def _componentes(at, nome):
    return [c for c in at.get("bidi_component") if c.proto.component_name == nome]


def _sala(at):
    salas = _componentes(at, "sala_agentes")
    assert len(salas) == 1, "a sala aparece uma vez só"
    return json.loads(salas[0].proto.json)


def test_sala_mostra_todos_os_agentes_concluidos_no_fim(monkeypatch):
    from tests import modelos_falsos as falsos

    falsos.ligar_falsos(monkeypatch)

    at = analisar(falsos.TEXTO_LIVRE)

    assert not at.exception
    sala = _sala(at)
    assert sala["concluida"] is True and sala["interrompida"] is False
    assert [a["id"] for a in sala["agentes"]] == [
        "ingestor", "agente_evidencias", "agente_texto", "agente_socratico", "sintetizador"]
    assert {a["estado"] for a in sala["agentes"]} == {"concluido"}


def test_sala_mostra_os_avisos_de_cada_agente():
    # o tests/conftest.py desliga os modelos: os ramos terminam com aviso
    at = analisar("O suco de mamão cura a dengue. Isso não tem comprovação.")

    agentes = {a["id"]: a for a in _sala(at)["agentes"]}
    assert any(aviso.startswith("texto:") for aviso in agentes["agente_texto"]["avisos"])


def test_sala_fica_interrompida_quando_a_analise_falha(monkeypatch):
    from src.pipeline import medicao

    def falha(*args, **kwargs):
        raise RuntimeError("modelo fora do ar")

    monkeypatch.setattr(medicao, "executar", falha)

    at = analisar("O suco de mamão cura a dengue. Isso não tem comprovação.")

    sala = _sala(at)
    assert sala["interrompida"] is True
    assert {a["id"]: a["estado"] for a in sala["agentes"]}["ingestor"] == "interrompido"


def test_sala_nao_aparece_antes_de_analisar():
    at = pagina_analisar()
    at.run()

    assert not _componentes(at, "sala_agentes")


def test_sala_soma_o_argumento_no_sintetizador(monkeypatch):
    # A sala tem cinco personagens: o nó agente_argumento é desenhado pelo Sintetizador,
    # que leva o tempo e os avisos dos dois nós (src/pipeline/progresso.py)
    from src.pipeline import medicao

    eventos = [
        {"ingestor": {"clean_text": "Uma frase.", "segments": [{"id": "s01", "text": "Uma frase."}]}},
        {"agente_evidencias": {"evidence": []}},
        {"agente_texto": {"text_report": None}},
        {"agente_socratico": {"socratic_questions": None}},
        {"agente_argumento": {"argument": None, "warnings": ["argumento: tempo esgotado"]}},
        {"sintetizador": {"dossier": "## Limites desta análise"}},
    ]

    class GrafoFalso:
        def stream(self, estado):
            yield from eventos

    tempos = iter([0, 1, 2, 10, 14, 15, 15.5])
    executar_de_verdade = medicao.executar

    def executar_falso(grafo, estado, ao_terminar_no=None):
        return executar_de_verdade(GrafoFalso(), estado, relogio=lambda: next(tempos), ao_terminar_no=ao_terminar_no)

    monkeypatch.setattr(medicao, "executar", executar_falso)

    at = analisar("Uma frase.")

    assert not at.exception
    sintetizador = {a["id"]: a for a in _sala(at)["agentes"]}["sintetizador"]
    assert sintetizador["estado"] == "concluido"
    assert sintetizador["segundos"] == 5.5  # argumento 5 s depois do texto + sintetizador 0,5 s
    assert sintetizador["avisos"] == ["argumento: tempo esgotado"]


# --- tema claro/escuro (app/tema/) ---

COR_HEX = re.compile(r"#[0-9A-Fa-f]{3}(?:[0-9A-Fa-f]{3})?\b")


def _pagina(pagina):
    at = AppTest.from_file(APP, default_timeout=120)
    at.query_params["page"] = pagina
    at.run()
    return at


@pytest.mark.parametrize("pagina", ["home", "analisar"])
def test_botao_de_tema_aparece_na_navbar(pagina):
    at = _pagina(pagina)

    assert not at.exception
    assert any('class="botao-tema"' in m.value for m in at.markdown)
    assert len(_componentes(at, "alternador_tema")) == 1


@pytest.mark.parametrize("pagina", ["home", "analisar"])
def test_pagina_traz_as_cores_do_tema_escuro(pagina):
    at = _pagina(pagina)

    assert any('[data-tema="escuro"]' in m.value for m in at.markdown)


def test_app_nao_tem_cor_fixa_fora_do_tema():
    # Cor fixa no app.py não muda com o tema: toda cor vem das variáveis de app/tema/tema.css
    codigo = Path(APP).read_text(encoding="utf-8")

    assert COR_HEX.findall(codigo) == []


def test_moldura_da_sala_segue_o_tema():
    # Só a ilustração (parede da cena e balão do Sintetizador, com o texto vinho) mantém cores próprias
    css = (Path(APP).parent / "sala" / "sala.css").read_text(encoding="utf-8")

    assert set(COR_HEX.findall(css)) <= {"#F3ECE2", "#FFFDF8", "#2B2024", "#7C2128"}


@pytest.mark.parametrize("pagina", ["home", "analisar"])
def test_logo_tem_versao_para_o_tema_escuro(pagina):
    # O logo original tem letras pretas, que somem no fundo escuro
    at = _pagina(pagina)

    navbar = next(m.value for m in at.markdown if 'class="header-nav"' in m.value)
    assert 'class="logo logo-claro"' in navbar
    assert 'class="logo logo-escuro"' in navbar
