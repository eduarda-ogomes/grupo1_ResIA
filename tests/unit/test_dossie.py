"""Partes do dossiê escritas pelo código (spec do Sintetizador, "Como funciona" e "Casos degradados")."""
import json
from pathlib import Path

import pytest

from src.agents import dossie
from src.state import PipelineState

MAMAO = Path(__file__).resolve().parents[1] / "fixtures" / "caso_mamao_dengue"
URL_LUPA = "https://www.agencialupa.org/jornalismo/2024/02/06/e-falso-que-cha-de-folha-de-mamao-cura-a-dengue-em-tres-dias/"
URL_AOSFATOS = "https://www.aosfatos.org/noticias/falso-cha-folha-mamao-dengue/"


def estado_mamao(**sobrescritas) -> PipelineState:
    dados = json.loads((MAMAO / "05_sintetizador_entrada.json").read_text(encoding="utf-8"))
    dados.update(sobrescritas)
    return PipelineState(**dados)


def evidencia(segment_id, url, stance="contradiz", verdict="Falso", excerpt="Trecho.", name="Agência Exemplo"):
    return {"segment_id": segment_id, "stance": stance, "excerpt": excerpt, "source_url": url,
            "source_name": name, "agency_verdict": verdict}


# --- Pré-processamento ----------------------------------------------------------

def test_preprocessar_mamao_bate_com_a_fixture_de_guardrails():
    esperado = json.loads((MAMAO / "05_sintetizador_guardrails.json").read_text(encoding="utf-8"))["pre_processamento"]

    ctx = dossie.preprocessar(estado_mamao())

    assert [s.id for s in ctx.factuais_sem_checagem] == esperado["frases_factuais_sem_evidencia"]
    assert len(ctx.evidencias) == 2
    assert [s.id for s in ctx.frases_valor] == ["s05", "s06"]


def test_deduplica_por_frase_e_url():
    state = estado_mamao(evidence=[
        evidencia("s02", "https://a.org/1"),
        evidencia("s02", "https://a.org/1", excerpt="Repetida."),
        evidencia("s03", "https://a.org/1"),   # mesma URL, outra frase: fica
    ])

    ctx = dossie.preprocessar(state)

    assert [(e.segment_id, e.excerpt) for e in ctx.evidencias] == [("s02", "Trecho."), ("s03", "Trecho.")]


def test_descarta_evidencia_de_frase_de_valor():
    ctx = dossie.preprocessar(estado_mamao(evidence=[evidencia("s05", "https://a.org/opiniao")]))

    assert ctx.evidencias == []


def test_sem_text_report_mantem_todas_as_evidencias_e_nao_lista_factuais():
    ctx = dossie.preprocessar(estado_mamao(text_report=None, evidence=[evidencia("s05", "https://a.org/opiniao")]))

    assert len(ctx.evidencias) == 1
    assert ctx.factuais_sem_checagem == []
    assert ctx.frases_valor == []


# --- Seção de checagens ---------------------------------------------------------

@pytest.mark.parametrize("stances, resumo", [
    (["contradiz"], "uma checagem contradiz esta frase"),
    (["contradiz", "contradiz", "apoia"], "duas checagens contradizem e uma apoia esta frase"),
    (["insuficiente"], "uma checagem não é conclusiva sobre esta frase"),
    (["apoia", "apoia", "apoia"], "três checagens apoiam esta frase"),
    (["insuficiente", "contradiz"], "uma checagem contradiz esta frase, e uma não é conclusiva"),
    (["insuficiente", "insuficiente"], "duas checagens não são conclusivas sobre esta frase"),
])
def test_resumo_por_stance(stances, resumo):
    assert dossie.resumo_por_stance(stances) == resumo


def test_secao_checagens_do_mamao():
    state = estado_mamao()

    linhas = dossie.secao_checagens(state, dossie.preprocessar(state))

    assert linhas == [
        dossie.TITULO_CHECAGENS,
        '- "O chá da folha de mamão cura a dengue em apenas três dias." — uma checagem contradiz esta frase.',
        f'  - Agência Lupa: Falso — "Não existe um tratamento específico para a dengue e as formas graves da doença." ({URL_LUPA})',
        '- "Ele estimula a medula óssea a produzir mais plaquetas e evita a dengue hemorrágica." — uma checagem contradiz esta frase.',
        f'  - Aos Fatos: Falso — "não comprovam que o tratamento seja eficaz em humanos" ({URL_AOSFATOS})',
        '- Nenhuma checagem encontrada no nosso banco para: "URGENTE: os médicos estão escondendo a cura natural da dengue!", '
        '"Um especialista em plantas medicinais garante que a folha de mamão salva vidas.". '
        'Isso não confirma nem descarta essas frases.',
    ]


def test_sem_selo_quando_a_agencia_nao_deu_veredito():
    state = estado_mamao(evidence=[evidencia("s02", "https://a.org/1", verdict=None)])

    linhas = dossie.secao_checagens(state, dossie.preprocessar(state))

    assert '  - Agência Exemplo — "Trecho." (https://a.org/1)' in linhas


def test_evidence_none_e_lista_vazia_sao_ausencias_diferentes():
    sem_banco = estado_mamao(evidence=None)
    vazia = estado_mamao(evidence=[])

    assert dossie.secao_checagens(sem_banco, dossie.preprocessar(sem_banco)) == [dossie.TITULO_CHECAGENS, dossie.SEM_BANCO]
    assert dossie.secao_checagens(vazia, dossie.preprocessar(vazia)) == [dossie.TITULO_CHECAGENS, dossie.SEM_CHECAGEM]


def test_evidencia_de_frase_desconhecida_nao_quebra_nem_mostra_id():
    state = estado_mamao(evidence=[evidencia("s99", "https://a.org/orfa")])

    linhas = dossie.secao_checagens(state, dossie.preprocessar(state))

    assert linhas == [dossie.TITULO_CHECAGENS, dossie.SEM_CHECAGEM]


# --- Seção do argumento sem LLM -------------------------------------------------

def test_argumento_sem_modelo():
    sem_texto = estado_mamao(text_report=None)
    sem_padroes = estado_mamao(text_report={"statements": [{"segment_id": "s01", "kind": "factual"}], "markers": []})
    mamao = estado_mamao()

    assert dossie.argumento_sem_modelo(sem_texto, dossie.preprocessar(sem_texto)) == [dossie.SEM_ESTRUTURA]
    assert dossie.argumento_sem_modelo(sem_padroes, dossie.preprocessar(sem_padroes)) == [dossie.SEM_PADROES]
    assert dossie.argumento_sem_modelo(mamao, dossie.preprocessar(mamao)) is None


def test_fallback_usa_rotulo_e_trecho_literal_e_nunca_a_explicacao():
    state = estado_mamao()

    linhas = dossie.fallback_argumento(state, dossie.preprocessar(state))

    assert linhas == [
        '- Urgência: "URGENTE"',
        '- Generalização: "os médicos estão escondendo"',
        '- Adjetivação extrema: "em apenas três dias"',
        '- Autoridade sem identificação: "Um especialista em plantas medicinais garante"',
        '- Falsa dicotomia: "nada melhor do que a natureza"',
        '- Urgência: "antes que apaguem este vídeo"',
        '- Juízo de valor: "Não existe nada melhor do que a natureza para cuidar da nossa saúde." é uma opinião e não foi checada.',
        '- Juízo de valor: "Compartilhe com todos antes que apaguem este vídeo!" é uma opinião e não foi checada.',
    ]
    assert not any(m.explanation in "\n".join(linhas) for m in state.text_report.markers)


# --- Perguntas e limites ----------------------------------------------------------

def test_secao_perguntas():
    mamao = estado_mamao()

    assert dossie.secao_perguntas(mamao) == [dossie.TITULO_PERGUNTAS] + [
        f"{i}. {q}" for i, q in enumerate(mamao.socratic_questions, start=1)
    ]
    assert dossie.secao_perguntas(estado_mamao(socratic_questions=None)) == [dossie.TITULO_PERGUNTAS, dossie.SEM_PERGUNTAS]
    assert dossie.secao_perguntas(estado_mamao(socratic_questions=[])) == [dossie.TITULO_PERGUNTAS, dossie.NENHUMA_PERGUNTA]


def test_limites_do_mamao():
    assert dossie.secao_limites(estado_mamao()) == [
        dossie.TITULO_LIMITES,
        "- O texto não tem data de publicação.",
        "- O texto não tem link de origem.",
        dossie.LIMITE_COLETA,
    ]


def test_limites_com_truncamento_url_data_e_ramos_que_falharam():
    state = estado_mamao(raw_input="https://exemplo.org/materia", published_at="2026-03-10", truncated=True,
                         evidence=None, text_report=None, socratic_questions=None)

    assert dossie.secao_limites(state) == [
        dossie.TITULO_LIMITES,
        "- Só o início do texto foi analisado (o texto ultrapassou o limite).",
        "- O banco de checagens não pôde ser consultado.",
        "- A estrutura do texto não pôde ser analisada.",
        "- As perguntas reflexivas não puderam ser geradas.",
        dossie.LIMITE_COLETA,
    ]


# --- Montagem e rede de segurança -----------------------------------------------

def test_montar_separa_as_secoes_por_linha_em_branco():
    assert dossie.montar(["## A", "- 1"], ["## B", "- 2"]) == "## A\n- 1\n\n## B\n- 2"


def test_remover_citacoes_invalidas():
    evidencias = estado_mamao().evidence
    texto = f"## A\n- válida ({URL_LUPA})\n- inventada (https://site-inventado.com/x)\n- sem link"

    limpo, removeu = dossie.remover_citacoes_invalidas(texto, evidencias)

    assert limpo == f"## A\n- válida ({URL_LUPA})\n- sem link"
    assert removeu is True
    assert dossie.remover_citacoes_invalidas(limpo, evidencias) == (limpo, False)


def test_frase_com_link_nao_desloca_a_checagem():
    # Antes: a linha da frase com link era removida e a checagem dela ficava embaixo da frase anterior
    state = estado_mamao(
        segments=[{"id": "s01", "text": "O mamão cura a dengue."},
                  {"id": "s02", "text": "Veja o vídeo em https://youtu.be/abc e compartilhe."}],
        evidence=[evidencia("s01", "https://a.org/1"), evidencia("s02", "https://a.org/2")],
        text_report=None,
    )

    texto = dossie.montar(dossie.secao_checagens(state, dossie.preprocessar(state)))

    assert texto.splitlines() == [
        dossie.TITULO_CHECAGENS,
        '- "O mamão cura a dengue." — uma checagem contradiz esta frase.',
        '  - Agência Exemplo: Falso — "Trecho." (https://a.org/1)',
        '- "Veja o vídeo em [link] e compartilhe." — uma checagem contradiz esta frase.',
        '  - Agência Exemplo: Falso — "Trecho." (https://a.org/2)',
    ]
    assert dossie.remover_citacoes_invalidas(texto, state.evidence) == (texto, False)


def test_trecho_da_checagem_com_link_mantem_a_citacao():
    state = estado_mamao(evidence=[evidencia("s02", "https://a.org/1", excerpt="Leia em https://outro.org/x.")])

    linhas = dossie.secao_checagens(state, dossie.preprocessar(state))

    assert '  - Agência Exemplo: Falso — "Leia em [link]." (https://a.org/1)' in linhas


def test_limites_listam_as_frases_que_ficaram_sem_classificacao():
    relatorio = {"statements": [{"segment_id": f"s0{i}", "kind": "factual"} for i in range(1, 6)], "markers": []}  # falta s06

    linhas = dossie.secao_limites(estado_mamao(text_report=relatorio))

    assert ('- Estas frases não puderam ser classificadas como fato ou opinião: '
            '"Compartilhe com todos antes que apaguem este vídeo!".') in linhas


def test_frase_sem_classificacao_com_link_aparece_neutralizada():
    state = estado_mamao(
        segments=[{"id": "s01", "text": "Frase classificada."}, {"id": "s02", "text": "Veja em https://golpe.example/v agora."}],
        text_report={"statements": [{"segment_id": "s01", "kind": "factual"}], "markers": []},
    )

    linhas = dossie.secao_limites(state)

    assert '- Estas frases não puderam ser classificadas como fato ou opinião: "Veja em [link] agora.".' in linhas
