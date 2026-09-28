"""Testes do modo "alegacao" (padrão) e da troca de modo, com busca e NLI simulados.

    python -m pytest tests/unit/test_evidence_alegacao.py
"""

import pytest

from src.agents import evidence as agent
from src.retrieval import config
from tests.evidence_fakes import (
    CONTRADICTION,
    ENTAILMENT,
    FACHIN_CLAIM,
    FACHIN_LEAD,
    FACHIN_URL,
    NEUTRAL,
    OUTRA_URL,
    FakeClassify,
    FakeSearch,
    claim_mode_fakes,
    hit,
    make_state,
    mamao_fakes,
)


@pytest.fixture
def alegacao(monkeypatch):
    """Modo alegacao só com o NLI (termos-chave e normalização desligados)."""
    monkeypatch.setattr(config, "STANCE_MODE", "alegacao")
    monkeypatch.setattr(config, "KEY_TERM_CHECK", False)
    monkeypatch.setattr(config, "CLAIM_NORMALIZE", False)
    state, search, classify, leads = claim_mode_fakes()
    monkeypatch.setattr(agent, "search", search)
    monkeypatch.setattr(agent, "classify", classify)
    monkeypatch.setattr(agent, "get_lead_text", lambda url: leads.get(url))
    monkeypatch.setattr(agent, "get_checagem_texts", lambda url: [leads.get(url, "")])
    return state, search, classify, leads


def test_padroes_da_configuracao():
    assert config.STANCE_MODES[0] == "alegacao"
    assert config.STANCE_MODE in config.STANCE_MODES
    assert config.KEY_TERM_CHECK is True       # ligada desde 28/09
    assert config.CLAIM_NORMALIZE is True      # ligada desde 28/09 (experimento + caso UOL)
    assert config.CLAIM_CANDIDATES == 6 and config.MAX_EVIDENCE_PER_SEGMENT == 3


def test_so_a_mesma_alegacao_vira_evidencia(alegacao):
    state, *_ = alegacao
    [item] = agent.run(state)["evidence"]
    assert item["source_url"] == FACHIN_URL          # a outra checagem sobre Fachin foi descartada
    assert item["stance"] == "contradiz"             # veredito "falso" da agência
    assert item["agency_verdict"] == "Falso"         # exibição normalizada
    assert item["excerpt"] == FACHIN_LEAD            # parágrafo de abertura, não o do boato


def test_nli_compara_alegacao_e_frase_nas_duas_direcoes_em_um_lote(alegacao):
    state, _, classify, _ = alegacao
    agent.run(state)
    assert len(classify.calls) == 1
    frase = state.segments[0]["text"]
    assert classify.calls[0][:2] == [(FACHIN_CLAIM, frase), (frase, FACHIN_CLAIM)]
    # 2 checagens acima do limiar (0,55) x 2 direções; a de 0,45 ficou de fora.
    assert len(classify.calls[0]) == 4


def test_basta_uma_direcao(monkeypatch, alegacao):
    state, _, classify, _ = alegacao
    frase = state.segments[0]["text"]
    classify.probs[(FACHIN_CLAIM, frase)] = NEUTRAL
    classify.probs[(frase, FACHIN_CLAIM)] = ENTAILMENT
    assert [e["source_url"] for e in agent.run(state)["evidence"]] == [FACHIN_URL]


def test_sem_mesma_alegacao_nao_emite_nada(alegacao):
    state, _, classify, _ = alegacao
    frase = state.segments[0]["text"]
    classify.probs[(FACHIN_CLAIM, frase)] = CONTRADICTION  # ex.: dengue x chikungunya
    assert agent.run(state) == {"evidence": []}


def test_limiar_da_etapa_2_vem_da_configuracao(monkeypatch, alegacao):
    state, *_ = alegacao
    monkeypatch.setattr(config, "CLAIM_MATCH_MIN_PROB", 0.95)
    assert agent.run(state) == {"evidence": []}


@pytest.mark.parametrize(
    "verdict, stance",
    [("falso", "contradiz"), ("Verdadeiro", "apoia"), ("Enganoso", "insuficiente"),
     ("não_é_bem_assim", "insuficiente")],
)
def test_stance_vem_do_veredito(monkeypatch, alegacao, verdict, stance):
    state, search, _, _ = alegacao
    for hits in search.hits_by_text.values():
        for h in hits:
            if h.metadata["source_url"] == FACHIN_URL:
                h.metadata["agency_verdict"] = verdict
    [item] = agent.run(state)["evidence"]
    assert item["stance"] == stance


def test_sem_abertura_indexada_usa_o_melhor_trecho_que_nao_e_boato(monkeypatch, alegacao):
    state, *_ = alegacao
    monkeypatch.setattr(agent, "get_lead_text", lambda url: None)
    [item] = agent.run(state)["evidence"]
    assert item["excerpt"] == "Trecho do meio da checagem sobre a foto."


def test_checagem_sem_claim_reviewed_usa_o_metodo_do_trecho(monkeypatch):
    """O caso do mamão não tem claim_reviewed nas fixtures: deve dar a saída da Seção 4.6."""
    monkeypatch.setattr(config, "STANCE_MODE", "alegacao")
    state, search, classify, expected = mamao_fakes()
    monkeypatch.setattr(agent, "search", search)
    monkeypatch.setattr(agent, "classify", classify)
    monkeypatch.setattr(agent, "get_lead_text", lambda url: pytest.fail("não deve buscar a abertura"))
    assert agent.run(state) == {"evidence": expected["evidence"]}


def test_evidencias_seguem_a_ordem_das_frases(monkeypatch):
    monkeypatch.setattr(config, "STANCE_MODE", "alegacao")
    segments = [{"id": "s01", "text": "Frase A."}, {"id": "s02", "text": "Frase B."}]
    search = FakeSearch(
        {
            "Frase A.": [hit("a", 0.8, "https://x.org/a", claim_reviewed="Alegação A")],
            "Frase B.": [hit("b", 0.8, "https://x.org/b", claim_reviewed="Alegação B")],
        }
    )
    classify = FakeClassify({("Alegação A", "Frase A."): ENTAILMENT, ("Alegação B", "Frase B."): ENTAILMENT})
    monkeypatch.setattr(agent, "search", search)
    monkeypatch.setattr(agent, "classify", classify)
    monkeypatch.setattr(agent, "get_lead_text", lambda url: f"Abertura de {url}.")
    monkeypatch.setattr(config, "KEY_TERM_CHECK", False)
    assert [e["segment_id"] for e in agent.run(make_state(segments))["evidence"]] == ["s01", "s02"]


# --- Modo "trecho" (Seção 4.2) ----------------------------------------------

def test_modo_trecho_reproduz_o_manual(monkeypatch):
    monkeypatch.setattr(config, "STANCE_MODE", "trecho")
    state, search, classify, expected = mamao_fakes()
    monkeypatch.setattr(agent, "search", search)
    monkeypatch.setattr(agent, "classify", classify)
    assert agent.run(state) == {"evidence": expected["evidence"]}


def test_modo_trecho_tem_a_falha_do_boato_citado(monkeypatch):
    """Documenta por que o padrão mudou: no modo trecho, o parágrafo do boato vira 'apoia'."""
    monkeypatch.setattr(config, "STANCE_MODE", "trecho")
    state, search, _, _ = claim_mode_fakes()
    rumor_text = search.hits_by_text[state.segments[0]["text"]][0].text
    monkeypatch.setattr(agent, "search", search)
    monkeypatch.setattr(agent, "classify", FakeClassify({rumor_text: ENTAILMENT}))
    evidence = agent.run(state)["evidence"]
    assert evidence[0]["source_url"] == FACHIN_URL and evidence[0]["stance"] == "apoia"


def test_modo_invalido_vira_aviso(monkeypatch):
    monkeypatch.setattr(config, "STANCE_MODE", "outro")
    output = agent.run(make_state([{"id": "s01", "text": "Frase."}]))
    assert output["evidence"] is None
    assert "EVIDENCE_STANCE_MODE" in output["warnings"][0]


# --- Título como excerpt -------------------------------------------------------

def test_excerpt_e_o_titulo_da_checagem_quando_existe(alegacao):
    state, search, _, _ = alegacao
    title = "Foto de briga entre Fachin e Moraes não é real, mas produzida por IA"
    for h in search.hits_by_text[state.segments[0]["text"]]:
        if h.metadata["source_url"] == FACHIN_URL:
            h.metadata["review_title"] = title
    [item] = agent.run(state)["evidence"]
    assert item["excerpt"] == title


# --- Variante (c): termos-chave --------------------------------------------------

def test_termos_chave_barram_troca_de_nome_que_o_nli_aceita(monkeypatch, alegacao):
    """O NLI dá entailment alto, mas 'chikungunya' não aparece na checagem de dengue."""
    monkeypatch.setattr(config, "KEY_TERM_CHECK", True)
    frase = "O chá da folha de mamão cura a chikungunya em apenas três dias."
    claim = "Chá de folha de mamão cura a dengue em três dias"
    url = "https://exemplo.org/checagem/cha-mamao-dengue"
    search = FakeSearch({frase: [hit("Não existe tratamento específico para a dengue.", 0.8, url,
                                     claim_reviewed=claim, review_title="É falso que chá de mamão cura dengue")]})
    classify = FakeClassify({(claim, frase): ENTAILMENT, (frase, claim): ENTAILMENT})
    monkeypatch.setattr(agent, "search", search)
    monkeypatch.setattr(agent, "classify", classify)
    monkeypatch.setattr(agent, "get_checagem_texts", lambda u: ["Texto da checagem sobre dengue e chá de mamão."])
    assert agent.run(make_state([{"id": "s01", "text": frase}])) == {"evidence": []}
    assert classify.calls == [], "rejeitada antes do NLI"


def test_termos_chave_deixam_passar_a_mesma_alegacao(monkeypatch, alegacao):
    monkeypatch.setattr(config, "KEY_TERM_CHECK", True)
    state, *_ = alegacao
    evidence = agent.run(state)["evidence"]
    # Frase cita Moraes e STF: presentes na checagem do Fachin, ausentes na outra.
    assert [e["source_url"] for e in evidence] == [FACHIN_URL]


# --- Variante (b): normalização da alegação -------------------------------------

def test_normalizacao_tira_foto_mostra_antes_do_nli(monkeypatch, alegacao):
    monkeypatch.setattr(config, "CLAIM_NORMALIZE", True)
    state, _, classify, _ = alegacao
    agent.run(state)
    premise, _ = classify.calls[0][0]
    assert premise == "Edson Fachin apontando o dedo para Alexandre de Moraes em discussão"


# --- Candidatas da etapa 2 e checagens duplicadas ---------------------------------

def _many_candidates(monkeypatch, titles):
    """Uma frase e várias checagens acima do limiar, todas a 'mesma alegação' para o NLI."""
    monkeypatch.setattr(config, "STANCE_MODE", "alegacao")
    monkeypatch.setattr(config, "KEY_TERM_CHECK", False)
    frase = "Frase da notícia."
    hits = [hit(f"trecho {i}", 0.9 - i * 0.01, f"https://x.org/{i}", claim_reviewed=f"Alegação {i}",
                review_title=t) for i, t in enumerate(titles)]
    # As 3 primeiras NÃO são a mesma alegação; a partir da 4ª, são.
    probs = {(f"Alegação {i}", frase): (NEUTRAL if i < 3 else ENTAILMENT) for i in range(len(titles))}
    monkeypatch.setattr(agent, "search", FakeSearch({frase: hits}))
    monkeypatch.setattr(agent, "classify", FakeClassify(probs))
    return make_state([{"id": "s01", "text": frase}])


def test_avalia_ate_6_checagens_e_so_depois_limita_a_3(monkeypatch):
    state = _many_candidates(monkeypatch, [f"Título {i}" for i in range(8)])
    urls = [e["source_url"] for e in agent.run(state)["evidence"]]
    # Antes de 28/09, só as 3 primeiras eram avaliadas e nenhuma casava.
    assert urls == ["https://x.org/3", "https://x.org/4", "https://x.org/5"]


def test_mesma_checagem_em_dois_enderecos_conta_uma_vez(monkeypatch):
    titles = ["T0", "T1", "T2", "Imagem de Fachin é falsa", "Imagem de Fachin é falsa", "T5"]
    state = _many_candidates(monkeypatch, titles)
    urls = [e["source_url"] for e in agent.run(state)["evidence"]]
    assert urls == ["https://x.org/3", "https://x.org/5"]
