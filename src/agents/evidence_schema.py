"""Cópia TEMPORÁRIA dos schemas da Seção 3.3 do manual usados pelo Agente de Evidências.

Por que existe: o src/state.py da main ainda não segue a Seção 3.3, e ele não
deve ser alterado nesta branch para evitar conflito de merge. Quando o
state.py da Seção 3.3 entrar na main:
  1. em src/agents/evidence.py e src/stubs/evidence_stub.py, trocar o import
     para `from src.state import Evidence, Segment`;
  2. apagar este arquivo;
  3. rodar `python -m pytest tests/contract/test_evidence_contract.py`.

Os dois sentidos de "insuficiente" (Seção 4.8, item 1):
  - Nenhuma checagem acima do limiar de similaridade para a frase
    -> NENHUM objeto Evidence é emitido para ela.
  - Checagem encontrada, mas o NLI não indica apoio nem contradição
    -> Evidence com stance "insuficiente" e source_url preenchida.
"""

from typing import Literal

from pydantic import BaseModel


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
