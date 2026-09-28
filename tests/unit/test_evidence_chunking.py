"""Testes da divisão das checagens em trechos.

    python -m pytest tests/unit/test_evidence_chunking.py
"""

from src.retrieval.chunking import build_chunks, split_paragraphs


def test_split_paragraphs_descarta_curtos_e_normaliza_espacos():
    text = "Título\n\nPrimeiro   parágrafo com texto suficiente para entrar no índice.\n\nOk.\n"
    assert split_paragraphs(text, min_chars=20) == ["Primeiro parágrafo com texto suficiente para entrar no índice."]


def test_respeita_tamanho_maximo_com_sobreposicao():
    paragraphs = [f"Parágrafo número {i} com algum conteúdo de conclusão da checagem." for i in range(6)]
    chunks = build_chunks("\n".join(paragraphs), max_chars=150, overlap=1, min_chars=10)
    assert len(chunks) > 1
    assert all(len(c) <= 150 for c in chunks)
    for previous, current in zip(chunks, chunks[1:]):   # o último parágrafo de um trecho abre o seguinte
        assert current.split("\n")[0] == previous.split("\n")[-1]
    joined = "\n".join(chunks)
    assert all(p in joined for p in paragraphs)          # nenhum parágrafo se perde


def test_texto_curto_vira_um_trecho_e_texto_vazio_nenhum():
    assert build_chunks("Um parágrafo com texto suficiente para o índice.", min_chars=10) == [
        "Um parágrafo com texto suficiente para o índice."]
    assert build_chunks("") == []
