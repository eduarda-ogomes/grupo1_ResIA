"""Roda o grafo inteiro com os modelos reais e imprime o tempo de cada nó.

Não roda no CI. Rode da raiz, com o LM Studio ligado (qwen2.5-7b em localhost:1234):
    pytest tests/integration/test_grafo_lmstudio.py -v -s
O Agente de Evidências usa o índice em chroma_data/. Sem ele, ou na primeira carga dos
modelos (que pode passar do timeout do ramo), o teste aceita o aviso de evidências.
"""
import json
import time
from pathlib import Path

import pytest
import requests

from src.graph import sistema_multiagente
from src.state import initial_state

ENTRADA = Path(__file__).resolve().parents[1] / "fixtures" / "caso_mamao_dengue" / "00_entrada.json"


def lm_studio_no_ar():
    try:
        return requests.get("http://localhost:1234/v1/models", timeout=2).ok
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(not lm_studio_no_ar(), reason="LM Studio não está rodando em localhost:1234")


def test_caso_do_mamao_com_os_modelos_reais():
    estado = initial_state(json.loads(ENTRADA.read_text(encoding="utf-8"))["raw_input"])
    final, tempos = dict(estado), {}
    inicio = time.monotonic()

    for evento in sistema_multiagente.stream(estado):
        for no, atualizacao in evento.items():
            tempos[no] = round(time.monotonic() - inicio, 1)
            for chave, valor in atualizacao.items():
                final[chave] = final["warnings"] + valor if chave == "warnings" else valor

    print("\nsegundos desde o início, quando cada nó terminou:", tempos)
    print("avisos:", final["warnings"])
    print(final["dossier"])

    assert final["dossier"]
    assert final["text_report"] is not None
    assert final["socratic_questions"]
    assert not [w for w in final["warnings"] if w.startswith(("ingestor", "texto", "socr", "sintetizador"))]
