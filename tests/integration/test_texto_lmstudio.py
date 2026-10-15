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


def test_texto_alarmista_mantem_os_marcadores():
    # O ajuste para desastres não pode cegar o agente para texto alarmista (saída com o prompt de 09/10)
    with open("tests/fixtures/caso_mamao_dengue/01_ingestor_saida.json", encoding="utf-8") as f:
        ingestor = json.load(f)
    relatorio = texto_node(PipelineState(**initial_state("teste", **ingestor)))["text_report"]

    encontrados = {(m.segment_id, m.type) for m in relatorio.markers}
    print(sorted(encontrados))
    assert {("s01", "urgencia_artificial"), ("s02", "adjetivacao_extrema"),
            ("s04", "apelo_autoridade"), ("s06", "urgencia_artificial")} <= encontrados


def test_noticia_de_desastre_nao_vira_adjetivacao_nem_urgencia():
    with open("tests/fixtures/bordas/texto_noticia_desastre.json", encoding="utf-8") as f:
        ingestor = json.load(f)
    state = PipelineState(**initial_state("teste", **ingestor))

    resultado = texto_node(state)

    relatorio = resultado["text_report"]
    assert relatorio is not None, resultado.get("warnings")
    proibidos = ("carbonizad", "destruíd", "pesar")
    assert not [m for m in relatorio.markers
                if m.type in ("adjetivacao_extrema", "urgencia_artificial") and any(p in m.excerpt for p in proibidos)]


def _relatorio_da_fixture(nome):
    with open(f"tests/fixtures/bordas/{nome}", encoding="utf-8") as f:
        ingestor = json.load(f)
    ingestor.pop("_sobre")
    state = PipelineState(**initial_state("teste", **ingestor))
    resultado = texto_node(state)
    relatorio = resultado["text_report"]
    assert relatorio is not None, resultado.get("warnings")
    print(json.dumps([m.model_dump() for m in relatorio.markers], ensure_ascii=False, indent=2))
    return relatorio


# max_fp: frases de contexto com algum marcador que ainda toleramos. No conjunto variado, o prompt de
# 09/10 marcava 8 das 9; com o exemplo de desastre (15/10) sobra 1 ("terremoto brutal").
@pytest.mark.parametrize("fixture, contexto, julgamento, termo, max_fp", [
    ("texto_noticia_deslizamento.json", ["s01", "s02", "s03"], "s04", "criminosa", 0),
    ("texto_desastres_variados.json", [f"s{i:02d}" for i in range(1, 10)], "s10", "incompetentes", 1),
])
def test_desastre_intensidade_de_contexto_nao_e_marcador_e_julgamento_e(fixture, contexto, julgamento, termo, max_fp):
    relatorio = _relatorio_da_fixture(fixture)

    assert len({m.segment_id for m in relatorio.markers if m.segment_id in contexto}) <= max_fp
    assert [m for m in relatorio.markers
            if m.type == "adjetivacao_extrema" and m.segment_id == julgamento and termo in m.excerpt]
