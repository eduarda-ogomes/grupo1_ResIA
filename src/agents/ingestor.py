import json
import re
import unicodedata
import urllib.parse

import requests
import spacy
import spacy.cli
import trafilatura
from bs4 import BeautifulSoup

from src.observabilidade import span
from src.state import PipelineState, Segment

MAX_WORDS = 5000
FETCH_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (compatible; ReliabilityBot/1.0)"

WARN_PAYWALL = "ingestor: conteúdo não extraído (paywall ou página vazia)"
WARN_TIMEOUT = "ingestor: tempo esgotado ao baixar a página"
WARN_JAVASCRIPT = "ingestor: página sem conteúdo legível (possivelmente renderizada por JavaScript)"
WARN_TRUNCATED = "ingestor: texto truncado no limite de tokens"

# Linhas de página que não são conteúdo da matéria (avisos, chamadas, rodapé).
# Casadas em minúsculas e sem acento; a linha inteira sai se algum padrão bater.
PADROES_BOILERPLATE = tuple(re.compile(p) for p in (
    r"^(leia|veja) (tambem|mais)\b",
    r"nao refletem necessariamente",
    r"todos os direitos reservados",
    r"^(receba|assine)\b.*\b(newsletter|noticias|e-?mail)\b",
    r"^siga\b.*\b(instagram|twitter|facebook|tiktok|youtube|redes sociais)\b",
    r"^clique aqui\b",
    r"^publicidade$",
))

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
    extracted = trafilatura.extract(
        html, output_format="json", with_metadata=True, include_tables=False
    )
    if extracted:
        data = json.loads(extracted)
        text = data.get("text") or ""
        if text.strip():
            return text, data.get("title"), data.get("date")
    text, title = _extract_with_bs4(html)
    return text, title, None


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def remover_boilerplate(texto: str) -> str:
    """Tira as linhas de boilerplate (o trafilatura separa parágrafos por \\n) e colapsa as vazias."""
    mantidas = []
    for linha in texto.splitlines():
        if not linha.strip():
            continue
        normalizada = _sem_acento(linha.strip().lower())
        if any(padrao.search(normalizada) for padrao in PADROES_BOILERPLATE):
            continue
        mantidas.append(linha)
    return "\n".join(mantidas)


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
    """Frases numeradas (s01, s02...).

    Fragmento só de pontuação ("URGENTE!!!" vira "URGENTE!!" e "!" no spaCy) volta para a
    frase anterior, pelo trecho original; antes da primeira frase, é descartado.
    """
    trechos: list[tuple[int, int]] = []  # (início, fim) de cada frase em `text`
    for sent in get_nlp()(text).sents:
        if not sent.text.strip():
            continue
        if not any(c.isalnum() for c in sent.text):
            if trechos:
                trechos[-1] = (trechos[-1][0], sent.end_char)
            continue
        trechos.append((sent.start_char, sent.end_char))
    return [Segment(id=f"s{i:02d}", text=text[inicio:fim].strip()) for i, (inicio, fim) in enumerate(trechos, start=1)]


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
        with span("ingestor.baixar", url=raw_input) as s:
            try:
                html = fetch_page(raw_input)
            except requests.Timeout:
                s.set_attribute("pipeline.ok", False)
                return _empty_result(WARN_TIMEOUT)
            s.set_attribute("pipeline.ok", bool(html))
        if not html:
            return _empty_result(WARN_PAYWALL)
        clean_text, title, published_at = extract_text(html)
        if not clean_text.strip():
            return _empty_result(WARN_JAVASCRIPT)
        clean_text = remover_boilerplate(clean_text)
    else:
        clean_text = raw_input

    clean_text, truncated = truncate_words(clean_text)
    warnings = [WARN_TRUNCATED] if truncated else []
    with span("ingestor.segmentar", truncado=truncated) as s:
        segments = segment_text(clean_text)
        s.set_attribute("pipeline.frases", len(segments))

    return {
        "clean_text": clean_text,
        "title": title,
        "published_at": published_at,
        "truncated": truncated,
        "segments": segments,
        "warnings": warnings,
    }
