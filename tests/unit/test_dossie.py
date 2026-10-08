"""Partes do dossiê escritas pelo código (spec do Sintetizador, "Como funciona" e "Casos degradados")."""
import json
from pathlib import Path

import pytest

from src.agents import dossie
from src.guardrails.veredito import termos_de_veredito
from src.state import PipelineState, Segment

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


def secao(state: PipelineState) -> list[str]:
    ctx = dossie.preprocessar(state)
    return dossie.secao_checagens(state, ctx, dossie.numerar_fontes(state, ctx))


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

def test_legenda_nao_usa_termos_de_veredito_e_esta_numa_linha_so():
    assert termos_de_veredito(dossie.LEGENDA_CHECAGENS) == []
    assert "\n" not in dossie.LEGENDA_CHECAGENS


def test_secao_checagens_do_mamao():
    state = estado_mamao(); ctx = dossie.preprocessar(state)
    linhas = dossie.secao_checagens(state, ctx, dossie.numerar_fontes(state, ctx))
    assert linhas == [
        dossie.TITULO_CHECAGENS, dossie.LEGENDA_CHECAGENS,
        '- "O chá da folha de mamão cura a dengue em apenas três dias."',
        f'  - Contradiz · Agência Lupa: Falso [↗ 1](<{URL_LUPA}>)',
        '- "Ele estimula a medula óssea a produzir mais plaquetas e evita a dengue hemorrágica."',
        f'  - Contradiz · Aos Fatos: Falso [↗ 2](<{URL_AOSFATOS}>)',
        '- Sem checagem no nosso banco: 2 afirmações factuais, "URGENTE: os médicos estão escondendo a cura natural da dengue!" '
        'e "Um especialista em plantas medicinais garante que a folha de mamão salva vidas.". '
        'Isso não confirma nem descarta essas frases.',
    ]


def test_fontes_do_mamao():
    state = estado_mamao(); ctx = dossie.preprocessar(state)
    assert dossie.secao_fontes(ctx, dossie.numerar_fontes(state, ctx)) == [
        dossie.TITULO_FONTES,
        f'1. Agência Lupa: Falso — "Não existe um tratamento específico para a dengue e as formas graves da doença." · [abrir ↗](<{URL_LUPA}>)',
        f'2. Aos Fatos: Falso — "não comprovam que o tratamento seja eficaz em humanos" · [abrir ↗](<{URL_AOSFATOS}>)',
    ]


def test_secao_fontes_vazia_quando_nao_ha_fontes():
    state = estado_mamao(evidence=[]); ctx = dossie.preprocessar(state)
    assert dossie.numerar_fontes(state, ctx) == {}
    assert dossie.secao_fontes(ctx, {}) == []


def test_sem_checagem_com_muitas_frases_mostra_duas_e_conta_o_resto():
    frases = [Segment(id=f"s{i:02d}", text=f"Frase factual número {i} " + "x" * 90) for i in range(1, 31)]
    linha = dossie.linha_sem_checagem(frases)
    assert linha.startswith('- Sem checagem no nosso banco: 30 afirmações factuais, como "Frase factual número 1 ')
    assert linha.endswith(' e mais 28. Isso não confirma nem descarta essas frases.')
    assert len(linha) < 300


def test_uma_frase_sem_checagem_usa_singular():
    assert dossie.linha_sem_checagem([Segment(id="s01", text="A ponte caiu.")]) == (
        '- Sem checagem no nosso banco: 1 afirmação factual, "A ponte caiu.". Isso não confirma nem descarta essa frase.')


def test_tres_frases_sem_checagem_mostram_duas_e_mais_uma():
    frases = [Segment(id=f"s0{i}", text=t) for i, t in enumerate(["A.", "B.", "C."], start=1)]
    assert dossie.linha_sem_checagem(frases) == (
        '- Sem checagem no nosso banco: 3 afirmações factuais, como "A.", "B." e mais 1. '
        'Isso não confirma nem descarta essas frases.')


def test_encurtar_corta_no_limite_com_reticencias():
    assert dossie.encurtar("curta") == "curta"
    assert dossie.encurtar("x" * 80) == "x" * 80
    assert dossie.encurtar("x" * 81) == "x" * 79 + "…"
    assert len(dossie.encurtar("palavra " * 30)) <= 80


def test_frase_sem_checagem_e_escapada_e_neutralizada_na_linha():
    linha = dossie.linha_sem_checagem([Segment(id="s01", text="Custa R$ 10, veja https://a.org/x_y agora.")])
    assert '"Custa R\\$ 10, veja [link] agora."' in linha


def test_mesma_url_em_duas_frases_tem_um_numero_so():
    url = "https://a.org/1"
    state = estado_mamao(evidence=[evidencia("s02", url), evidencia("s03", url)]); ctx = dossie.preprocessar(state)
    fontes = dossie.numerar_fontes(state, ctx)
    assert fontes == {url: 1}
    assert len(dossie.secao_fontes(ctx, fontes)) == 2
    corpo = dossie.secao_checagens(state, ctx, fontes)
    assert corpo.count(f"  - Contradiz · Agência Exemplo: Falso [↗ 1](<{url}>)") == 2


def test_numeracao_segue_a_ordem_das_frases_e_nao_a_das_evidencias():
    state = estado_mamao(evidence=[evidencia("s03", "https://a.org/terceira"), evidencia("s02", "https://a.org/segunda")])
    fontes = dossie.numerar_fontes(state, dossie.preprocessar(state))
    assert fontes == {"https://a.org/segunda": 1, "https://a.org/terceira": 2}


def test_evidencia_de_frase_desconhecida_nao_ganha_numero():
    state = estado_mamao(evidence=[evidencia("s99", "https://a.org/orfa"), evidencia("s02", "https://a.org/1")])
    ctx = dossie.preprocessar(state)
    fontes = dossie.numerar_fontes(state, ctx)
    assert fontes == {"https://a.org/1": 1}
    assert dossie.secao_fontes(ctx, fontes)[1:] == [
        '1. Agência Exemplo: Falso — "Trecho." · [abrir ↗](<https://a.org/1>)']


def test_url_com_parenteses_continua_valida():
    url = "https://x.org/a_(b)"
    state = estado_mamao(evidence=[evidencia("s02", url)]); ctx = dossie.preprocessar(state)
    texto = dossie.montar(dossie.secao_checagens(state, ctx, dossie.numerar_fontes(state, ctx)))
    assert f"[↗ 1](<{url}>)" in texto
    assert dossie.remover_citacoes_invalidas(texto, state.evidence)[1] is False


def test_cifrao_asterisco_e_colchete_da_noticia_sao_escapados():
    assert dossie.texto_seguro("Custa R$ 10 e R$ 20, *exclusivo* [veja]") == r"Custa R\$ 10 e R\$ 20, \*exclusivo\* \[veja\]"
    assert dossie.texto_seguro("veja https://a.org/x_y.") == "veja [link]."


def test_escapar_markdown_cobre_o_conjunto_inteiro():
    assert dossie.escapar_markdown("\\ ` * _ [ ] < > ~ $") == r"\\ \` \* \_ \[ \] \< \> \~ \$"
    assert dossie.escapar_markdown("texto simples, com acento e 100%.") == "texto simples, com acento e 100%."


def test_stance_sai_por_extenso_em_portugues():
    state = estado_mamao(evidence=[
        evidencia("s02", "https://a.org/1", stance="contradiz"),
        evidencia("s02", "https://a.org/2", stance="apoia"),
        evidencia("s02", "https://a.org/3", stance="insuficiente"),
    ])
    ctx = dossie.preprocessar(state)
    linhas = dossie.secao_checagens(state, ctx, dossie.numerar_fontes(state, ctx))
    assert "  - Contradiz · Agência Exemplo: Falso [↗ 1](<https://a.org/1>)" in linhas
    assert "  - Apoia · Agência Exemplo: Falso [↗ 2](<https://a.org/2>)" in linhas
    assert "  - Não conclusiva · Agência Exemplo: Falso [↗ 3](<https://a.org/3>)" in linhas


def test_sem_selo_quando_a_agencia_nao_deu_veredito():
    state = estado_mamao(evidence=[evidencia("s02", "https://a.org/1", verdict=None)])
    ctx = dossie.preprocessar(state)
    fontes = dossie.numerar_fontes(state, ctx)

    linhas = dossie.secao_checagens(state, ctx, fontes)

    assert "  - Contradiz · Agência Exemplo [↗ 1](<https://a.org/1>)" in linhas
    assert dossie.secao_fontes(ctx, fontes)[1:] == ['1. Agência Exemplo — "Trecho." · [abrir ↗](<https://a.org/1>)']


def test_evidence_none_e_lista_vazia_sao_ausencias_diferentes():
    sem_banco = estado_mamao(evidence=None)
    vazia = estado_mamao(evidence=[])

    assert secao(sem_banco) == [dossie.TITULO_CHECAGENS, dossie.SEM_BANCO]
    assert secao(vazia) == [dossie.TITULO_CHECAGENS, dossie.SEM_CHECAGEM]   # sem checagem listada, sem legenda


def test_evidencia_de_frase_desconhecida_nao_quebra_nem_mostra_id():
    state = estado_mamao(evidence=[evidencia("s99", "https://a.org/orfa")])

    assert secao(state) == [dossie.TITULO_CHECAGENS, dossie.SEM_CHECAGEM]


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

    texto = dossie.montar(secao(state))

    assert texto.splitlines() == [
        dossie.TITULO_CHECAGENS, dossie.LEGENDA_CHECAGENS,
        '- "O mamão cura a dengue."',
        '  - Contradiz · Agência Exemplo: Falso [↗ 1](<https://a.org/1>)',
        '- "Veja o vídeo em [link] e compartilhe."',
        '  - Contradiz · Agência Exemplo: Falso [↗ 2](<https://a.org/2>)',
    ]
    assert dossie.remover_citacoes_invalidas(texto, state.evidence) == (texto, False)


def test_trecho_da_checagem_com_link_mantem_a_citacao():
    state = estado_mamao(evidence=[evidencia("s02", "https://a.org/1", excerpt="Leia em https://outro.org/x.")])
    ctx = dossie.preprocessar(state)

    linhas = dossie.secao_fontes(ctx, dossie.numerar_fontes(state, ctx))

    assert linhas[1] == '1. Agência Exemplo: Falso — "Leia em [link]." · [abrir ↗](<https://a.org/1>)'
    texto = dossie.montar(dossie.secao_checagens(state, ctx, dossie.numerar_fontes(state, ctx)), linhas)
    assert dossie.remover_citacoes_invalidas(texto, state.evidence)[1] is False


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


# --- Texto da notícia escapado em todas as seções do código -----------------------

def test_frase_da_noticia_e_escapada_no_corpo_das_checagens():
    state = estado_mamao(segments=[{"id": "s01", "text": "O kit custa R$ 10 e é *natural*."}],
                         evidence=[evidencia("s01", "https://a.org/1")], text_report=None)

    linhas = secao(state)

    assert '- "O kit custa R\\$ 10 e é \\*natural\\*."' in linhas


def test_fallback_e_limites_escapam_trecho_e_frase_da_noticia():
    state = estado_mamao(
        segments=[{"id": "s01", "text": "Paga R$ 5 por mês."}, {"id": "s02", "text": "Frase_sem classificar."}],
        text_report={"statements": [{"segment_id": "s01", "kind": "valor"}],
                     "markers": [{"segment_id": "s01", "type": "adjetivacao_extrema", "excerpt": "R$ 5 *só*", "explanation": "x"}]},
    )

    linhas = dossie.fallback_argumento(state, dossie.preprocessar(state))

    assert linhas[0] == '- Adjetivação extrema: "R\\$ 5 \\*só\\*"'
    assert linhas[1] == '- Juízo de valor: "Paga R\\$ 5 por mês." é uma opinião e não foi checada.'
    assert ('- Estas frases não puderam ser classificadas como fato ou opinião: "Frase\\_sem classificar.".'
            in dossie.secao_limites(state))
