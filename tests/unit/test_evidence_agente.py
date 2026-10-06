"""Testes do Agente de Evidências, com busca e NLI simulados.

    python -m pytest tests/unit/test_evidence_agente.py
"""

import pytest

from src.agents import evidence as agent
from src.retrieval import config
from tests.evidence_fakes import (
    CONTRADICTION,
    ENTAILMENT,
    FACHIN_CLAIM_NORMALIZADA,
    FACHIN_LEAD,
    FACHIN_URL,
    NEUTRAL,
    FakeClassify,
    FakeSearch,
    fachin_fakes,
    hit,
    load_fixture,
    make_state,
    mamao_fakes,
    patch_agent,
)
from src.retrieval.indice import Hit


@pytest.fixture
def fachin(monkeypatch):
    state, search, classify, leads, texts = fachin_fakes()
    patch_agent(monkeypatch, agent, search, classify, leads, texts)
    return state, search, classify


def _run_one(monkeypatch, sentence, hits, probs=None, default=ENTAILMENT, leads=None, texts=None):
    search = FakeSearch({sentence: hits})
    classify = FakeClassify(probs or {}, default=default)
    patch_agent(monkeypatch, agent, search, classify, leads, texts)
    return agent.run(make_state([{"id": "s01", "text": sentence}])), classify


# --- Configuração ---------------------------------------------------------------

def test_padroes_da_configuracao():
    assert config.SIM_THRESHOLD == 0.55 and config.CLAIM_MATCH_MIN_PROB == 0.8
    assert config.CLAIM_CANDIDATES == 6 and config.MAX_EVIDENCE_PER_SEGMENT == 3


# --- Passo 1: busca e agrupamento ------------------------------------------------

def test_agrupa_por_checagem_com_limiar_e_link_obrigatorio():
    hits = [hit("a", 0.95, "https://x.org/1"), hit("b", 0.90, "https://x.org/1"), hit("c", 0.88, ""),
            hit("d", 0.85, "https://x.org/2"), hit("e", 0.50, "https://x.org/3")]
    groups = agent.group_hits_by_url(hits, threshold=0.75, max_urls=6)
    assert [[h.text for h in g] for g in groups] == [["a", "b"], ["d"]]


# Textos em minúsculas: sem nomes próprios, a checagem de termos-chave não interfere.
def test_avalia_ate_6_checagens_e_devolve_no_maximo_3(monkeypatch):
    frase = "a frase da notícia."
    hits = [hit(f"t{i}", 0.9 - i * 0.01, f"https://x.org/{i}", claim_reviewed=f"a alegação {i}",
                review_title=f"título {i}") for i in range(8)]
    # As 3 primeiras NÃO são a mesma alegação; a partir da 4ª, são.
    probs = {pair: NEUTRAL for i in range(3) for pair in ((f"a alegação {i}", frase), (frase, f"a alegação {i}"))}
    output, _ = _run_one(monkeypatch, frase, hits, probs)
    assert [e["source_url"] for e in output["evidence"]] == ["https://x.org/3", "https://x.org/4", "https://x.org/5"]


def test_mesma_checagem_em_dois_enderecos_conta_uma_vez(monkeypatch):
    frase = "a frase da notícia."
    titles = ["Imagem de Fachin é falsa", "Imagem de Fachin é falsa", "Outro título"]
    hits = [hit("t", 0.9 - i * 0.01, f"https://x.org/{i}", claim_reviewed="a alegação", review_title=t)
            for i, t in enumerate(titles)]
    output, _ = _run_one(monkeypatch, frase, hits)
    assert [e["source_url"] for e in output["evidence"]] == ["https://x.org/0", "https://x.org/2"]


def test_espelho_bol_perde_para_o_original_uol(monkeypatch):
    frase = "a frase da notícia."
    title = "Imagem de Fachin é falsa"
    bol = "https://www.bol.uol.com.br/noticias/x.htm"
    uol = "https://noticias.uol.com.br/confere/x.htm"
    hits = [hit("t", 0.62, bol, "BOL - UOL", claim_reviewed="a alegação", review_title=title),
            hit("t", 0.62, uol, "UOL Notícias", claim_reviewed="a alegação", review_title=title),
            hit("t", 0.60, "https://x.org/2", claim_reviewed="a alegação", review_title="Outro título")]
    output, _ = _run_one(monkeypatch, frase, hits)
    assert [e["source_url"] for e in output["evidence"]] == [uol, "https://x.org/2"]


def test_checagem_sem_alegacao_checada_e_ignorada(monkeypatch):
    output, classify = _run_one(monkeypatch, "Frase.", [hit("t", 0.9, "https://x.org/1")])
    assert output == {"evidence": []} and classify.calls == []


# --- Passos 2 e 3: é a mesma alegação? -------------------------------------------

def test_so_a_mesma_alegacao_vira_evidencia(fachin):
    state, _, _ = fachin
    [item] = agent.run(state)["evidence"]
    assert item["source_url"] == FACHIN_URL          # a outra checagem sobre Fachin foi descartada
    assert item["stance"] == "contradiz"             # veredito "falso" da agência
    assert item["agency_verdict"] == "Falso"


def test_nli_usa_a_alegacao_normalizada_nas_duas_direcoes_em_um_lote(fachin):
    state, _, classify = fachin
    agent.run(state)
    frase = state.segments[0]["text"]
    assert len(classify.calls) == 1
    # Só a checagem do Fachin chega ao NLI: a outra foi barrada pelos termos-chave (INSS, Presidência).
    assert classify.calls[0] == [(FACHIN_CLAIM_NORMALIZADA, frase), (frase, FACHIN_CLAIM_NORMALIZADA)]


def test_basta_uma_direcao_do_nli(fachin):
    state, _, classify = fachin
    frase = state.segments[0]["text"]
    classify.probs[(FACHIN_CLAIM_NORMALIZADA, frase)] = NEUTRAL
    classify.probs[(frase, FACHIN_CLAIM_NORMALIZADA)] = ENTAILMENT
    assert [e["source_url"] for e in agent.run(state)["evidence"]] == [FACHIN_URL]


def test_nli_abaixo_do_minimo_nao_gera_evidencia(fachin, monkeypatch):
    state, _, classify = fachin
    classify.probs[(FACHIN_CLAIM_NORMALIZADA, state.segments[0]["text"])] = CONTRADICTION
    assert agent.run(state) == {"evidence": []}
    monkeypatch.setattr(config, "CLAIM_MATCH_MIN_PROB", 0.95)
    classify.probs[(FACHIN_CLAIM_NORMALIZADA, state.segments[0]["text"])] = ENTAILMENT
    assert agent.run(state) == {"evidence": []}


def test_termos_chave_barram_troca_de_doenca_antes_do_nli(monkeypatch):
    """O NLI aceitaria (entailment alto), mas 'chikungunya' troca 'dengue'."""
    frase = "O chá da folha de mamão cura a chikungunya em apenas três dias."
    hits = [hit("Não existe tratamento específico para a dengue.", 0.8, "https://x.org/1",
                claim_reviewed="Chá de folha de mamão cura a dengue em três dias")]
    output, classify = _run_one(monkeypatch, frase, hits)
    assert output == {"evidence": []} and classify.calls == []


# --- Passo 4: a evidência ------------------------------------------------------------

@pytest.mark.parametrize(
    "verdict, stance",
    [("falso", "contradiz"), ("Verdadeiro", "apoia"), ("Enganoso", "insuficiente"), ("não_é_bem_assim", "insuficiente")],
)
def test_stance_vem_do_veredito(fachin, verdict, stance):
    state, search, _ = fachin
    for h in search.hits_by_text[state.segments[0]["text"]]:
        h.metadata["agency_verdict"] = verdict
    assert agent.run(state)["evidence"][0]["stance"] == stance


def test_excerpt_titulo_depois_abertura_depois_trecho(fachin, monkeypatch):
    state, search, _ = fachin
    hits = search.hits_by_text[state.segments[0]["text"]]
    assert agent.run(state)["evidence"][0]["excerpt"] == FACHIN_LEAD          # sem título: abertura
    monkeypatch.setattr(agent, "get_lead_text", lambda url: None)
    assert agent.run(state)["evidence"][0]["excerpt"] == hits[0].text          # sem abertura: melhor trecho
    for h in hits:
        h.metadata["review_title"] = "Foto de briga entre Fachin e Moraes não é real"
    assert agent.run(state)["evidence"][0]["excerpt"] == "Foto de briga entre Fachin e Moraes não é real"


def test_veredito_vazio_vira_none(fachin):
    state, search, _ = fachin
    for h in search.hits_by_text[state.segments[0]["text"]]:
        h.metadata["agency_verdict"] = ""
    assert agent.run(state)["evidence"][0]["agency_verdict"] is None


def test_excerpt_curto_fica_igual():
    assert agent.make_excerpt("  Frase curta.  ", max_chars=100) == "Frase curta."


def test_excerpt_longo_corta_no_fim_de_frase_e_continua_literal():
    text = "Primeira frase da checagem. Segunda frase, um pouco maior que a primeira. Terceira frase que passa do limite."
    excerpt = agent.make_excerpt(text, max_chars=80)
    assert excerpt == "Primeira frase da checagem. Segunda frase, um pouco maior que a primeira."
    assert text.startswith(excerpt)


def test_excerpt_sem_fim_de_frase_corta_em_espaco():
    text = "palavra " * 50
    excerpt = agent.make_excerpt(text, max_chars=30)
    assert len(excerpt) <= 30 and text.startswith(excerpt) and not excerpt.endswith(" ")


# --- Casos da Seção 4.6 e 4.7 -----------------------------------------------------------

def test_caso_mamao_reproduz_a_saida_da_secao_4_6(monkeypatch):
    state, search, classify, expected = mamao_fakes()
    patch_agent(monkeypatch, agent, search, classify)
    assert agent.run(state) == {"evidence": expected["evidence"]}
    assert len(search.calls) == 1 and len(classify.calls) == 1   # um lote para a notícia inteira


# Fixtures no formato do grupo (tests/fixtures/README.md) + a chave "hits" com a busca simulada.
# O NLI simulado diz "entailment" para tudo: no fato parecido, quem barra é a checagem de termos-chave.
@pytest.mark.parametrize("fixture", ["evidencias_sem_checagem", "evidencias_veredito_inconclusivo",
                                     "evidencias_fato_parecido"])
def test_casos_de_borda(monkeypatch, fixture):
    case = load_fixture(f"bordas/{fixture}.json")
    [segment] = case["entrada"]["segments"]
    hits = [Hit(h["chunk_id"], h["text"], h["similarity"], h["metadata"]) for h in case["hits"][segment["id"]]]
    output, _ = _run_one(monkeypatch, segment["text"], hits)
    assert output == {"evidence": case["saida_esperada"]["evidence"]}


# --- Robustez e contrato ------------------------------------------------------------------

def test_sem_segmentos_devolve_lista_vazia_sem_buscar(monkeypatch):
    search = FakeSearch({})
    patch_agent(monkeypatch, agent, search, FakeClassify({}))
    assert agent.run(make_state([])) == {"evidence": []}
    assert agent.run(make_state([{"id": "s01", "text": "   "}])) == {"evidence": []}
    assert search.calls == []


def test_falha_vira_aviso(fachin, monkeypatch):
    state, _, _ = fachin

    def broken(pairs):
        raise OSError("modelo não encontrado")

    monkeypatch.setattr(agent, "classify", broken)
    output = agent.run(state)
    assert output["evidence"] is None and "OSError" in output["warnings"][0]


def test_aceita_segment_de_outra_classe(fachin):
    from pydantic import BaseModel

    class OtherSegment(BaseModel):
        id: str
        text: str

    state, _, _ = fachin
    other = make_state([OtherSegment(**s) for s in state.segments])
    assert agent.run(other) == agent.run(state)


def test_alias_para_o_graph_atual():
    assert agent.evidencias_node is agent.run
