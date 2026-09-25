import json
from src.state import PipelineState
from src.stubs.ingestor_stub import ingestor_node
from src.stubs.evidence_stub import evidence_node
from src.stubs.text_stub import text_node
from src.stubs.socratic_stub import socratic_node
from src.stubs.synthesizer_stub import synthesizer_node

def load_fixture(name):
    with open(f"tests/fixtures/caso_mamao_dengue/{name}", "r", encoding="utf-8") as f:
        return json.load(f)

def test_ingestor_contract():
    state = PipelineState(raw_input="test")
    result = ingestor_node(state)
    
    # Valida usando o schema Pydantic
    dump = state.model_dump()
    dump.update(result)
    merged = PipelineState(**dump)
    
    assert merged.truncated is False
    assert len(merged.segments) == 6
    assert merged.segments[0].id == "s01"

def test_evidence_contract():
    base_data = load_fixture("01_ingestor_saida.json")
    state = PipelineState(raw_input="test", **base_data)
    
    result = evidence_node(state)
    assert "evidence" in result
    
    dump = state.model_dump()
    dump["evidence"] = dump.get("evidence", []) + result["evidence"]
    merged = PipelineState(**dump)
    
    assert len(merged.evidence) == 2
    assert merged.evidence[0].stance == "contradiz"

def test_text_contract():
    base_data = load_fixture("01_ingestor_saida.json")
    state = PipelineState(raw_input="test", **base_data)
    
    result = text_node(state)
    assert "text_report" in result
    
    dump = state.model_dump()
    dump.update(result)
    merged = PipelineState(**dump)
    
    assert len(merged.text_report.statements) == 6
    assert len(merged.text_report.markers) == 6
    assert merged.text_report.markers[0].type == "urgencia_artificial"

def test_socratic_contract():
    base_data = load_fixture("01_ingestor_saida.json")
    state = PipelineState(raw_input="test", **base_data)
    
    result = socratic_node(state)
    assert "socratic_questions" in result
    
    dump = state.model_dump()
    dump.update(result)
    merged = PipelineState(**dump)
    
    assert len(merged.socratic_questions) == 3

def test_synthesizer_contract():
    base_data = load_fixture("05_sintetizador_entrada.json")
    state = PipelineState(**base_data)
    
    result = synthesizer_node(state)
    assert "dossier" in result
    
    dump = state.model_dump()
    dump.update(result)
    merged = PipelineState(**dump)
    
    assert merged.dossier is not None
    assert isinstance(merged.warnings, list)
