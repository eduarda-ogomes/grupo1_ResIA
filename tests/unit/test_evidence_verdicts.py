"""Testes da normalização dos vereditos, com formatos encontrados no corpus real.

    python -m pytest tests/unit/test_evidence_verdicts.py
"""

import pytest

from src.retrieval.verdicts import display_verdict, stance_from_verdict


@pytest.mark.parametrize(
    "raw, stance",
    [
        ("falso", "contradiz"),
        ("Falso", "contradiz"),
        ("Falso: Na verdade, uma empresa subsidiária de uma estatal chinesa adquiriu uma mineradora.", "contradiz"),
        ("Montagem", "contradiz"),
        ("verdadeiro", "apoia"),
        ("Comprovado", "apoia"),
        ("Enganoso", "insuficiente"),
        ("Enganoso: O conteúdo foi tirado de contexto para parecer atual.", "insuficiente"),
        ("não_é_bem_assim", "insuficiente"),
        ("Falta contexto", "insuficiente"),
        ("Contextualizando: Lula recebe aposentadoria especial como anistiado desde 1993.", "insuficiente"),
        ("Sátira", "insuficiente"),
        ("verdadeiro, mas impreciso", "insuficiente"),
        ("É mentirosa a afirmação de que Moraes ordenou a troca de 48 urnas.", "insuficiente"),  # texto livre: conservador
        ("", "insuficiente"),
        (None, "insuficiente"),
    ],
)
def test_stance_from_verdict(raw, stance):
    assert stance_from_verdict(raw) == stance


@pytest.mark.parametrize(
    "raw, shown",
    [
        ("falso", "Falso"),
        ("não_é_bem_assim", "Não é bem assim"),
        ("Falso: Na verdade, uma empresa adquiriu uma mineradora.", "Falso"),
        ("Contextualizando: Lula recebe aposentadoria.", "Contextualizando"),
        ("A prefeita não foi alvo de operação da PF: diz o site.", "A prefeita não foi alvo de operação da PF: diz o site."),
        ("", None),
        (None, None),
    ],
)
def test_display_verdict(raw, shown):
    assert display_verdict(raw) == shown
