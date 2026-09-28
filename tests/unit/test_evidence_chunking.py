"""Testes da divisão em trechos e da marcação "descreve o boato".

    python -m pytest tests/unit/test_evidence_chunking.py
"""

import pytest

from src.retrieval.chunking import build_chunks, describes_rumor, split_paragraphs


@pytest.mark.parametrize(
    "paragraph",
    [
        "Circula nas redes sociais um vídeo em que um homem afirma que o chá cura a dengue.",
        "Circula no WhatsApp uma mensagem sobre a vacina.",
        "Um vídeo que viralizou no TikTok diz que a urna foi fraudada.",
        "Posts publicados no Facebook alegam que o governo cortou o benefício.",
        "Segundo a publicação, o remédio é distribuído de graça.",
        "O conteúdo foi compartilhado nas redes mais de 10 mil vezes.",
    ],
)
def test_descreve_boato(paragraph):
    assert describes_rumor(paragraph)


@pytest.mark.parametrize(
    "paragraph",
    [
        "Não existe um tratamento específico para a dengue e as formas graves da doença.",
        "O vírus da dengue circula com mais intensidade no verão.",
        "Procurado, o Ministério da Saúde informou que não há estudos que comprovem o efeito.",
        "Os estudos citados não comprovam que o tratamento seja eficaz em humanos.",
    ],
)
def test_nao_descreve_boato(paragraph):
    assert not describes_rumor(paragraph)


@pytest.mark.parametrize(
    "paragraph",
    [
        # Conclusões reais do corpus que a versão de 26/09 marcava como boato.
        "É falso que um vídeo mostra tropas americanas em solo brasileiro para capturar o presidente Lula.",
        "São enganosas as publicações que afirmam que o ministro Gilmar Mendes teve um encontro secreto.",
        "Não é verdade que a cantora Ivete Sangalo tenha elogiado o presidente. O registro que circula nas redes é antigo.",
        "Foi gerado por IA o vídeo que supostamente mostra uma equipe do Bope filmando a sede do Comando Vermelho.",
        "Um vídeo que circula nas redes engana ao orientar os vacinados a realizar exames de coagulação.",
        "Vídeo que circula nas redes sociais como se fosse atual foi gravado em maio de 2022.",
        "A imagem circula nas redes sociais como se fosse um registro verdadeiro.",
    ],
)
def test_conclusao_que_menciona_o_post_nao_e_boato(paragraph):
    assert not describes_rumor(paragraph)


def test_split_paragraphs_descarta_curtos_e_normaliza_espacos():
    text = "Título\n\nPrimeiro   parágrafo com texto suficiente para entrar no índice.\n\nOk.\n"
    assert split_paragraphs(text, min_chars=20) == ["Primeiro parágrafo com texto suficiente para entrar no índice."]


def test_trecho_nunca_mistura_boato_e_conclusao():
    text = "\n".join(
        [
            "Circula nas redes um vídeo em que um homem afirma que o chá de mamão cura a dengue.",
            "Não existe um tratamento específico para a dengue e as formas graves da doença.",
            "O Ministério da Saúde recomenda hidratação e acompanhamento médico.",
        ]
    )
    chunks = build_chunks(text, max_chars=800, overlap=1, min_chars=10)
    assert [c.describes_rumor for c in chunks] == [True, False]
    assert "Circula" not in chunks[1].text
    assert chunks[1].text.count("\n") == 1  # os dois parágrafos de conclusão juntos


def test_respeita_tamanho_maximo_com_sobreposicao():
    paragraphs = [f"Parágrafo número {i} com algum conteúdo de conclusão da checagem." for i in range(6)]
    chunks = build_chunks("\n".join(paragraphs), max_chars=150, overlap=1, min_chars=10)
    assert len(chunks) > 1
    assert all(len(c.text) <= 150 for c in chunks)
    # Sobreposição: o último parágrafo de um trecho abre o seguinte.
    for previous, current in zip(chunks, chunks[1:]):
        assert current.text.split("\n")[0] == previous.text.split("\n")[-1]
    # Nenhum parágrafo se perde.
    joined = "\n".join(c.text for c in chunks)
    assert all(p in joined for p in paragraphs)


def test_texto_vazio():
    assert build_chunks("") == []
