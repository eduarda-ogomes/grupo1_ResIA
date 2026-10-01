import pytest

from src.agents import text_analysis


@pytest.fixture(autouse=True)
def sem_lm_studio(monkeypatch):
    """Testes unitários nunca chamam o LM Studio de verdade.

    Quem precisa de uma resposta do modelo substitui `text_analysis.chamar_modelo`
    no próprio teste. Testes com o modelo real ficam em tests/integration/.
    """
    def recusa(mensagens):
        raise ConnectionError("LM Studio desligado nos testes unitários")

    monkeypatch.setattr(text_analysis, "chamar_modelo", recusa)
