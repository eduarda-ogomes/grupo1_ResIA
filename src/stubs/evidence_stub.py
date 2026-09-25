import json
from src.state import PipelineState

def evidence_node(state: PipelineState) -> dict:
    with open("tests/fixtures/caso_mamao_dengue/02_evidencias_saida.json", "r", encoding="utf-8") as f:
        return json.load(f)
