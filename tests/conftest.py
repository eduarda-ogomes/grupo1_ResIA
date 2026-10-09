"""Nenhum teste de tests/unit ou tests/contract fala com um modelo de verdade.

Bloqueia os quatro pontos de acesso: o LM Studio (Agentes de Texto, Socrático e
Sintetizador) e a busca no índice do Agente de Evidências, que carregaria o
ChromaDB e o BGE-M3. Quem precisa de uma resposta substitui a função no próprio
teste (ver tests/modelos_falsos.py). O tests/integration/conftest.py desliga este bloqueio.
"""
import pytest

from src.agents import evidence, socratic, synthesizer, text_analysis

MOTIVO = "modelos desligados nos testes (tests/conftest.py)"


def _recusa(*args, **kwargs):
    raise ConnectionError(MOTIVO)


@pytest.fixture(autouse=True)
def sem_modelos(monkeypatch):
    monkeypatch.setattr(text_analysis, "chamar_modelo", _recusa)
    monkeypatch.setattr(socratic, "chamar_modelo", _recusa)
    monkeypatch.setattr(synthesizer, "chamar_modelo", _recusa)
    monkeypatch.setattr(evidence, "search", _recusa)


@pytest.fixture(autouse=True)
def sem_tracing_do_ambiente(monkeypatch):
    """PHOENIX_TRACING=1 exportado no terminal (como o README ensina) não pode vazar para os testes.

    Sem isto, o app chamaria o `register` real do Phoenix, que toma o provider global
    (a fixture `spans` deixa de funcionar) e tenta exportar os spans de teste pela rede.
    Os testes que precisam do tracing ligado fazem `setenv` depois desta fixture.
    """
    monkeypatch.delenv("PHOENIX_TRACING", raising=False)


_EXPORTADOR = None


@pytest.fixture
def spans():
    """Spans gravados em memória, para conferir o tracing sem Phoenix.

    O OpenTelemetry só aceita um provider global por processo: ele é registrado na
    primeira vez que um teste pede a fixture, e o exportador é limpo a cada teste.
    """
    global _EXPORTADOR
    if _EXPORTADOR is None:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        _EXPORTADOR = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(_EXPORTADOR))
        trace.set_tracer_provider(provider)
    _EXPORTADOR.clear()
    return _EXPORTADOR
