from langgraph.graph import StateGraph, START, END
from src.state import PipelineState
from src.agents.ingestor import ingestor_node
from src.stubs.evidence_stub import evidence_node as evidencias_node
from src.stubs.text_stub import text_node as texto_node
from src.stubs.socratic_stub import socratic_node as socratico_node
from src.stubs.synthesizer_stub import synthesizer_node as sintetizador_node

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
