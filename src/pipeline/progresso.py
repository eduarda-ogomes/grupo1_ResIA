"""Progresso de uma análise, no formato que a sala dos agentes (app/sala/) desenha.

O `grafo.stream` só avisa quando um nó termina. Quem começa sai da forma do grafo
(src/pipeline/graph.py, `PREDECESSORES`): o Ingestor abre a análise; Evidências, Texto e
Socrático começam quando ele termina; o Sintetizador espera os três. Cada personagem da
sala é um nó do grafo.
"""
from __future__ import annotations

from src.pipeline.graph import ORDEM_NOS, PREDECESSORES
from src.pipeline.medicao import duracoes

AGENTES = ORDEM_NOS


class Progresso:
    def __init__(self, analise: str):
        self.analise = analise              # identifica a análise na sala, que sobrevive aos redesenhos
        self.fim_por_no: dict[str, float] = {}
        self.avisos: dict[str, list[str]] = {no: [] for no in ORDEM_NOS}
        self.interrompida = False

    def terminou(self, no: str, segundos: float, avisos: list[str]) -> None:
        """`segundos` desde o início da análise, como o `ao_terminar_no` de src/pipeline/medicao.py."""
        self.fim_por_no[no] = segundos
        self.avisos[no] = list(avisos)

    def interromper(self) -> None:
        self.interrompida = True

    def _comecou(self, agente: str) -> bool:
        return all(p in self.fim_por_no for p in PREDECESSORES[agente])

    def estado(self, agente: str) -> str:
        if agente in self.fim_por_no:
            return "concluido"
        if not self._comecou(agente):
            return "aguardando"
        return "interrompido" if self.interrompida else "trabalhando"

    def para_a_sala(self) -> dict:
        """Os dados (JSON) que o componente da sala recebe a cada redesenho."""
        duracao = duracoes(self.fim_por_no)
        return {
            "analise": self.analise,
            "concluida": "sintetizador" in self.fim_por_no,
            "interrompida": self.interrompida,
            "agentes": [
                {"id": a, "estado": self.estado(a), "segundos": duracao.get(a), "avisos": list(self.avisos[a])}
                for a in AGENTES
            ],
        }
