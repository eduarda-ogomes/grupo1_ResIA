"""Progresso de uma análise, no formato que a sala dos agentes (app/sala/) desenha.

O `grafo.stream` só avisa quando um nó termina. Quem começa sai da forma do grafo
(src/pipeline/graph.py, `PREDECESSORES`): o Ingestor abre a análise; Evidências e Texto começam
quando ele termina; o `agente_argumento` e o Socrático começam quando o Texto termina;
o `sintetizador` espera Evidências, argumento e Socrático.

A sala tem cinco personagens e o grafo tem seis nós: o `agente_argumento` não tem
personagem e é desenhado pelo Sintetizador, que trabalha do fim do Texto até o fim do
nó `sintetizador`. O tempo e os avisos do personagem somam os dos dois nós.
"""
from __future__ import annotations

from src.pipeline.graph import ORDEM_NOS, PREDECESSORES
from src.pipeline.medicao import duracoes

AGENTES = ("ingestor", "agente_evidencias", "agente_texto", "agente_socratico", "sintetizador")

# Nós de cada personagem, na ordem em que rodam: começa com o primeiro, termina com o último
NOS_DO_AGENTE: dict[str, tuple[str, ...]] = {a: (a,) for a in AGENTES}
NOS_DO_AGENTE["sintetizador"] = ("agente_argumento", "sintetizador")


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
        primeiro = NOS_DO_AGENTE[agente][0]
        return all(p in self.fim_por_no for p in PREDECESSORES[primeiro])

    def estado(self, agente: str) -> str:
        if NOS_DO_AGENTE[agente][-1] in self.fim_por_no:
            return "concluido"
        if not self._comecou(agente):
            return "aguardando"
        return "interrompido" if self.interrompida else "trabalhando"

    def para_a_sala(self) -> dict:
        """Os dados (JSON) que o componente da sala recebe a cada redesenho."""
        duracao = duracoes(self.fim_por_no)

        def segundos(agente: str) -> float | None:
            medidos = [duracao[no] for no in NOS_DO_AGENTE[agente] if no in duracao]
            return sum(medidos) if medidos else None

        return {
            "analise": self.analise,
            "concluida": "sintetizador" in self.fim_por_no,
            "interrompida": self.interrompida,
            "agentes": [
                {"id": a, "estado": self.estado(a), "segundos": segundos(a),
                 "avisos": [aviso for no in NOS_DO_AGENTE[a] for aviso in self.avisos[no]]}
                for a in AGENTES
            ],
        }
