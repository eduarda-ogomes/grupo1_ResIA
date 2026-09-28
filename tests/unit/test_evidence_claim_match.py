"""Testes da etapa "mesma alegação": normalização da alegação e termos-chave.

    python -m pytest tests/unit/test_evidence_claim_match.py
"""

import pytest

from src.retrieval.claim_match import key_terms, key_terms_present, name_groups, normalize_claim, normalize_text


@pytest.mark.parametrize(
    "claim, expected",
    [
        ("Foto mostra Edson Fachin apontando o dedo para Alexandre de Moraes em discussão",
         "Edson Fachin apontando o dedo para Alexandre de Moraes em discussão"),
        ("Vídeo mostra que Lula recebeu refugiados", "Lula recebeu refugiados"),
        ("Vídeos mostram ajuda humanitária da China em Gaza", "Ajuda humanitária da China em Gaza"),
        ("Imagens provam que Lula tem um sósia", "Lula tem um sósia"),
        ("Em áudio, Lula parabeniza Moraes pela prisão de Bolsonaro", "Lula parabeniza Moraes pela prisão de Bolsonaro"),
        ("Vídeo publicado no TikTok mostra multidão na Paulista", "Multidão na Paulista"),
        # Sem enquadramento de mídia: não muda.
        ("Lula morreu após hemorragia cerebral", "Lula morreu após hemorragia cerebral"),
        ("Fotógrafo mostra o Rio", "Fotógrafo mostra o Rio"),
        ("", ""),
    ],
)
def test_normalize_claim(claim, expected):
    assert normalize_claim(claim) == expected


def test_normalize_text_numeros():
    assert normalize_text("R$ 5.000, R$ 5 mil, 1,5 mil e 1.800") == "r$ 5000, r$ 5000, 1500 e 1800"


@pytest.mark.parametrize(
    "sentence, terms",
    [
        ("Fachin apontou o dedo para Moraes durante uma discussão no STF.", ["fachin", "moraes", "stf"]),
        ("Eduardo Bolsonaro foi fotografado ao lado de um elefante morto.", ["eduardo", "bolsonaro"]),
        ("Lewandowski não tomou vacina contra a Covid-19.", ["lewandowski", "covid"]),
        ("Governo Lula anunciou um novo programa.", ["lula"]),        # "Governo" é palavra comum de início
        ("O chá da folha de mamão cura a chikungunya em apenas três dias.", ["chikungunya"]),
        ("A Receita vai taxar Pix acima de R$ 5 mil.", ["receita", "pix", "5000"]),
        ("Os beneficiários vão receber R$ 1.800 no dia 20 de julho.", ["1800", "20"]),
        ("Não existe nada melhor do que a natureza.", []),
    ],
)
def test_key_terms(sentence, terms):
    assert key_terms(sentence) == terms


def test_nomes_compostos_formam_um_grupo():
    assert name_groups("Imagem mostra Edson Fachin apontando para Alexandre de Moraes") == [
        ["edson", "fachin"], ["alexandre", "moraes"]]


CHECAGEM_PARAGUAI = ["Presidente do Paraguai agradece Lula pela migração de empresas brasileiras",
                     "É falso que presidente do Paraguai agradeceu a Lula na ONU"]
ALEGACAO_PARAGUAI = "Presidente do Paraguai agradece Lula pela migração de empresas brasileiras"


@pytest.mark.parametrize(
    "sentence, texts, claim, expected",
    [
        # Paráfrase (o radical tolera "paraguaio").
        ("O presidente paraguaio agradeceu a Lula pela ida de empresas ao Paraguai.",
         CHECAGEM_PARAGUAI, ALEGACAO_PARAGUAI, (True, [], [])),
        # Troca de nome: falta "argentina" e a alegação tem "paraguai", ausente da frase.
        ("O presidente argentino agradeceu a Lula pela ida de empresas à Argentina.",
         CHECAGEM_PARAGUAI, ALEGACAO_PARAGUAI, (False, ["argentina"], ["paraguai"])),
        # Contexto a mais sem troca: "STF" não está no título, mas não há nome sobrando na alegação.
        ("Fachin apontou o dedo para Moraes durante uma discussão acalorada no STF.",
         ["Imagem de Fachin apontando dedo para Moraes é falsa e criada por IA"],
         "Imagem mostra Fachin apontando o dedo para Moraes", (True, ["stf"], [])),
        # Troca de nome no início da frase da alegação (Lewandowski) e da frase (Fux, no meio).
        ("O ministro Fux nunca se vacinou contra a Covid.",
         ["Lewandowski tomou, sim, vacina contra a Covid-19"], "Lewandowski não tomou vacina contra a Covid-19",
         (False, ["fux"], ["lewandowski"])),
        # Troca de doença e de número.
        ("O chá de mamão cura a chikungunya em três dias.", ["Não existe tratamento para a dengue"],
         "Chá de folha de mamão cura a dengue em três dias", (False, ["chikungunya"], ["dengue"])),
        ("A Receita Federal vai cobrar imposto sobre Pix acima de R$ 50 mil.",
         ["É falso que Pix acima de R$ 5.000 será taxado pela Receita Federal"],
         "Pix acima de R$ 5.000 será taxado pela Receita Federal", (False, ["50000"], ["5000"])),
    ],
)
def test_key_terms_present_com_alegacao(sentence, texts, claim, expected):
    assert key_terms_present(sentence, texts, claim) == expected


def test_sem_alegacao_a_regra_e_estrita():
    """Sem a alegação, qualquer termo ausente reprova (contexto a mais também)."""
    result = key_terms_present("Fachin apontou o dedo para Moraes no STF.", ["Imagem de Fachin e Moraes é falsa"])
    assert result == (False, ["stf"], [])
