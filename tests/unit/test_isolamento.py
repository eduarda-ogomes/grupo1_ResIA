"""O tests/conftest.py desliga todos os modelos: nenhum teste unitário fala com o LM Studio ou com o índice."""
import pytest

from src.agents import argumento, evidence, socratic, text_analysis


def test_agente_de_texto_nao_alcanca_o_modelo():
    with pytest.raises(ConnectionError, match="modelos desligados"):
        text_analysis.chamar_modelo([("user", "oi")])


def test_agente_socratico_nao_alcanca_o_modelo():
    with pytest.raises(ConnectionError, match="modelos desligados"):
        socratic.chamar_modelo([("user", "oi")])


def test_argumento_nao_alcanca_o_modelo():
    with pytest.raises(ConnectionError, match="modelos desligados"):
        argumento.chamar_modelo([("user", "oi")])


def test_evidencias_nao_alcanca_o_indice():
    with pytest.raises(ConnectionError, match="modelos desligados"):
        evidence.search(["uma frase"], k=1)
