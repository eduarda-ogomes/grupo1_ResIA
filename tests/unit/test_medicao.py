"""Execução medida do grafo: estado final, duração de cada nó e o span raiz da análise."""
from opentelemetry import trace

from src import graph, medicao
from src.state import initial_state
from tests import modelos_falsos as falsos

EVENTOS = [
    {"ingestor": {"clean_text": "Uma frase.", "segments": [{"id": "s01", "text": "Uma frase."}],
                  "warnings": ["ingestor: x"]}},
    {"agente_socratico": {"socratic_questions": None, "warnings": ["socrático: y"]}},
    {"agente_evidencias": {"evidence": []}},
    {"agente_texto": {"text_report": None, "warnings": ["texto: z"]}},
    {"sintetizador": {"dossier": "## Limites desta análise"}},
]


class GrafoFalso:
    def __init__(self, eventos):
        self.eventos = eventos

    def stream(self, estado):
        yield from self.eventos


def relogio(*tempos):
    restantes = iter(tempos)
    return lambda: next(restantes)


def executar_falso(**kwargs):
    return medicao.executar(GrafoFalso(EVENTOS), initial_state("Uma frase."), relogio=relogio(0, 1, 4, 6, 9, 12), **kwargs)


def test_junta_o_estado_e_soma_os_avisos():
    e = executar_falso()

    assert e.estado.warnings == ["ingestor: x", "socrático: y", "texto: z"]
    assert e.estado.dossier == "## Limites desta análise"
    assert e.estado.segments[0].text == "Uma frase."


def test_duracoes_respeitam_o_paralelismo():
    e = executar_falso()

    assert e.duracao_por_no == {"ingestor": 1, "agente_socratico": 3, "agente_evidencias": 5,
                                "agente_texto": 8, "sintetizador": 3}
    assert e.fim_por_no["agente_texto"] == 9
    assert e.total == 12


def test_avisa_cada_no_que_termina():
    vistos = []

    executar_falso(ao_terminar_no=lambda no, segundos: vistos.append((no, segundos)))

    assert vistos == [("ingestor", 1), ("agente_socratico", 4), ("agente_evidencias", 6),
                      ("agente_texto", 9), ("sintetizador", 12)]


def test_span_raiz_analise_com_atributos(spans, monkeypatch):
    falsos.ligar_falsos(monkeypatch)

    e = medicao.executar(graph.sistema_multiagente, initial_state(falsos.TEXTO_LIVRE))

    finalizados = spans.get_finished_spans()
    raiz = next(s for s in finalizados if s.name == "analise")
    assert raiz.parent is None
    assert raiz.attributes["pipeline.entrada"] == "texto"
    assert raiz.attributes["pipeline.frases"] == 2
    assert e.trace_id == format(raiz.context.trace_id, "032x")
    nos = [s for s in finalizados if s.name.startswith("no.")]
    assert len(nos) == 5
    assert all(s.context.trace_id == raiz.context.trace_id for s in nos)


def test_trace_id_de_contexto_invalido_e_none():
    # tracing desligado = contexto inválido; testado na função pura, porque o provider de testes é global
    assert medicao.trace_id_de(trace.INVALID_SPAN_CONTEXT) is None
