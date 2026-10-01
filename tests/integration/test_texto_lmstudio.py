"""Roda o Agente de Texto contra o LM Studio de verdade.

Não roda no CI. Rode localmente com o LM Studio ligado:
    pytest tests/integration/test_texto_lmstudio.py -v -s
"""
import json

import pytest
import requests

from src.agents.text_analysis import texto_node
from src.state import PipelineState, initial_state


def lm_studio_no_ar():
    try:
        return requests.get("http://localhost:1234/v1/models", timeout=2).ok
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(not lm_studio_no_ar(), reason="LM Studio não está rodando em localhost:1234")


def test_caso_mamao_com_modelo_real():
    with open("tests/fixtures/caso_mamao_dengue/01_ingestor_saida.json", encoding="utf-8") as f:
        ingestor = json.load(f)
    state = PipelineState(**initial_state("teste", **ingestor))

    resultado = texto_node(state)

    relatorio = resultado["text_report"]
    assert relatorio is not None, resultado.get("warnings")
    assert [st.segment_id for st in relatorio.statements] == [s.id for s in state.segments]
    textos = {s.id: s.text for s in state.segments}
    for marcador in relatorio.markers:
        assert marcador.excerpt in textos[marcador.segment_id]
    print(json.dumps(relatorio.model_dump(), ensure_ascii=False, indent=2))
