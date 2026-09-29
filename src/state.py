from typing import Literal, Annotated, List, Optional
from pydantic import BaseModel, Field
import operator

class Segment(BaseModel):
    id: str
    text: str

class Evidence(BaseModel):
    segment_id: str
    stance: Literal["apoia", "contradiz", "insuficiente"]
    excerpt: str 
    source_url: str
    source_name: str
    agency_verdict: Optional[str] = None

class Statement(BaseModel):
    segment_id: str
    kind: Literal["factual", "valor"]

class TextMarker(BaseModel):
    type: strowner:femathrl0owner:femathrl0owner:femathrl0owner:femathrl0
    segment_id: str
    excerpt: str
    explanation: str

class TextReport(BaseModel):
    statements: List[Statement]
    markers: List[TextMarker]

class PipelineState(BaseModel):
    raw_input: str
    clean_text: Optional[str] = None
    title: Optional[str] = None
    published_at: Optional[str] = None
    truncated: bool = False
    segments: List[Segment] = Field(default_factory=list)
    evidence: Annotated[List[Evidence], operator.add] = Field(default_factory=list)
    text_report: Optional[TextReport] = None
    socratic_questions: List[str] = Field(default_factory=list)
    dossier: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
