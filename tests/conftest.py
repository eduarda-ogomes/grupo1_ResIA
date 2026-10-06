"""Nenhum teste de tests/unit ou tests/contract fala com um modelo de verdade.

Bloqueia os quatro pontos de acesso: o LM Studio (Agentes de Texto, Socrático e
Sintetizador) e a busca no índice do Agente de Evidências, que carregaria o
ChromaDB e o BGE-M3. Quem precisa de uma resposta substitui a função no próprio
teste (ver tests/modelos_falsos.py). O tests/integration/conftest.py desliga este bloqueio.
"""
import pytest

from src.agents import evidence, socratic, synthesizer, text_analysis

MOTIVO = "modelos desligados nos testes (tests/conftest.py)"


def _recusa(*args, **kwargs):
    raise ConnectionError(MOTIVO)


@pytest.fixture(autouse=True)
def sem_modelos(monkeypatch):
    monkeypatch.setattr(text_analysis, "chamar_modelo", _recusa)
    monkeypatch.setattr(socratic, "chamar_modelo", _recusa)
    monkeypatch.setattr(synthesizer, "chamar_modelo", _recusa)
    monkeypatch.setattr(evidence, "search", _recusa)
