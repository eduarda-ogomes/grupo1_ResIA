"""Observabilidade (Manual §5.4): traces no Arize Phoenix local, via OpenTelemetry.

Desligado por padrão. Com `PHOENIX_TRACING=1`, `configurar_tracing()` registra o
projeto no Phoenix (endereço em `PHOENIX_COLLECTOR_ENDPOINT`, padrão
http://localhost:6006) e instrumenta o LangChain, então toda chamada de LLM vira
um span com prompt, resposta, tokens e tempo. Os spans manuais (`span(...)`) usam
só a API do OpenTelemetry: sem provider configurado, não fazem nada.

Nada aqui pode derrubar uma análise: pacote ausente ou Phoenix fora do ar viram aviso no log.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace

logger = logging.getLogger(__name__)

PROJETO = "grupo1-resia"
PREFIXO = "pipeline."

_configurado: bool | None = None  # None: ainda não tentou; True/False: resultado da tentativa


def configurar_tracing() -> bool:
    """Liga o tracing no Phoenix quando PHOENIX_TRACING=1; devolve se ficou ligado. Idempotente."""
    global _configurado
    if os.environ.get("PHOENIX_TRACING") != "1":
        return False
    if _configurado is not None:
        return _configurado
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from phoenix.otel import register
    except ImportError:
        logger.warning("PHOENIX_TRACING=1, mas o Phoenix não está instalado: "
                       "pip install arize-phoenix-otel openinference-instrumentation-langchain")
        _configurado = False
        return False
    try:
        provider = register(project_name=PROJETO, batch=True)
        LangChainInstrumentor().instrument(tracer_provider=provider)
    except Exception:
        logger.warning("Não foi possível ligar o tracing no Phoenix; a análise segue sem traces", exc_info=True)
        _configurado = False
        return False
    _configurado = True
    return True


def _valor(valor: Any) -> Any:
    """Valor aceito pelo OpenTelemetry: str, bool, int, float ou tupla de str."""
    if isinstance(valor, (str, bool, int, float)):
        return valor
    if isinstance(valor, (list, tuple)):
        return tuple(str(v) for v in valor)
    return str(valor)


@contextmanager
def span(nome: str, tipo: str = "CHAIN", **atributos: Any) -> Iterator[trace.Span]:
    """Abre um span filho do atual, com `openinference.span.kind = tipo` e os atributos em `pipeline.*`.

    Uma exceção no bloco fica registrada no span e é repassada.
    """
    tracer = trace.get_tracer("grupo1_resia")  # na hora da chamada: respeita o provider definido depois
    with tracer.start_as_current_span(nome) as s:
        s.set_attribute("openinference.span.kind", tipo)
        for chave, valor in atributos.items():
            if valor is not None:
                s.set_attribute(PREFIXO + chave, _valor(valor))
        yield s
