"""Stub do Agente de Evidências: saída fixa e válida no schema da Seção 3.3.

Devolve sempre as duas evidências do exemplo de ponta a ponta da Seção 4.6
(caso do chá de folha de mamão e dengue), independentemente da entrada.
"""

from __future__ import annotations

import copy

# TEMPORÁRIO: trocar por `from src.state import Evidence` quando o state.py da
# Seção 3.3 estiver na main (ver src/agents/evidence_schema.py).
from src.agents.evidence_schema import Evidence

_FIXED_EVIDENCE = [
    Evidence(
        segment_id="s02",
        stance="contradiz",
        excerpt="Não existe um tratamento específico para a dengue e as formas graves da doença.",
        source_url="https://www.agencialupa.org/jornalismo/2024/02/06/e-falso-que-cha-de-folha-de-mamao-cura-a-dengue-em-tres-dias/",
        source_name="Agência Lupa",
        agency_verdict="Falso",
    ).model_dump(),
    Evidence(
        segment_id="s03",
        stance="contradiz",
        excerpt="não comprovam que o tratamento seja eficaz em humanos",
        source_url="https://www.aosfatos.org/noticias/falso-cha-folha-mamao-dengue/",
        source_name="Aos Fatos",
        agency_verdict="Falso",
    ).model_dump(),
]


def run(state) -> dict:
    return {"evidence": copy.deepcopy(_FIXED_EVIDENCE)}
