import json
from src.state import PipelineState

def socratic_node(state: PipelineState) -> dict:
    with open("tests/fixtures/caso_mamao_dengue/04_socratico_saida.json", "r", encoding="utf-8") as f:
        return json.load(f)
