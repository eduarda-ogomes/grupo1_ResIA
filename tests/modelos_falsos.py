"""Modelos falsos para rodar os agentes e o grafo sem LM Studio, índice nem NLI."""
import json
from pathlib import Path

from src.agents import synthesizer

FIXTURES_MAMAO = Path(__file__).resolve().parent / "fixtures" / "caso_mamao_dengue"

# Passa nos dois guardrails: sem termo de veredito e sem link
RESPOSTA_SINTETIZADOR = '- Urgência: "URGENTE" pede ação imediata, sem indicar um prazo real.'


def carregar_mamao(nome: str) -> dict:
    return json.loads((FIXTURES_MAMAO / nome).read_text(encoding="utf-8"))


class SintetizadorFalso:
    """Substitui synthesizer.chamar_modelo: devolve as respostas na ordem (a última se repete)
    e guarda a mensagem do usuário de cada chamada. Uma resposta Exception é levantada."""

    def __init__(self, *respostas):
        self.respostas = list(respostas) or [RESPOSTA_SINTETIZADOR]
        self.prompts: list[str] = []

    def __call__(self, mensagens):
        self.prompts.append(mensagens[-1][1])
        resposta = self.respostas[min(len(self.prompts), len(self.respostas)) - 1]
        if isinstance(resposta, BaseException):
            raise resposta
        return resposta

    def instalar(self, monkeypatch) -> "SintetizadorFalso":
        monkeypatch.setattr(synthesizer, "chamar_modelo", self)
        return self
