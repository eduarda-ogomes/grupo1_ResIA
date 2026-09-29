import requests

from src.agents import ingestor
from src.agents.ingestor import (
    MAX_WORDS,
    extract_text,
    ingestor_node,
    segment_text,
    truncate_words,
)
from src.state import PipelineState

URL = "https://exemplo-jornal.com.br/materia"

ARTIGO_HTML = """
<html><head><title>Mamão cura dengue?</title>
<meta property="article:published_time" content="2026-03-10">
</head>
<body>
<nav>Menu Assine Já</nav>
<article>
<h1>Mamão cura dengue?</h1>
<p>Circula nas redes uma mensagem sobre o suco de folha de mamão. Especialistas dizem que não há comprovação.</p>
<p>A dengue é transmitida pelo mosquito Aedes aegypti. O tratamento é feito com hidratação e repouso.</p>
</article>
<footer>Todos os direitos reservados</footer>
</body></html>
"""


def run_node(raw_input):
    state = PipelineState(raw_input=raw_input)
    return ingestor_node(state)


# --- entrada de texto livre ---

def test_texto_livre_gera_segmentos_com_ids_contiguos():
    result = run_node("Primeira frase. Segunda frase! Terceira frase?")

    assert [s.id for s in result["segments"]] == ["s01", "s02", "s03"]
    assert result["truncated"] is False
    assert result["warnings"] == []


def test_ids_continuos_mesmo_com_frases_vazias():
    segments = segment_text("Primeira frase.\n\n\n\nSegunda frase.\n \nTerceira frase.")

    assert [s.id for s in segments] == [f"s{i:02d}" for i in range(1, len(segments) + 1)]
    assert all(s.text.strip() for s in segments)


# --- truncamento ---

def test_truncate_words_nao_altera_texto_curto():
    text, truncated = truncate_words("Uma frase curta.", max_words=10)

    assert text == "Uma frase curta."
    assert truncated is False


def test_truncate_words_corta_no_fim_da_ultima_frase_completa():
    text, truncated = truncate_words("Um dois tres. Quatro cinco seis. Sete oito", max_words=7)

    assert truncated is True
    assert text == "Um dois tres. Quatro cinco seis."


def test_truncate_words_sem_pontuacao_corta_no_limite_de_palavras():
    text, truncated = truncate_words("a b c d e f", max_words=3)

    assert truncated is True
    assert text == "a b c"


def test_texto_acima_do_limite_marca_truncated_e_avisa():
    long_text = "Esta é uma frase de teste. " * (MAX_WORDS // 5 + 500)

    result = run_node(long_text)

    assert result["truncated"] is True
    assert result["warnings"] == ["ingestor: texto truncado no limite de tokens"]
    assert len(result["clean_text"].split()) <= MAX_WORDS
    assert not result["clean_text"].endswith("...")
    assert result["segments"]


# --- extração de HTML ---

def test_extract_text_usa_trafilatura_no_html_bom():
    text, title, date = extract_text(ARTIGO_HTML)

    assert "suco de folha de mamão" in text
    assert "Menu Assine" not in text
    assert "Todos os direitos" not in text


def test_extract_text_trafilatura_devolve_titulo_e_data():
    text, title, date = extract_text(ARTIGO_HTML)

    assert title == "Mamão cura dengue?"
    assert date == "2026-03-10"


def test_extract_text_nao_emite_sintaxe_de_tabela():
    html = ARTIGO_HTML.replace(
        "</article>",
        "<table>"
        + "".join(f"<tr><th>Campo{i}</th><td>infecciologia{i}</td></tr>" for i in range(8))
        + "</table></article>",
    )

    text, title, date = extract_text(html)

    assert "|" not in text


def test_extract_text_fallback_bs4_quando_trafilatura_falha(monkeypatch):
    monkeypatch.setattr(ingestor.trafilatura, "extract", lambda *a, **k: None)

    text, title, date = extract_text(ARTIGO_HTML)

    assert "suco de folha de mamão" in text
    assert "Menu Assine" not in text
    assert "Todos os direitos" not in text
    assert title == "Mamão cura dengue?"


def test_extract_text_html_sem_conteudo_devolve_vazio(monkeypatch):
    monkeypatch.setattr(ingestor.trafilatura, "extract", lambda *a, **k: None)

    text, title, date = extract_text("<html><body><script>render()</script></body></html>")

    assert text == ""


# --- URL: fluxo do nó ---

def test_url_com_artigo_preenche_campos(monkeypatch):
    monkeypatch.setattr(ingestor, "fetch_page", lambda url: ARTIGO_HTML)

    result = run_node(URL)

    assert "suco de folha de mamão" in result["clean_text"]
    assert result["segments"]
    assert result["warnings"] == []


def test_url_paywall_devolve_vazio_e_aviso(monkeypatch):
    monkeypatch.setattr(ingestor, "fetch_page", lambda url: None)

    result = run_node(URL)

    assert result["clean_text"] == ""
    assert result["title"] is None
    assert result["published_at"] is None
    assert result["truncated"] is False
    assert result["segments"] == []
    assert result["warnings"] == ["ingestor: conteúdo não extraído (paywall ou página vazia)"]


def test_url_timeout_devolve_vazio_e_aviso(monkeypatch):
    def boom(url):
        raise requests.Timeout()

    monkeypatch.setattr(ingestor, "fetch_page", boom)

    result = run_node(URL)

    assert result["clean_text"] == ""
    assert result["segments"] == []
    assert result["warnings"] == ["ingestor: tempo esgotado ao baixar a página"]


def test_url_pagina_so_javascript_avisa_possivel_renderizacao(monkeypatch):
    html = "<html><body><div id='root'></div><script>render()</script></body></html>"
    monkeypatch.setattr(ingestor, "fetch_page", lambda url: html)

    result = run_node(URL)

    assert result["clean_text"] == ""
    assert result["segments"] == []
    assert result["warnings"] == [
        "ingestor: página sem conteúdo legível (possivelmente renderizada por JavaScript)"
    ]
