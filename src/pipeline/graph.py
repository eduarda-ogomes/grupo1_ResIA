"""Orquestrador: o grafo do Manual §3.1 com os cinco agentes reais.

Cada nó passa por `proteger` (src/pipeline/protecao.py): estourar o tempo ou levantar exceção
vira aviso em `warnings` e a saída de falha do nó, e o grafo sempre chega ao
Sintetizador (Manual §3.4).

Topologia: o Ingestor abre dois ramos, Evidências e Texto; depois do Texto, o `agente_argumento`
(LLM) e o Socrático (LLM) rodam em paralelo; o Sintetizador só monta e espera os três.

ATENÇÃO: o PipelineState é estrito (sem valores padrão). Quem chamar o grafo
deve passar o estado completo criado por `initial_state(...)` (src/state.py):
    sistema_multiagente.invoke(initial_state("texto ou URL"))
Passar só {"raw_input": ...} levanta ValidationError. Ver o aviso no topo de src/state.py.
"""
from langgraph.graph import END, START, StateGraph

from src.pipeline import protecao
from src.agents.evidence import run as evidencias_node
from src.agents.ingestor import ingestor_node
from src.agents.socratic import socratic_node as socratico_node
from src.agents.synthesizer.agent import argumento_fallback, argumento_node, sintetizador_node
from src.agents.text_analysis import texto_node
from src.state import PipelineState

# Ordem de exibição dos nós (tabela de tempos do app) e quem precisa terminar antes de cada um
# (src/pipeline/medicao.py mede a duração de um nó a partir do fim dos predecessores)
ORDEM_NOS = ("ingestor", "agente_evidencias", "agente_texto", "agente_argumento", "agente_socratico", "sintetizador")
PREDECESSORES: dict[str, tuple[str, ...]] = {
    "ingestor": (),
    "agente_evidencias": ("ingestor",),
    "agente_texto": ("ingestor",),
    "agente_argumento": ("agente_texto",),
    "agente_socratico": ("agente_texto",),
    "sintetizador": ("agente_evidencias", "agente_argumento", "agente_socratico"),
}


def construir_grafo(
    timeout_ingestor: float = protecao.TIMEOUT_INGESTOR_S,
    timeout_ramo: float = protecao.TIMEOUT_RAMO_S,
    timeout_sintetizador: float = protecao.TIMEOUT_SINTETIZADOR_S,
):
    """Monta e compila o grafo; os timeouts (em segundos) existem como parâmetro para os testes."""
    builder = StateGraph(PipelineState)

    builder.add_node("ingestor", protecao.proteger("ingestor", ingestor_node, timeout_ingestor, protecao.FALHA_INGESTOR))
    builder.add_node("agente_evidencias", protecao.proteger("evidencias", evidencias_node, timeout_ramo, {"evidence": None}))
    builder.add_node("agente_texto", protecao.proteger("texto", texto_node, timeout_ramo, {"text_report": None}))
    builder.add_node("agente_socratico", protecao.proteger("socratico", socratico_node, timeout_ramo, {"socratic_questions": None}))
    builder.add_node(
        "agente_argumento",
        protecao.proteger(
            "argumento", argumento_node, timeout_sintetizador, {"argument": None},
            recuperar=argumento_fallback,  # estourou o tempo esperando o LLM: o argumento sai do fallback em código
        ),
    )
    builder.add_node(
        "sintetizador",
        protecao.proteger("sintetizador", sintetizador_node, timeout_sintetizador, {"dossier": protecao.DOSSIE_INDISPONIVEL}),
    )

    builder.add_edge(START, "ingestor")
    builder.add_edge("ingestor", "agente_evidencias")
    builder.add_edge("ingestor", "agente_texto")
    # Superstep: argumento e socrático só começam quando evidências E texto terminam (ver docs/agents/desempenho.md).
    builder.add_edge("agente_texto", "agente_argumento")
    builder.add_edge("agente_texto", "agente_socratico")
    # Lista de origens: o sintetizador espera as três e roda uma vez só
    builder.add_edge(["agente_evidencias", "agente_argumento", "agente_socratico"], "sintetizador")
    builder.add_edge("sintetizador", END)

    return builder.compile()


sistema_multiagente = construir_grafo()
