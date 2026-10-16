"""Stub do Agente de Evidências: saída fixa e válida no schema da Seção 3.3.

Devolve sempre as duas evidências do exemplo de ponta a ponta da Seção 4.6
(caso do chá de folha de mamão e dengue), lidas da fixture
tests/fixtures/caso_mamao_dengue/02_evidencias_saida.json, independentemente
da entrada. O caminho é relativo a este arquivo, então funciona de qualquer
pasta de onde o programa seja rodado.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.state import Evidence

_FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "caso_mamao_dengue" / "02_evidencias_saida.json"


def run(state) -> dict:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return {"evidence": [Evidence.model_validate(e).model_dump() for e in data["evidence"]]}


# Nome usado pelo graph.py e pelo test_state_contracts.py.
evidence_node = run
