"""Execução medida do grafo: estado final, quanto cada nó levou e o span raiz da análise.

O Streamlit (app/app.py) e o relatório de latência (eval/medir_latencia.py) usam esta
mesma função, então a tela e o relatório medem do mesmo jeito.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from opentelemetry.trace import SpanContext

from src.agents.ingestor import is_url
from src.graph import ORDEM_NOS, PREDECESSORES
from src.observabilidade import span
from src.state import PipelineState


@dataclass
class Execucao:
    estado: PipelineState
    fim_por_no: dict[str, float]       # segundos desde o início até o nó terminar
    duracao_por_no: dict[str, float]
    total: float
    trace_id: str | None               # 32 hex; None com o tracing desligado


def trace_id_de(contexto: SpanContext) -> str | None:
    return format(contexto.trace_id, "032x") if contexto.is_valid else None


def duracoes(fim_por_no: dict[str, float]) -> dict[str, float]:
    """Duração de um nó = o fim dele menos o maior fim entre os predecessores que terminaram
    (src/graph.py::PREDECESSORES); sem predecessor, conta desde o início da análise."""
    return {
        no: fim_por_no[no] - max((fim_por_no[p] for p in PREDECESSORES[no] if p in fim_por_no), default=0.0)
        for no in ORDEM_NOS
        if no in fim_por_no
    }


def executar(
    grafo: Any,
    estado_inicial: dict,
    relogio: Callable[[], float] = time.monotonic,
    ao_terminar_no: Callable[[str, float, list[str]], None] | None = None,
) -> Execucao:
    """Roda o grafo por `stream`, junta as atualizações (warnings somados) e mede cada nó.

    `ao_terminar_no(nó, segundos desde o início, avisos que esse nó deu)` é chamada a cada nó.
    """
    entrada = "url" if is_url(estado_inicial["raw_input"].strip()) else "texto"
    with span("analise", entrada=entrada) as raiz:
        inicio = relogio()
        final, fim_por_no = dict(estado_inicial), {}
        for evento in grafo.stream(estado_inicial):
            agora = relogio() - inicio
            for no, atualizacao in evento.items():
                fim_por_no[no] = agora
                for chave, valor in (atualizacao or {}).items():
                    final[chave] = final["warnings"] + valor if chave == "warnings" else valor
                if ao_terminar_no is not None:
                    ao_terminar_no(no, agora, list((atualizacao or {}).get("warnings", [])))

        estado = PipelineState.model_validate(final)
        total = max(fim_por_no.values(), default=0.0)
        raiz.set_attribute("pipeline.frases", len(estado.segments))
        raiz.set_attribute("pipeline.avisos", tuple(estado.warnings))
        raiz.set_attribute("pipeline.total_s", float(total))
        return Execucao(estado, fim_por_no, duracoes(fim_por_no), total, trace_id_de(raiz.get_span_context()))
