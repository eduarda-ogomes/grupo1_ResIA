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


def test_grafo_roda_ponta_a_ponta_com_texto_livre():
    out = sistema_multiagente.invoke(
        initial_state("O suco de mamão cura a dengue. Isso não tem comprovação.")
    )

    assert out["segments"]
    assert out["dossier"]
    assert out["warnings"] == []
