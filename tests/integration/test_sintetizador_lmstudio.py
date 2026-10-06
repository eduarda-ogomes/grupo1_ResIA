"""Roda o Sintetizador contra o qwen2.5-7b de verdade, no caso do mamão.

Não roda no CI. Rode da raiz, com o LM Studio ligado:
    pytest tests/integration/test_sintetizador_lmstudio.py -v -s
Não compara texto exato: confere as 4 seções e os dois guardrails.
"""
import json
from pathlib import Path

import pytest
import requests

from src.agents import dossie
from src.agents.synthesizer import sintetizador_node
from src.guardrails.citacoes import extrair_urls
from src.guardrails.veredito import termos_de_veredito
from src.state import PipelineState

ENTRADA = Path(__file__).resolve().parents[1] / "fixtures" / "caso_mamao_dengue" / "05_sintetizador_entrada.json"


def lm_studio_no_ar():
    try:
        return requests.get("http://localhost:1234/v1/models", timeout=2).ok
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(not lm_studio_no_ar(), reason="LM Studio não está rodando em localhost:1234")


def test_caso_do_mamao_no_7b_real():
    state = PipelineState(**json.loads(ENTRADA.read_text(encoding="utf-8")))

    resultado = sintetizador_node(state)

    texto = resultado["dossier"]
    print("\n" + texto)
    assert [l for l in texto.splitlines() if l.startswith("## ")] == [
        dossie.TITULO_CHECAGENS, dossie.TITULO_ARGUMENTO, dossie.TITULO_PERGUNTAS, dossie.TITULO_LIMITES,
    ]
    assert resultado.get("warnings", []) == [], "o 7B real deveria passar nos guardrails sem cair no fallback"
    secao_do_modelo = texto.split(dossie.TITULO_ARGUMENTO)[1].split(dossie.TITULO_PERGUNTAS)[0]
    assert termos_de_veredito(secao_do_modelo) == []
    assert extrair_urls(secao_do_modelo) == []
