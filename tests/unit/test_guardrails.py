"""Guardrails do Sintetizador (Manual §3.5): filtro de veredito, checagem de citações e ancoragem no contexto."""
import json
from pathlib import Path

import pytest

from src.guardrails.ancoragem import citacoes_nao_literais, termos_fora_do_contexto, trechos_citados
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


# --- Ancoragem no contexto (G3, G4) -------------------------------------------

FRASES = ["Segundo o Corpo de Bombeiros, a aeronave ficou totalmente destruída.",
          "As causas serão investigadas pelo Cenipa em 2022."]


def test_trechos_citados_pega_aspas_retas_e_curvas_na_ordem_e_ignora_curtos():
    texto = '- "primeiro trecho" e “segundo trecho”; o "ok" é curto demais.'

    assert trechos_citados(texto) == ["primeiro trecho", "segundo trecho"]


def test_trecho_literal_passa_com_aspas_curvas_e_caixa_diferente():
    assert citacoes_nao_literais('- Urgência: “TOTALMENTE destruída” reforça o dano.', FRASES) == []


def test_trecho_com_reticencias_passa_quando_as_partes_estao_na_mesma_frase():
    assert citacoes_nao_literais('- "Segundo o Corpo de Bombeiros… totalmente destruída"', FRASES) == []


def test_trecho_com_tres_pontos_tambem_divide_em_partes():
    assert citacoes_nao_literais('- "Segundo o Corpo de Bombeiros... totalmente destruída"', FRASES) == []


def test_trecho_com_reticencias_reprova_quando_as_partes_estao_em_frases_diferentes():
    texto = '- "Segundo o Corpo de Bombeiros… investigadas pelo Cenipa"'

    assert citacoes_nao_literais(texto, FRASES) == ["Segundo o Corpo de Bombeiros… investigadas pelo Cenipa"]


def test_trecho_parafraseado_e_reprovado():
    assert citacoes_nao_literais('- "o avião foi completamente destruído"', FRASES) == ["o avião foi completamente destruído"]


def test_espacos_a_mais_e_aspas_tipograficas_dentro_do_trecho_nao_reprovam():
    fontes = ["Ele disse que não há\n  risco para a população, \u201cpor ora\u201d."]

    assert citacoes_nao_literais('- "não   há risco" e "por ora"', fontes) == []
    assert citacoes_nao_literais("- \u201cpor ora\u201d", ["a \"por ora\" basta"]) == []


def test_sem_aspas_ou_sem_fontes_a_checagem_e_coerente():
    assert citacoes_nao_literais("- Sem trecho citado aqui.", FRASES) == []
    assert citacoes_nao_literais('- "algum trecho"', []) == ["algum trecho"]


def test_nome_numero_e_doenca_de_fora_sao_apontados():
    texto = "- Generalização: a OMS registrou 15 casos de dengue."
    assert termos_fora_do_contexto(texto, " ".join(FRASES)) == ["oms", "15", "dengue"]


def test_caixa_e_acento_diferentes_nao_reprovam():
    assert termos_fora_do_contexto("- O CENIPA vai investigar o caso de 2022.", " ".join(FRASES)) == []


def test_rotulos_ignorados_nao_viram_nome():
    texto = '- Autoridade sem identificação: "Corpo de Bombeiros" é citado sem nome.'
    assert termos_fora_do_contexto(texto, " ".join(FRASES), ignorar=["Autoridade sem identificação"]) == []


def test_rotulo_no_meio_da_linha_so_deixa_de_ser_nome_com_ignorar():
    texto = "- A matéria cita Autoridade Sem Identificação, mas não diz quem."
    contexto = " ".join(FRASES)

    assert termos_fora_do_contexto(texto, contexto) == ["autoridade", "identificacao"]
    assert termos_fora_do_contexto(texto, contexto, ignorar=["Autoridade sem identificação"]) == []


def test_ignorar_ignora_caixa():
    texto = "- AUTORIDADE SEM IDENTIFICAÇÃO: a aeronave ficou destruída."

    assert termos_fora_do_contexto(texto, " ".join(FRASES), ignorar=["Autoridade sem identificação"]) == []


def test_doenca_que_tambem_vira_nome_nao_aparece_duas_vezes():
    texto = "- Casos de Dengue e dengue."

    assert termos_fora_do_contexto(texto, " ".join(FRASES)) == ["dengue"]


def test_nome_composto_e_apontado_como_um_grupo_so():
    texto = "- Declaração do Ministério da Saúde sobre o caso."

    assert termos_fora_do_contexto(texto, " ".join(FRASES)) == ["ministerio saude"]


def test_grupo_de_nome_presente_se_algum_token_esta_no_contexto():
    texto = "- Segundo o Corpo de Bombeiros Militar, houve danos."

    assert termos_fora_do_contexto(texto, " ".join(FRASES)) == []


def test_primeira_palavra_do_marcador_de_lista_e_tratada_como_inicio_de_frase():
    # "Governo" abre a linha: palavra comum de início de frase, não é nome
    assert termos_fora_do_contexto("- Governo investiga a aeronave.", " ".join(FRASES)) == []
    assert termos_fora_do_contexto("1. Governo investiga a aeronave.", " ".join(FRASES)) == []


def test_termos_repetidos_em_linhas_diferentes_aparecem_uma_vez():
    texto = "- A OMS registrou 15 casos.\n- A OMS registrou 15 mortes."

    assert termos_fora_do_contexto(texto, " ".join(FRASES)) == ["oms", "15"]


def test_numero_com_milhar_e_comparado_normalizado():
    contexto = "O incêndio atingiu 1.800 casas."

    assert termos_fora_do_contexto("- Foram 1800 casas atingidas.", contexto) == []


@pytest.mark.parametrize("texto", [
    "- A aeronave caiu. Moradores relataram barulho.",
    "- A aeronave caiu. Testemunhas viram fumaça.",
    "- Urgência: Reforça o dano da aeronave.",
])
def test_inicio_de_cada_frase_da_linha_nao_e_nome(texto):
    # Só a primeira palavra da linha era tratada como início de frase; as de depois de ". " e de ": " também são
    assert termos_fora_do_contexto(texto, " ".join(FRASES)) == []


def test_nome_de_fora_na_segunda_frase_da_linha_continua_sendo_apontado():
    assert termos_fora_do_contexto("- A aeronave caiu. Segundo a OMS, houve falhas.", " ".join(FRASES)) == ["oms"]


def test_g3_aceita_aspas_simples_dentro_de_aspas_duplas():
    texto = '- Juízo de valor: "\'Essa medida é um desastre\', afirmou o senador." é uma opinião'
    assert citacoes_nao_literais(texto, ['"Essa medida é um desastre", afirmou o senador.']) == []


@pytest.mark.parametrize("marca", ["(...)", "(…)", "[...]", "[…]", "[ ... ]"])
def test_g3_aceita_supressao_entre_parenteses_ou_colchetes(marca):
    texto = f'- "Segundo o Corpo de Bombeiros {marca} totalmente destruída"'
    assert citacoes_nao_literais(texto, ["Segundo o Corpo de Bombeiros, a aeronave ficou totalmente destruída."]) == []


def test_g3_supressao_entre_colchetes_ainda_exige_a_mesma_frase():
    texto = '- "Segundo o Corpo de Bombeiros [...] totalmente destruída"'
    fontes = ["Segundo o Corpo de Bombeiros, houve um incêndio.", "A aeronave ficou totalmente destruída."]
    assert citacoes_nao_literais(texto, fontes) == ["Segundo o Corpo de Bombeiros [...] totalmente destruída"]
