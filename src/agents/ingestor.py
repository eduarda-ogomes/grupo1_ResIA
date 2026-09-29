import json
import re
import urllib.parse

import requests
import spacy
import spacy.cli
import trafilatura
from bs4 import BeautifulSoup

from src.state import PipelineState, Segment

MAX_WORDS = 5000
FETCH_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (compatible; ReliabilityBot/1.0)"

WARN_PAYWALL = "ingestor: conteúdo não extraído (paywall ou página vazia)"
WARN_TIMEOUT = "ingestor: tempo esgotado ao baixar a página"
WARN_JAVASCRIPT = "ingestor: página sem conteúdo legível (possivelmente renderizada por JavaScript)"
WARN_TRUNCATED = "ingestor: texto truncado no limite de tokens"

# Inicializa o modelo de NLP para português de forma lazy (segura)
nlp = None


def get_nlp():
    global nlp
    if nlp is None:
        try:
            nlp = spacy.load("pt_core_news_sm")
        except OSError:
            spacy.cli.download("pt_core_news_sm")
            nlp = spacy.load("pt_core_news_sm")
    return nlp


def is_url(text: str) -> bool:
    try:
        result = urllib.parse.urlparse(text)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False


def fetch_page(url: str) -> str | None:
    """Baixa o HTML da página. Devolve None se bloqueada ou vazia; levanta requests.Timeout."""
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=FETCH_TIMEOUT)
        if response.ok and response.text.strip():
            return response.text
    except requests.Timeout:
        raise
    except requests.RequestException:
        pass
    return trafilatura.fetch_url(url)


def _extract_with_bs4(html: str) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    container = soup.find("article") or soup.body or soup
    paragraphs = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    text = "\n".join(p for p in paragraphs if p)
    title = soup.title.get_text(strip=True) if soup.title else None
    return text, title


def extract_text(html: str) -> tuple[str, str | None, str | None]:
    """Extrai (texto, título, data) do HTML: trafilatura primeiro, BeautifulSoup como fallback."""
    extracted = trafilatura.extract(html, output_format="json")
    if extracted:
        data = json.loads(extracted)
        text = data.get("text") or ""
        if text.strip():
            return text, data.get("title"), data.get("date")
    text, title = _extract_with_bs4(html)
    return text, title, None


def truncate_words(text: str, max_words: int = MAX_WORDS) -> tuple[str, bool]:
    """Limita o texto a max_words, cortando no fim da última frase completa."""
    words = list(re.finditer(r"\S+", text))
    if len(words) <= max_words:
        return text, False
    cut = text[: words[max_words - 1].end()]
    last_end = max(cut.rfind(mark) for mark in ".!?")
    if last_end > 0:
        cut = cut[: last_end + 1]
    return cut, True


def segment_text(text: str) -> list[Segment]:
    segments = []
    for sent in get_nlp()(text).sents:
        sentence = sent.text.strip()
        if sentence:
            segments.append(Segment(id=f"s{len(segments) + 1:02d}", text=sentence))
    return segments


def _empty_result(warning: str) -> dict:
    return {
        "clean_text": "",
        "title": None,
        "published_at": None,
        "truncated": False,
        "segments": [],
        "warnings": [warning],
    }


def ingestor_node(state: PipelineState) -> dict:
    raw_input = state.raw_input.strip()
    title = "Texto Inserido Manualmente"
    published_at = None

    if is_url(raw_input):
        try:
            html = fetch_page(raw_input)
        except requests.Timeout:
            return _empty_result(WARN_TIMEOUT)
        if not html:
            return _empty_result(WARN_PAYWALL)
        clean_text, title, published_at = extract_text(html)
        if not clean_text.strip():
            return _empty_result(WARN_JAVASCRIPT)
    else:
        clean_text = raw_input

    clean_text, truncated = truncate_words(clean_text)
    warnings = [WARN_TRUNCATED] if truncated else []

    return {
        "clean_text": clean_text,
        "title": title,
        "published_at": published_at,
        "truncated": truncated,
        "segments": segment_text(clean_text),
        "warnings": warnings,
    }
