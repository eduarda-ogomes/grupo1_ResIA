# =============================================================================
# ATENÇÃO — LEIA ANTES DE CRIAR OU CHAMAR QUALQUER COISA QUE USE O PipelineState
# (vale para pessoas e para agentes de código)
#
# O PipelineState é ESTRITO (Manual §3.3): nenhum campo tem valor padrão.
#   - `PipelineState(raw_input="...")` FALHA com "Field required".
#   - `sistema_multiagente.invoke({"raw_input": "..."})` FALHA com ValidationError,
#     porque o LangGraph valida o estado de entrada.
#
# Sempre construa o estado de entrada com `initial_state(...)`, definido no fim
# deste arquivo:
#     estado = initial_state("texto ou URL")
#     PipelineState(**estado)                    # testes / validação
#     sistema_multiagente.invoke(estado)         # execução do grafo
#     initial_state("x", **saida_do_ingestor)    # partindo da saída de outro nó
#
# Se você adicionar, remover ou renomear um campo do PipelineState, atualize
# `initial_state` no mesmo commit. `tests/unit/test_state.py` falha se os dois
# ficarem fora de sincronia.
# =============================================================================

from typing import Literal, Annotated, List, Optional
from pydantic import BaseModel, Field
import operator

class Segment(BaseModel):
    id: str                        # ex.: "s03"
    text: str                      # uma frase da notícia

class Evidence(BaseModel):
    segment_id: str
    stance: Literal["apoia", "contradiz", "insuficiente"]
    excerpt: str                   # trecho literal da checagem
    source_url: str                # obrigatório
    source_name: str               # ex.: Aos Fatos, Lupa
    agency_verdict: str | None     # veredito da agência, citado com atribuição

class Statement(BaseModel):
    segment_id: str
    kind: Literal["factual", "valor"]

class TextMarker(BaseModel):
    type: Literal["adjetivacao_extrema", "urgencia_artificial",
                  "apelo_autoridade", "falsa_dicotomia", "generalizacao"]
    segment_id: str
    excerpt: str
    explanation: str

class TextReport(BaseModel):
    statements: list[Statement]
    markers: list[TextMarker]

class PipelineState(BaseModel):
    raw_input: str
    clean_text: str
    title: str | None
    published_at: str | None
    truncated: bool
    segments: list[Segment]
    evidence: list[Evidence] | None
    text_report: TextReport | None
    socratic_questions: list[str] | None
    dossier: str | None
    warnings: Annotated[list[str], operator.add]


def initial_state(raw_input: str, **overrides) -> dict:
    """Estado inicial válido no schema estrito: entrada do usuário e o resto vazio.

    O LangGraph valida o estado de entrada, então todo campo precisa estar presente.
    `evidence`, `text_report`, `socratic_questions` e `dossier` começam em None
    (ainda não produzidos); os nós dos ramos os preenchem.
    """
    return {
        "raw_input": raw_input,
        "clean_text": "",
        "title": None,
        "published_at": None,
        "truncated": False,
        "segments": [],
        "evidence": None,
        "text_report": None,
        "socratic_questions": None,
        "dossier": None,
        "warnings": [],
        **overrides,
    }
