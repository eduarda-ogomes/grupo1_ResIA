from pathlib import Path

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
    from src import medicao

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
        "ingestor", "agente_evidencias", "agente_texto", "agente_socratico", "sintetizador", "total"]


def test_app_mostra_tempos_sem_trace_quando_tracing_desligado(monkeypatch):
    from tests import modelos_falsos as falsos

    from src import medicao

    falsos.ligar_falsos(monkeypatch)
    monkeypatch.delenv("PHOENIX_TRACING", raising=False)
    # Tracing desligado = contexto de span inválido = trace_id None. Simulado aqui porque outro
    # teste da sessão pode já ter registrado o provider global (fixture `spans`), que não se desfaz.
    monkeypatch.setattr(medicao, "trace_id_de", lambda contexto: None)

    at = analisar(falsos.TEXTO_LIVRE)

    assert any(e.label == "Detalhes técnicos" for e in at.expander)
    assert not any("Phoenix" in c.value for c in at.caption)


def test_app_mostra_o_trace_quando_ha_trace_id(monkeypatch):
    from src import medicao
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
