from typing import Literal, Annotated, List, Optional
from pydantic import BaseModel, Field
import operator

class Evidence(BaseModel):
    stance: Literal["apoia", "contradiz", "insuficiente"]
    excerpt: str 
    source_url: str
    source_name: str
    retrieved_from: Literal["corpus", "web"]

class FramingMarker(BaseModel):
    type: str
    exact_excerpt: str
    short_explanation: str

class FramingReport(BaseModel):
    markers: List[FramingMarker]
    emotional_tone: dict[str, float]

class Dossier(BaseModel):
    content_summary: str
    framing_summary: str

class PipelineState(BaseModel):
    raw_input: str
    clean_text: Optional[str] = None
    title: Optional[str] = None
    date: Optional[str] = None
    evidence: Annotated[List[Evidence], operator.add] = Field(default_factory=list)
    framing: Optional[FramingReport] = None
    socratic_questions: List[str] = Field(default_factory=list)
    dossier: Optional[Dossier] = None
