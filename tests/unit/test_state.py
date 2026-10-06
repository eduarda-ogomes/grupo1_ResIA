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


def test_initial_state_cobre_exatamente_os_campos_do_schema():
    # Falha se alguém mudar o PipelineState sem atualizar initial_state (ver aviso em src/state.py)
    assert set(initial_state("x")) == set(PipelineState.model_fields)
