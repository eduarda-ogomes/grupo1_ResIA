import json

from src.agents import text_analysis
from src.graph import sistema_multiagente
from src.state import PipelineState, initial_state


def test_initial_state_valida_no_schema_estrito():
    state = PipelineState(**initial_state("uma noticia"))

    assert state.raw_input == "uma noticia"
    assert state.segments == []
    assert state.warnings == []
    assert state.evidence is None
    assert state.dossier is None


def test_initial_state_aceita_sobrescritas():
    state = PipelineState(**initial_state("x", clean_text="texto", truncated=True))

    assert state.clean_text == "texto"
    assert state.truncated is True


def test_grafo_roda_ponta_a_ponta_com_texto_livre(monkeypatch):
    def modelo_falso(mensagens):
        return json.dumps({
            "statements": [{"segment_id": "s01", "kind": "factual"}, {"segment_id": "s02", "kind": "factual"}],
            "markers": [],
        })

    monkeypatch.setattr(text_analysis, "chamar_modelo", modelo_falso)

    out = sistema_multiagente.invoke(
        initial_state("O suco de mamão cura a dengue. Isso não tem comprovação.")
    )

    assert out["segments"]
    assert out["dossier"]
    assert out["text_report"].statements[0].kind == "factual"
    assert out["warnings"] == []


def test_grafo_segue_quando_o_agente_de_texto_falha():
    # o conftest deixa o modelo "desligado": o texto devolve None + aviso e o grafo termina
    out = sistema_multiagente.invoke(initial_state("Uma frase qualquer. Outra frase."))

    assert out["text_report"] is None
    assert out["dossier"]
    assert out["warnings"] == [text_analysis.WARN_MODELO_INDISPONIVEL]


def test_initial_state_cobre_exatamente_os_campos_do_schema():
    # Falha se alguém mudar o PipelineState sem atualizar initial_state (ver aviso em src/state.py)
    assert set(initial_state("x")) == set(PipelineState.model_fields)
