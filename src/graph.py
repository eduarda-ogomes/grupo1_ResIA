from langgraph.graph import StateGraph, START, END
from src.state import PipelineState
from src.agents.ingestor import ingestor_node
from src.stubs.evidence_stub import evidence_node as evidencias_node
from src.agents.text_analysis import texto_node
from src.stubs.socratic_stub import socratic_node as socratico_node
from src.agents.synthesizer import synthesizer_node as sintetizador_node

# ATENÇÃO: o PipelineState é estrito (sem valores padrão). Quem chamar o grafo
# deve passar o estado completo criado por `initial_state(...)` (src/state.py):
#     sistema_multiagente.invoke(initial_state("texto ou URL"))
# Passar só {"raw_input": ...} levanta ValidationError. Ver o aviso no topo de src/state.py.
builder = StateGraph(PipelineState)

builder.add_node("ingestor", ingestor_node)
builder.add_node("agente_evidencias", evidencias_node)
builder.add_node("agente_texto", texto_node)
builder.add_node("agente_socratico", socratico_node)
builder.add_node("sintetizador", sintetizador_node)

builder.add_edge(START, "ingestor")
builder.add_edge("ingestor", "agente_evidencias")
builder.add_edge("ingestor", "agente_texto")
builder.add_edge("ingestor", "agente_socratico")

for node in ["agente_evidencias", "agente_texto", "agente_socratico"]:
    builder.add_edge(node, "sintetizador")

builder.add_edge("sintetizador", END)

sistema_multiagente = builder.compile()
