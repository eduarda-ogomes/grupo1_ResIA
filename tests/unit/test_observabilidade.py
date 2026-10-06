"""Tracing com Phoenix local (Manual §5.4): opcional, nunca derruba a análise."""
import sys
from types import SimpleNamespace

import pytest

from src import observabilidade


@pytest.fixture(autouse=True)
def configuracao_limpa(monkeypatch):
    monkeypatch.setattr(observabilidade, "_configurado", None)


def instalar_phoenix_falso(monkeypatch, register):
    """Troca phoenix.otel e o instrumentador do LangChain por dublês; devolve onde o instrumentador anota."""
    instrumentado_com = []

    class InstrumentadorFalso:
        def instrument(self, **kwargs):
            instrumentado_com.append(kwargs.get("tracer_provider"))

    otel = SimpleNamespace(register=register)
    langchain = SimpleNamespace(LangChainInstrumentor=InstrumentadorFalso)
    monkeypatch.setitem(sys.modules, "phoenix", SimpleNamespace(otel=otel))
    monkeypatch.setitem(sys.modules, "phoenix.otel", otel)
    monkeypatch.setitem(sys.modules, "openinference", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "openinference.instrumentation", SimpleNamespace(langchain=langchain))
    monkeypatch.setitem(sys.modules, "openinference.instrumentation.langchain", langchain)
    return instrumentado_com


def test_desligado_por_padrao_nao_importa_phoenix(monkeypatch):
    monkeypatch.delenv("PHOENIX_TRACING", raising=False)
    monkeypatch.setitem(sys.modules, "phoenix.otel", None)  # importar levantaria ImportError

    assert observabilidade.configurar_tracing() is False


def test_ligado_registra_o_projeto_e_instrumenta_o_langchain_uma_vez(monkeypatch):
    monkeypatch.setenv("PHOENIX_TRACING", "1")
    chamadas_register, provider = [], object()

    def register(**kwargs):
        chamadas_register.append(kwargs)
        return provider

    instrumentado_com = instalar_phoenix_falso(monkeypatch, register)

    assert observabilidade.configurar_tracing() is True
    assert observabilidade.configurar_tracing() is True
    assert chamadas_register == [{"project_name": "grupo1-resia", "batch": True}]
    assert instrumentado_com == [provider]


def test_pacote_ausente_devolve_false_e_avisa(monkeypatch, caplog):
    monkeypatch.setenv("PHOENIX_TRACING", "1")
    monkeypatch.setitem(sys.modules, "phoenix.otel", None)

    assert observabilidade.configurar_tracing() is False
    assert "pip install arize-phoenix-otel" in caplog.text


def test_register_que_falha_nao_derruba_e_devolve_false(monkeypatch):
    monkeypatch.setenv("PHOENIX_TRACING", "1")

    def register(**kwargs):
        raise ConnectionError("Phoenix fora do ar")

    instalar_phoenix_falso(monkeypatch, register)

    assert observabilidade.configurar_tracing() is False


def test_span_grava_tipo_e_atributos_com_prefixo(spans):
    with observabilidade.span("ingestor.segmentar", frases=3, truncado=False):
        pass

    [s] = spans.get_finished_spans()
    assert s.name == "ingestor.segmentar"
    assert s.attributes["openinference.span.kind"] == "CHAIN"
    assert s.attributes["pipeline.frases"] == 3
    assert s.attributes["pipeline.truncado"] is False


def test_atributos_estranhos_nao_quebram(spans):
    with observabilidade.span("x", nada=None, dicionario={"a": 1}, lista=["a", 2], objeto=object()):
        pass

    attrs = spans.get_finished_spans()[0].attributes
    assert "pipeline.nada" not in attrs
    assert attrs["pipeline.dicionario"] == "{'a': 1}"
    assert attrs["pipeline.lista"] == ("a", "2")
    assert isinstance(attrs["pipeline.objeto"], str)


def test_excecao_no_bloco_fica_no_span_e_e_repassada(spans):
    with pytest.raises(ValueError):
        with observabilidade.span("x"):
            raise ValueError("bug")

    s = spans.get_finished_spans()[0]
    assert s.status.status_code.name == "ERROR"
    assert s.events[0].name == "exception"
