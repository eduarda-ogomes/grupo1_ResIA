"""Roda o passo do argumento (Agente de Texto) e o Sintetizador contra o qwen2.5-7b de verdade, no caso do mamão.

Não roda no CI. Rode da raiz, com o LM Studio ligado:
    pytest tests/integration/test_sintetizador_lmstudio.py -v -s
Não compara texto exato: confere as seções, as linhas escritas pelo código (rótulo, trecho literal e
juízo de valor) e os guardrails sobre o que o modelo escreveu (os efeitos).
"""
import json
from pathlib import Path

import pytest
import requests

from src.agents.synthesizer import dossie
from src.agents.argumento import argumento_node
from src.agents.synthesizer.agent import sintetizador_node
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

    argumento = argumento_node(state)
    resultado = sintetizador_node(state.model_copy(update={"argument": argumento["argument"]}))

    texto = resultado["dossier"]
    print("\n" + texto)
    assert [l for l in texto.splitlines() if l.startswith("## ")] == [
        dossie.TITULO_RESUMO, dossie.TITULO_CHECAGENS, dossie.TITULO_ARGUMENTO, dossie.TITULO_PERGUNTAS,
        dossie.TITULO_LIMITES, dossie.TITULO_FONTES,
    ]
    assert argumento.get("warnings", []) == [], "o 7B real deveria passar nos guardrails sem deixar marcador sem efeito"
    linhas = argumento["argument"]
    assert len(linhas) == 7 and linhas[-1].startswith("- Juízo de valor: ")
    for linha, m in zip(linhas, state.text_report.markers):
        assert linha.startswith(f'- {dossie.ROTULOS[m.type]}: "{m.excerpt}"'), "rótulo e trecho são do código"
        assert linha != f'- {dossie.ROTULOS[m.type]}: "{m.excerpt}"', "o 7B deveria escrever um efeito para cada marcador"
    secao_do_modelo = texto.split(dossie.TITULO_ARGUMENTO)[1].split(dossie.TITULO_PERGUNTAS)[0]
    assert termos_de_veredito(secao_do_modelo) == []
    assert extrair_urls(secao_do_modelo) == []
