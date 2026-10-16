import json
from src.state import PipelineState

def ingestor_node(state: PipelineState) -> dict:
    with open("tests/fixtures/caso_mamao_dengue/01_ingestor_saida.json", "r", encoding="utf-8") as f:
        return json.load(f)
