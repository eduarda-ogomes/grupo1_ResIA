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
