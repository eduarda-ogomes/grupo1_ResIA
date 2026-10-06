"""Guardrails do Sintetizador (Manual §3.5): filtro de veredito e checagem de citações."""
import json
from pathlib import Path

import pytest

from src.guardrails.citacoes import extrair_urls, neutralizar_urls, urls_invalidas
from src.guardrails.veredito import termos_de_veredito
from src.state import Evidence

BORDAS = Path(__file__).resolve().parents[1] / "fixtures" / "bordas"


def borda(nome: str) -> dict:
    return json.loads((BORDAS / f"{nome}.json").read_text(encoding="utf-8"))


def evidencia(url: str) -> Evidence:
    return Evidence(segment_id="s01", stance="contradiz", excerpt="x", source_url=url,
                    source_name="Agência Exemplo", agency_verdict=None)


# --- Filtro de veredito -------------------------------------------------------

def test_veredito_vazado_da_fixture_e_reprovado():
    caso = borda("sintetizador_veredito_vazado")

    assert termos_de_veredito(caso["rascunho"]) == caso["saida_esperada"]["filtro_veredito"]["termos_encontrados"]


def test_parafrase_passa_falso_negativo_conhecido():
    # Manual §3.5: "não procede" escapa do filtro por lista; fica fixado aqui de propósito
    assert termos_de_veredito(borda("sintetizador_parafrase")["rascunho"]) == []


@pytest.mark.parametrize("texto, termos", [
    ("Isso é FALSO.", ["falso"]),
    ("As alegações são falsas e verdadeiras ao mesmo tempo.", ["falsas", "verdadeiras"]),
    ("Circula como Fake   News nas redes.", ["fake news"]),
    ("Uma mentira repetida; mentiras demais.", ["mentira", "mentiras"]),
    ("Campanha de desinformação.", ["desinformacao"]),
    ("Campanha de desinformacao.", ["desinformacao"]),
    ("Falso, falso e FALSO.", ["falso"]),
    ("Verdadeiro.", ["verdadeiro"]),
])
def test_filtro_pega_os_termos_com_variacoes(texto, termos):
    assert termos_de_veredito(texto) == termos


@pytest.mark.parametrize("texto", [
    "Houve falsificação de documentos.",
    "A falsidade ideológica é crime.",
    "Verdadeiramente curioso.",
    "Nenhum termo proibido aqui.",
])
def test_filtro_respeita_a_fronteira_de_palavra(texto):
    assert termos_de_veredito(texto) == []


# --- Checagem de citações -------------------------------------------------------

def test_citacao_inventada_da_fixture_e_reprovada():
    caso = borda("sintetizador_citacao_inventada")
    texto = " ".join(f"Fonte ({url})." for url in caso["urls_no_dossie"])
    evidencias = [evidencia(url) for url in caso["urls_nas_evidencias"]]

    assert urls_invalidas(texto, evidencias) == caso["saida_esperada"]["checagem_citacoes"]["urls_invalidas"]


def test_pontuacao_final_nao_faz_parte_da_url():
    texto = "Veja (https://a.org/x), https://b.org/y. E https://c.org/z;"

    assert extrair_urls(texto) == ["https://a.org/x", "https://b.org/y", "https://c.org/z"]


def test_url_da_evidencia_terminada_em_pontuacao_continua_valida():
    assert urls_invalidas("(https://a.org/x.)", [evidencia("https://a.org/x.")]) == []


def test_url_invalida_repetida_aparece_uma_vez():
    assert urls_invalidas("http://x.org e de novo http://x.org", []) == ["http://x.org"]


def test_texto_sem_url_nao_tem_url_invalida():
    assert urls_invalidas("Sem links aqui.", []) == []


def test_neutralizar_urls_mantem_a_pontuacao_em_volta():
    assert neutralizar_urls("Veja (https://a.org/x). E http://b.org") == "Veja ([link]). E [link]"


@pytest.mark.parametrize("texto", [
    '- Falsa dicotomia: "nada melhor do que a natureza" opõe natural a tratamento médico.',
    "Há uma FALSA DICOTOMIA no texto.",
    "Há uma falsa   dicotomia no texto.",
])
def test_nome_da_falacia_falsa_dicotomia_nao_e_veredito(texto):
    # O rótulo que o próprio Sintetizador manda o modelo usar (dossie.ROTULOS) não pode reprová-lo
    assert termos_de_veredito(texto) == []


def test_falsa_fora_do_nome_da_falacia_continua_sendo_pega():
    assert termos_de_veredito("Falsa dicotomia à parte, a notícia é falsa.") == ["falsa"]
