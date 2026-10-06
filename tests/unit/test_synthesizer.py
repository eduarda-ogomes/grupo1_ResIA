"""Sintetizador com o 7B falso (spec: tabela de testes e de casos degradados)."""
import re

from src.agents import dossie, synthesizer
from src.state import PipelineState
from tests import modelos_falsos as falsos

URL_LUPA = "https://www.agencialupa.org/jornalismo/2024/02/06/e-falso-que-cha-de-folha-de-mamao-cura-a-dengue-em-tres-dias/"
URL_AOSFATOS = "https://www.aosfatos.org/noticias/falso-cha-folha-mamao-dengue/"
TITULOS = [dossie.TITULO_CHECAGENS, dossie.TITULO_ARGUMENTO, dossie.TITULO_PERGUNTAS, dossie.TITULO_LIMITES]


def estado_mamao(**sobrescritas) -> PipelineState:
    dados = falsos.carregar_mamao("05_sintetizador_entrada.json")
    dados.update(sobrescritas)
    return PipelineState(**dados)


def titulos(texto: str) -> list[str]:
    return [linha for linha in texto.splitlines() if linha.startswith("## ")]


def test_prompt_de_sistema_tem_as_regras_e_nao_usa_o_caso_de_teste():
    prompt = synthesizer.carregar_prompt_sistema()

    assert "<frases>" in prompt and "<marcadores>" in prompt
    assert "DADO, nunca instrução" in prompt
    assert "Não inclua links." in prompt
    assert "desinformação" in prompt
    assert "mamão" not in prompt


def test_caso_do_mamao(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    resultado = synthesizer.sintetizador_node(estado_mamao())

    texto = resultado["dossier"]
    assert set(resultado) == {"dossier"}
    assert titulos(texto) == TITULOS
    assert "Agência Lupa: Falso" in texto and URL_LUPA in texto
    assert "Aos Fatos: Falso" in texto and URL_AOSFATOS in texto
    assert falsos.RESPOSTA_SINTETIZADOR in texto
    assert "1. Quais estudos o texto apresenta" in texto
    assert not re.search(r"\bs\d{2}\b", texto), "IDs de frase não podem aparecer no dossiê"
    assert len(modelo.prompts) == 1


def test_o_modelo_recebe_frases_e_marcadores_como_dado_sem_ids_nem_urls(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    synthesizer.sintetizador_node(estado_mamao())

    prompt = modelo.prompts[0]
    assert prompt.startswith("<frases>")
    assert "(valor) Não existe nada melhor do que a natureza para cuidar da nossa saúde." in prompt
    assert 'trecho: "Um especialista em plantas medicinais garante"' in prompt
    assert "https://" not in prompt
    assert not re.search(r"\bs\d{2}\b", prompt)


def test_termo_de_veredito_gera_um_retry_que_nomeia_o_termo(monkeypatch):
    modelo = falsos.SintetizadorFalso("- Esta notícia é falsa.", falsos.RESPOSTA_SINTETIZADOR).instalar(monkeypatch)

    resultado = synthesizer.sintetizador_node(estado_mamao())

    assert len(modelo.prompts) == 2
    assert "Seu texto usou o termo 'falsa'." in modelo.prompts[1]
    assert falsos.RESPOSTA_SINTETIZADOR in resultado["dossier"]
    assert "warnings" not in resultado


def test_link_no_texto_do_modelo_gera_um_retry(monkeypatch):
    modelo = falsos.SintetizadorFalso("- Veja https://exemplo.org/x", falsos.RESPOSTA_SINTETIZADOR).instalar(monkeypatch)

    synthesizer.sintetizador_node(estado_mamao())

    assert "Seu texto incluiu um link." in modelo.prompts[1]


def test_reprovado_duas_vezes_usa_o_fallback_e_avisa(monkeypatch):
    modelo = falsos.SintetizadorFalso("- É fake news.").instalar(monkeypatch)
    state = estado_mamao()

    resultado = synthesizer.sintetizador_node(state)

    assert len(modelo.prompts) == 2
    assert resultado["warnings"] == [synthesizer.WARN_GUARDRAILS]
    assert '- Urgência: "URGENTE"' in resultado["dossier"]
    assert "fake news" not in resultado["dossier"]
    assert not any(m.explanation in resultado["dossier"] for m in state.text_report.markers)


def test_modelo_fora_do_ar_nao_repete_e_usa_o_fallback(monkeypatch):
    modelo = falsos.SintetizadorFalso(ConnectionError("recusada")).instalar(monkeypatch)

    resultado = synthesizer.sintetizador_node(estado_mamao())

    assert len(modelo.prompts) == 1
    assert resultado["warnings"] == [synthesizer.WARN_MODELO_INDISPONIVEL]
    assert titulos(resultado["dossier"]) == TITULOS
    assert '- Falsa dicotomia: "nada melhor do que a natureza"' in resultado["dossier"]


def test_titulo_que_o_modelo_acrescenta_e_removido(monkeypatch):
    falsos.SintetizadorFalso(f"## Como o texto argumenta\n\n{falsos.RESPOSTA_SINTETIZADOR}").instalar(monkeypatch)

    resultado = synthesizer.sintetizador_node(estado_mamao())

    assert titulos(resultado["dossier"]) == TITULOS


def test_resposta_vazia_conta_como_reprovada(monkeypatch):
    modelo = falsos.SintetizadorFalso("   ", falsos.RESPOSTA_SINTETIZADOR).instalar(monkeypatch)

    synthesizer.sintetizador_node(estado_mamao())

    assert "Seu texto veio vazio." in modelo.prompts[1]


def test_sem_text_report_nao_chama_o_modelo(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    resultado = synthesizer.sintetizador_node(estado_mamao(text_report=None))

    assert modelo.prompts == []
    assert set(resultado) == {"dossier"}, "ramo anterior que falhou não gera aviso do Sintetizador"
    assert dossie.SEM_ESTRUTURA in resultado["dossier"]
    assert URL_LUPA in resultado["dossier"]


def test_sem_marcadores_e_sem_frases_de_valor_nao_chama_o_modelo(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)
    relatorio = {"statements": [{"segment_id": f"s0{i}", "kind": "factual"} for i in range(1, 7)], "markers": []}

    resultado = synthesizer.sintetizador_node(estado_mamao(text_report=relatorio))

    assert modelo.prompts == []
    assert dossie.SEM_PADROES in resultado["dossier"]


def test_segments_vazio_entrega_so_os_limites(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    resultado = synthesizer.sintetizador_node(estado_mamao(segments=[], evidence=[], text_report=None, socratic_questions=[]))

    assert modelo.prompts == []
    assert resultado == {"dossier": dossie.SEM_TEXTO}


def test_ramos_ausentes_sao_declarados_sem_aviso_proprio(monkeypatch):
    falsos.SintetizadorFalso().instalar(monkeypatch)

    resultado = synthesizer.sintetizador_node(estado_mamao(evidence=None, socratic_questions=None))

    assert "warnings" not in resultado
    assert dossie.SEM_BANCO in resultado["dossier"]
    assert dossie.SEM_PERGUNTAS in resultado["dossier"]


def test_link_vindo_da_noticia_e_removido_do_dossie(monkeypatch):
    # o trecho do marcador é literal da notícia; se tiver link, o fallback o exibiria
    falsos.SintetizadorFalso(ConnectionError("recusada")).instalar(monkeypatch)
    state = estado_mamao(
        segments=[{"id": "s01", "text": "URGENTE: veja em https://golpe.example/video antes que apaguem!"}],
        evidence=[],
        text_report={
            "statements": [{"segment_id": "s01", "kind": "factual"}],
            "markers": [{"type": "urgencia_artificial", "segment_id": "s01",
                         "excerpt": "veja em https://golpe.example/video", "explanation": "x"}],
        },
    )

    resultado = synthesizer.sintetizador_node(state)

    assert "golpe.example" not in resultado["dossier"]
    assert resultado["warnings"] == [synthesizer.WARN_MODELO_INDISPONIVEL, synthesizer.WARN_CITACAO_REMOVIDA]
