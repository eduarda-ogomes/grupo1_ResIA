"""Modelos falsos para rodar os agentes e o grafo sem LM Studio, índice nem NLI."""
import json
from pathlib import Path

from src.agents import evidence, socratic, synthesizer, text_analysis

FIXTURES_MAMAO = Path(__file__).resolve().parent / "fixtures" / "caso_mamao_dengue"

# Passa em todos os guardrails (veredito, link, G3, G4) tanto no caso do mamão quanto no TEXTO_LIVRE:
# "cura a dengue" é literal nos dois textos, e o rótulo "Adjetivação extrema" é fixo do prompt
RESPOSTA_SINTETIZADOR = '- Adjetivação extrema: "cura a dengue" promete um resultado garantido, sem apresentar fonte.'


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


# Duas frases para o ingestor real (spaCy): s01 e s02.
TEXTO_LIVRE = "O suco de mamão cura a dengue. Isso não tem comprovação."
RELATORIO_TEXTO_LIVRE = {
    "statements": [{"segment_id": "s01", "kind": "factual"}, {"segment_id": "s02", "kind": "valor"}],
    "markers": [],
}
PERGUNTAS_TEXTO_LIVRE = [
    "Quais estudos sustentam que o suco de mamão cura a dengue?",
    "Quem afirma que isso não tem comprovação, e com base em quê?",
]


def texto_falso(relatorio: dict):
    """Substitui text_analysis.chamar_modelo: sempre o mesmo relatório em JSON."""
    resposta = json.dumps(relatorio, ensure_ascii=False)
    return lambda mensagens: resposta


def socratico_falso(perguntas: list[str]):
    """Substitui socratic.chamar_modelo: sempre as mesmas perguntas em JSON."""
    resposta = json.dumps({"socratic_questions": perguntas}, ensure_ascii=False)
    return lambda mensagens: resposta


def busca_vazia(textos, k=None):
    """Substitui evidence.search: nenhuma checagem para nenhuma frase."""
    return [[] for _ in textos]


def ligar_falsos(monkeypatch, relatorio=RELATORIO_TEXTO_LIVRE, perguntas=PERGUNTAS_TEXTO_LIVRE) -> SintetizadorFalso:
    """Liga os quatro modelos falsos com respostas válidas; devolve o Sintetizador falso."""
    monkeypatch.setattr(text_analysis, "chamar_modelo", texto_falso(relatorio))
    monkeypatch.setattr(socratic, "chamar_modelo", socratico_falso(perguntas))
    monkeypatch.setattr(evidence, "search", busca_vazia)
    return SintetizadorFalso().instalar(monkeypatch)
