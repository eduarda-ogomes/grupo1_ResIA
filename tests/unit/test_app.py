from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[2] / "app" / "app.py")


def analisar(texto):
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.text_area[0].set_value(texto)
    at.button[0].click()
    at.run()
    return at


def test_app_analisa_texto_sem_excecao():
    at = analisar("O suco de mamão cura a dengue. Isso não tem comprovação.")

    assert not at.exception
    assert at.header[0].value == "Texto Inserido Manualmente"
    assert any("Frases segmentadas" in e.label for e in at.expander)


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
