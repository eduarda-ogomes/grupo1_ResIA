import urllib.parse
import trafilatura
import json
import spacy
import spacy.cli
from src.state import PipelineState, Segment

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

def ingestor_node(state: PipelineState) -> dict:
    raw_input = state.raw_input.strip()
    clean_text = ""
    title = "Texto Inserido Manualmente"
    date = None
    truncated = False
    
    # 1. Extração
    if is_url(raw_input):
        html_content = trafilatura.fetch_url(raw_input)
        if not html_content:
            clean_text = "Erro: Site bloqueou o acesso ou está fora do ar. Cole o texto da matéria manualmente."
            title = "Falha na Extração (Paywall/Bloqueio)"
        else:
            extracted_json = trafilatura.extract(html_content, output_format='json')
            if extracted_json:
                data = json.loads(extracted_json)
                clean_text = data.get('text', '')
                title = data.get('title', 'Sem Título')
                date = data.get('date', None)
            else:
                clean_text = "Erro: Não foi possível extrair o conteúdo legível desta página."
                title = "Falha no Parse HTML"
    else:
        clean_text = raw_input

    # 2. Truncamento (Limite Rígido)
    MAX_CHARS = 5000
    if len(clean_text) > MAX_CHARS:
        clean_text = clean_text[:MAX_CHARS] + "..."
        truncated = True

    # 3. Segmentação (Sentence Splitting)
    segments = []
    if clean_text and not clean_text.startswith("Erro:"):
        nlp_model = get_nlp()
        doc = nlp_model(clean_text)
        for i, sent in enumerate(doc.sents):
            if sent.text.strip():
                segments.append(Segment(
                    id=f"s{i+1:02d}",  # Gera s01, s02, etc.
                    text=sent.text.strip()
                ))

    return {
        "clean_text": clean_text, 
        "title": title, 
        "date": date, 
        "truncated": truncated,
        "segments": segments
    }
