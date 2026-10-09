"""Progresso de uma análise, no formato que a sala dos agentes (app/sala/) desenha.

O `grafo.stream` só avisa quando um nó termina. Quem começa sai da forma do grafo
(src/graph.py): o Ingestor abre a análise, os três ramos começam quando ele termina
e o Sintetizador quando os três terminam.
"""
from __future__ import annotations

from src.graph import RAMOS
from src.medicao import duracoes

AGENTES = ("ingestor", *RAMOS, "sintetizador")


class Progresso:
    def __init__(self, analise: str):
        self.analise = analise              # identifica a análise na sala, que sobrevive aos redesenhos
        self.fim_por_no: dict[str, float] = {}
        self.avisos: dict[str, list[str]] = {a: [] for a in AGENTES}
        self.interrompida = False

    def terminou(self, no: str, segundos: float, avisos: list[str]) -> None:
        """`segundos` desde o início da análise, como o `ao_terminar_no` de src/medicao.py."""
        self.fim_por_no[no] = segundos
        self.avisos[no] = list(avisos)

    def interromper(self) -> None:
        self.interrompida = True

    def _comecou(self, agente: str) -> bool:
        if agente == "ingestor":
            return True
        if agente == "sintetizador":
            return all(r in self.fim_por_no for r in RAMOS)
        return "ingestor" in self.fim_por_no

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
                {"id": a, "estado": self.estado(a), "segundos": duracao.get(a), "avisos": self.avisos[a]}
                for a in AGENTES
            ],
        }
