"""Testes unitários do Agente de Evidências, com busca e NLI simulados.

    python -m pytest tests/unit/test_evidence_unit.py
"""

import pytest
from pydantic import BaseModel

from src.agents import evidence as agent
from src.retrieval import config
from tests.evidence_fakes import (
    FakeClassify,
    FakeSearch,
    hit,
    load_fixture,
    make_state,
    mamao_fakes,
)


def _patch(monkeypatch, search, classify):
    monkeypatch.setattr(agent, "search", search)
    monkeypatch.setattr(agent, "classify", classify)


# --- stance ---------------------------------------------------------------

@pytest.mark.parametrize(
    "probs, expected",
    [
        ({"entailment": 0.9, "neutral": 0.05, "contradiction": 0.05}, "apoia"),
        ({"entailment": 0.05, "neutral": 0.05, "contradiction": 0.9}, "contradiz"),
        ({"entailment": 0.1, "neutral": 0.8, "contradiction": 0.1}, "insuficiente"),
        ({"entailment": 0.45, "neutral": 0.1, "contradiction": 0.45}, "insuficiente"),  # abaixo do mínimo
        ({}, "insuficiente"),
    ],
)
def test_stance_from_probs(probs, expected):
    assert agent.stance_from_probs(probs, min_prob=0.5) == expected


# --- excerpt --------------------------------------------------------------

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


# --- seleção de candidatos ------------------------------------------------

def test_select_candidates_limiar_url_dedup_e_maximo():
    hits = [
        hit("a", 0.95, "https://x.org/1"),
        hit("b", 0.90, "https://x.org/1"),   # mesma URL, menor -> sai
        hit("c", 0.88, ""),                   # sem URL -> sai
        hit("d", 0.85, "https://x.org/2"),
        hit("e", 0.80, "https://x.org/3"),
        hit("f", 0.78, "https://x.org/4"),   # passa do máximo -> sai
        hit("g", 0.60, "https://x.org/5"),   # abaixo do limiar -> sai
    ]
    selected = agent.select_candidates(hits, threshold=0.75, max_per_segment=3)
    assert [h.text for h in selected] == ["a", "d", "e"]


# --- run: caso do mamão ---------------------------------------------------

def test_caso_mamao_reproduz_a_saida_da_secao_4_6(monkeypatch):
    state, search, classify, expected = mamao_fakes()
    _patch(monkeypatch, search, classify)
    output = agent.run(state)
    assert output == {"evidence": expected["evidence"]}
    # Todas as frases vão numa única chamada de busca e numa única de NLI.
    assert len(search.calls) == 1 and len(classify.calls) == 1
    # Premissa = trecho da checagem; hipótese = frase da notícia.
    premise, hypothesis = classify.calls[0][0]
    assert premise == expected["evidence"][0]["excerpt"]
    assert hypothesis == state.segments[1]["text"]


# --- run: casos de borda da Seção 4.7 -------------------------------------

def _run_border_case(monkeypatch, name):
    case = load_fixture(f"bordas/{name}.json")
    segments = case["segments"]
    text_by_id = {s["id"]: s["text"] for s in segments}
    search = FakeSearch(
        {
            text_by_id[sid]: [hit(h["text"], h["similarity"], h["metadata"]["source_url"],
                                  h["metadata"]["source_name"], h["metadata"]["agency_verdict"],
                                  chunk_id=h["chunk_id"]) for h in hits]
            for sid, hits in case["hits"].items()
        }
    )
    premises = [h["text"] for hits in case["hits"].values() for h in hits]
    classify = FakeClassify(dict(zip(premises, case["nli"])))
    _patch(monkeypatch, search, classify)
    return agent.run(make_state(segments)), case["esperado"], classify


def test_nenhuma_checagem_acima_do_limiar_nao_gera_objeto(monkeypatch):
    output, expected, classify = _run_border_case(monkeypatch, "evidencias_sem_checagem")
    assert output == expected
    assert classify.calls == [], "sem candidatos, o NLI nem é chamado"


def test_nli_neutro_gera_insuficiente_com_url(monkeypatch):
    output, expected, _ = _run_border_case(monkeypatch, "evidencias_nli_neutro")
    assert output == expected


def test_sem_segmentos_devolve_lista_vazia_sem_buscar(monkeypatch):
    search, classify = FakeSearch({}), FakeClassify({})
    _patch(monkeypatch, search, classify)
    assert agent.run(make_state([])) == {"evidence": []}
    assert agent.run(make_state([{"id": "s01", "text": "   "}])) == {"evidence": []}
    assert search.calls == []


def test_falha_no_nli_vira_aviso(monkeypatch):
    state, search, _, _ = mamao_fakes()

    def broken(pairs):
        raise OSError("modelo não encontrado")

    _patch(monkeypatch, search, broken)
    output = agent.run(state)
    assert output["evidence"] is None
    assert "OSError" in output["warnings"][0]


def test_veredito_vazio_vira_none(monkeypatch):
    segment = {"id": "s01", "text": "Frase qualquer."}
    search = FakeSearch({segment["text"]: [hit("Trecho.", 0.9, "https://x.org/1", verdict="")]})
    _patch(monkeypatch, search, FakeClassify({}))
    [item] = agent.run(make_state([segment]))["evidence"]
    assert item["agency_verdict"] is None


# --- run: compatibilidade com o state.py ---------------------------------

def test_aceita_segment_de_outra_classe(monkeypatch):
    """O Segment do state.py é outra classe; o agente precisa aceitá-lo."""

    class OtherSegment(BaseModel):
        id: str
        text: str

    state, search, classify, expected = mamao_fakes()
    _patch(monkeypatch, search, classify)
    other_state = make_state([OtherSegment(**s) for s in state.segments])
    assert agent.run(other_state) == {"evidence": expected["evidence"]}


def test_alias_para_o_graph_atual():
    assert agent.evidencias_node is agent.run


def test_limiares_vem_da_configuracao(monkeypatch):
    state, search, classify, _ = mamao_fakes()
    _patch(monkeypatch, search, classify)
    monkeypatch.setattr(config, "SIM_THRESHOLD", 0.99)
    assert agent.run(state) == {"evidence": []}
