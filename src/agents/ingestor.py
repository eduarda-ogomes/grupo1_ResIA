import urllib.parse
import trafilatura
import json
from src.state import PipelineState

def is_url(text: str) -> bool:
    try:
        result = urllib.parse.urlparse(text)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def ingestor_node(state: PipelineState) -> dict:
    raw_input = state.raw_input.strip()
    
    if is_url(raw_input):
        html_content = trafilatura.fetch_url(raw_input)
        if not html_content:
            return {"clean_text": "Erro ao tentar acessar a URL.", "title": "Falha na Extração"}
    else:
        html_content = raw_input

    extracted_json = trafilatura.extract(html_content, output_format='json')
    if extracted_json:
        data = json.loads(extracted_json)
        clean_text = data.get('text', '')
        title = data.get('title', 'Sem Título')
        date = data.get('date', None)
    else:
        clean_text = html_content
        title = "Texto Inserido Manualmente"
        date = None

    MAX_CHARS = 5000
    if len(clean_text) > MAX_CHARS:
        clean_text = clean_text[:MAX_CHARS] + "\n\n[TEXTO TRUNCADO POR SEGURANÇA]"
        
    return {"clean_text": clean_text, "title": title, "date": date}
