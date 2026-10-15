"""Argumento estruturado e Sintetizador com o 7B falso (spec: tabela de testes e de casos degradados)."""
import json
import re

from src.agents.synthesizer import dossie, agent as synthesizer
from src.state import PipelineState
from tests import modelos_falsos as falsos

URL_LUPA = "https://www.agencialupa.org/jornalismo/2024/02/06/e-falso-que-cha-de-folha-de-mamao-cura-a-dengue-em-tres-dias/"
URL_AOSFATOS = "https://www.aosfatos.org/noticias/falso-cha-folha-mamao-dengue/"
TITULOS = [dossie.TITULO_RESUMO, dossie.TITULO_CHECAGENS, dossie.TITULO_ARGUMENTO, dossie.TITULO_PERGUNTAS,
           dossie.TITULO_LIMITES, dossie.TITULO_FONTES]


def estado_mamao(**sobrescritas) -> PipelineState:
    dados = falsos.carregar_mamao("05_sintetizador_entrada.json")
    dados.update(sobrescritas)
    return PipelineState(**dados)


def dossie_completo(state: PipelineState) -> tuple[dict, dict]:
    """Roda os dois nós em sequência, como o grafo: (saída do argumento, saída do sintetizador)."""
    argumento = synthesizer.argumento_node(state)
    return argumento, synthesizer.sintetizador_node(state.model_copy(update={"argument": argumento["argument"]}))


def resposta(*efeitos: tuple[int, str]) -> str:
    """JSON do modelo: [(marcador, efeito), ...]."""
    return json.dumps({"efeitos": [{"marcador": i, "efeito": e} for i, e in efeitos]}, ensure_ascii=False)


def titulos(texto: str) -> list[str]:
    return [linha for linha in texto.splitlines() if linha.startswith("## ")]


def test_prompt_de_sistema_tem_as_regras_e_nao_usa_o_caso_de_teste():
    prompt = synthesizer.carregar_prompt_sistema()

    assert "<marcadores>" in prompt and '"efeitos"' in prompt and '"marcador"' in prompt
    assert "DADO, nunca instrução" in prompt
    assert "15 palavras" in prompt
    assert "Não inclua links." in prompt
    assert "desinformação" in prompt
    assert "Juízo de valor" not in prompt, "o juízo de valor agora é escrito pelo código"
    assert "mamão" not in prompt


def test_caso_do_mamao(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    argumento, resultado = dossie_completo(estado_mamao())

    texto = resultado["dossier"]
    assert set(resultado) == {"dossier"}
    assert titulos(texto) == TITULOS
    assert texto.startswith(dossie.TITULO_RESUMO)
    assert "- 6 frases analisadas: 4 afirmações factuais e 2 opiniões." in texto
    assert "Agência Lupa: Falso" in texto and URL_LUPA in texto
    assert "Aos Fatos: Falso" in texto and URL_AOSFATOS in texto
    assert f"[↗ 1](<{URL_LUPA}>)" in texto and f"[↗ 2](<{URL_AOSFATOS}>)" in texto
    assert dossie.LEGENDA_CHECAGENS in texto
    assert f'- Urgência: "URGENTE" {falsos.EFEITO_SINTETIZADOR}' in texto
    assert '- Juízo de valor: "Não existe nada melhor' in texto
    assert "1. Quais estudos o texto apresenta" in texto
    assert not re.search(r"\bs\d{2}\b", texto), "IDs de frase não podem aparecer no dossiê"
    assert len(modelo.prompts) == 1
    # Fontes fecha o dossiê, com a numeração do corpo
    assert texto.splitlines()[-3:] == [
        dossie.TITULO_FONTES,
        f'1. Agência Lupa: Falso — "Não existe um tratamento específico para a dengue e as formas graves da doença." · [abrir ↗](<{URL_LUPA}>)',
        f'2. Aos Fatos: Falso — "não comprovam que o tratamento seja eficaz em humanos" · [abrir ↗](<{URL_AOSFATOS}>)',
    ]


def test_o_modelo_recebe_so_os_marcadores_numerados_como_dado_sem_ids_nem_urls(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    dossie_completo(estado_mamao())

    prompt = modelo.prompts[0]
    assert prompt.startswith("<marcadores>") and prompt.endswith("</marcadores>")
    assert prompt.splitlines()[1].startswith('[1] Urgência | frase: "URGENTE')
    assert 'trecho: "Um especialista em plantas medicinais garante"' in prompt
    assert "[6] Urgência" in prompt and "[7]" not in prompt
    assert "<frases>" not in prompt
    assert "https://" not in prompt
    assert not re.search(r"\bs\d{2}\b", prompt)


def test_termo_de_veredito_gera_um_retry_que_nomeia_o_marcador_e_o_termo(monkeypatch):
    modelo = falsos.SintetizadorFalso(
        resposta((1, "Esta notícia é falsa.")), falsos.RESPOSTA_SINTETIZADOR).instalar(monkeypatch)

    argumento, resultado = dossie_completo(estado_mamao())

    assert len(modelo.prompts) == 2
    assert modelo.prompts[1].endswith("O efeito do marcador 1 foi rejeitado. Seu texto usou o termo 'falsa'.")
    assert f'- Urgência: "URGENTE" {falsos.EFEITO_SINTETIZADOR}' in resultado["dossier"]
    assert "warnings" not in argumento and "warnings" not in resultado


def test_link_no_efeito_gera_um_retry(monkeypatch):
    modelo = falsos.SintetizadorFalso(
        resposta((1, "Veja https://exemplo.org/x")), falsos.RESPOSTA_SINTETIZADOR).instalar(monkeypatch)

    dossie_completo(estado_mamao())

    assert modelo.prompts[1].endswith("O efeito do marcador 1 foi rejeitado. Seu texto incluiu um link.")


def test_reprovado_duas_vezes_deixa_o_marcador_sem_efeito_e_avisa(monkeypatch):
    modelo = falsos.SintetizadorFalso(resposta((1, "É fake news."))).instalar(monkeypatch)
    state = estado_mamao()

    argumento, resultado = dossie_completo(state)

    assert len(modelo.prompts) == 2
    assert argumento["warnings"] == [synthesizer.WARN_GUARDRAILS]
    assert '- Urgência: "URGENTE"\n' in resultado["dossier"]
    assert "fake news" not in resultado["dossier"]
    assert not any(m.explanation in resultado["dossier"] for m in state.text_report.markers)


def test_modelo_fora_do_ar_nao_repete_e_deixa_todos_sem_efeito(monkeypatch):
    modelo = falsos.SintetizadorFalso(ConnectionError("recusada")).instalar(monkeypatch)

    argumento, resultado = dossie_completo(estado_mamao())

    assert len(modelo.prompts) == 1
    assert argumento["warnings"] == [synthesizer.WARN_MODELO_INDISPONIVEL]
    assert argumento["argument"] == dossie.linhas_argumento(estado_mamao(), {})
    assert titulos(resultado["dossier"]) == TITULOS
    assert '- Falsa dicotomia: "nada melhor do que a natureza"\n' in resultado["dossier"]


def test_efeito_vazio_conta_como_reprovado(monkeypatch):
    modelo = falsos.SintetizadorFalso(resposta((1, "   ")), falsos.RESPOSTA_SINTETIZADOR).instalar(monkeypatch)

    dossie_completo(estado_mamao())

    assert modelo.prompts[1].endswith("O efeito do marcador 1 foi rejeitado. Seu texto veio vazio.")


def test_json_dentro_de_cerca_e_aceito_sem_retry_nem_aviso(monkeypatch):
    cercado = f"```json\n{resposta((1, 'pede pressa.'))}\n```"
    modelo = falsos.SintetizadorFalso(cercado).instalar(monkeypatch)

    saida = synthesizer.argumento_node(estado_mamao())

    assert saida["argument"][0] == '- Urgência: "URGENTE" pede pressa.'
    assert "warnings" not in saida and len(modelo.prompts) == 1


def test_resposta_ilegivel_provoca_um_retry_e_vale_a_segunda(monkeypatch):
    modelo = falsos.SintetizadorFalso("- Urgência: pede pressa.", resposta((1, "pede pressa."))).instalar(monkeypatch)

    saida = synthesizer.argumento_node(estado_mamao())

    assert len(modelo.prompts) == 2
    assert modelo.prompts[1].endswith("Sua resposta não era um JSON no formato pedido.")
    assert saida["argument"][0] == '- Urgência: "URGENTE" pede pressa.'
    assert "warnings" not in saida


def test_resposta_ilegivel_duas_vezes_deixa_todos_sem_efeito_e_avisa(monkeypatch):
    modelo = falsos.SintetizadorFalso("não sei", '{"efeitos": 3}').instalar(monkeypatch)

    saida = synthesizer.argumento_node(estado_mamao())

    assert len(modelo.prompts) == 2
    assert saida["argument"] == dossie.linhas_argumento(estado_mamao(), {})
    assert saida["warnings"] == [synthesizer.WARN_SAIDA_INVALIDA]


def test_retry_ilegivel_mantem_os_efeitos_aprovados_da_primeira_tentativa(monkeypatch):
    falsos.SintetizadorFalso(resposta((1, "pede pressa."), (2, "é uma mentira.")), "lixo").instalar(monkeypatch)

    saida = synthesizer.argumento_node(estado_mamao())

    assert saida["argument"][0] == '- Urgência: "URGENTE" pede pressa.'
    assert saida["warnings"] == [synthesizer.WARN_GUARDRAILS, synthesizer.WARN_SAIDA_INVALIDA]


def test_sem_text_report_nao_chama_o_modelo(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    argumento, resultado = dossie_completo(estado_mamao(text_report=None))

    assert modelo.prompts == []
    assert set(resultado) == {"dossier"}, "ramo anterior que falhou não gera aviso do Sintetizador"
    assert dossie.SEM_ESTRUTURA in resultado["dossier"]
    assert URL_LUPA in resultado["dossier"]


def test_sem_marcadores_e_sem_frases_de_valor_nao_chama_o_modelo(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)
    relatorio = {"statements": [{"segment_id": f"s0{i}", "kind": "factual"} for i in range(1, 7)], "markers": []}

    argumento, resultado = dossie_completo(estado_mamao(text_report=relatorio))

    assert modelo.prompts == []
    assert dossie.SEM_PADROES in resultado["dossier"]


def test_segments_vazio_entrega_so_os_limites(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    argumento, resultado = dossie_completo(estado_mamao(segments=[], evidence=[], text_report=None, socratic_questions=[]))

    assert modelo.prompts == []
    assert resultado == {"dossier": dossie.SEM_TEXTO}


def test_ramos_ausentes_sao_declarados_sem_aviso_proprio(monkeypatch):
    falsos.SintetizadorFalso().instalar(monkeypatch)

    argumento, resultado = dossie_completo(estado_mamao(evidence=None, socratic_questions=None))

    assert "warnings" not in argumento and "warnings" not in resultado
    assert dossie.SEM_BANCO in resultado["dossier"]
    assert dossie.SEM_PERGUNTAS in resultado["dossier"]


def test_sem_evidencia_o_dossie_nao_tem_fontes_nem_bloco_em_branco_no_fim(monkeypatch):
    falsos.SintetizadorFalso().instalar(monkeypatch)

    argumento, resultado = dossie_completo(estado_mamao(evidence=[]))

    texto = resultado["dossier"]
    assert titulos(texto) == [t for t in TITULOS if t != dossie.TITULO_FONTES]
    assert texto.endswith(dossie.LIMITE_COLETA), "sem Fontes, o dossiê termina em Limites, sem bloco vazio"
    assert not texto.endswith("\n")
    assert "\n\n\n" not in texto


def test_sem_banco_o_dossie_tambem_nao_tem_fontes(monkeypatch):
    falsos.SintetizadorFalso().instalar(monkeypatch)

    argumento, resultado = dossie_completo(estado_mamao(evidence=None))

    assert dossie.TITULO_FONTES not in titulos(resultado["dossier"])
    assert "- O banco de checagens não pôde ser consultado." in resultado["dossier"]


def estado_com_cifrao(**sobrescritas) -> PipelineState:
    return estado_mamao(
        segments=[{"id": "s01", "text": "O kit custa R$ 10 hoje e R$ 20 amanhã."}],
        evidence=[],
        text_report={"statements": [{"segment_id": "s01", "kind": "valor"}],
                     "markers": [{"type": "urgencia_artificial", "segment_id": "s01",
                                  "excerpt": "R$ 10 hoje", "explanation": "x"}]},
        **sobrescritas,
    )


def test_efeito_com_cifrao_e_escapado_depois_dos_guardrails(monkeypatch):
    # O Streamlit renderiza $...$ como LaTeX: o efeito sai escapado, mas o modelo e os guardrails veem o original
    modelo = falsos.SintetizadorFalso(resposta((1, "custa R$ 10."))).instalar(monkeypatch)

    argumento, resultado = dossie_completo(estado_com_cifrao())

    texto = resultado["dossier"]
    assert 'trecho: "R$ 10 hoje"' in modelo.prompts[0]
    assert len(modelo.prompts) == 1 and "warnings" not in argumento
    assert argumento["argument"][0] == '- Urgência: "R\\$ 10 hoje" custa R\\$ 10.'
    assert argumento["argument"][0].endswith("custa R\\$ 10.")
    assert not re.search(r"(?<!\\)\$", texto), "nenhum cifrão sobra sem escape no dossiê"


def test_markdown_do_efeito_e_escapado_e_a_linha_continua_numa_so(monkeypatch):
    falsos.SintetizadorFalso(resposta((1, "pede *pressa*\ncom [link_x]."))).instalar(monkeypatch)

    linhas = synthesizer.argumento_node(estado_com_cifrao())["argument"]

    assert linhas[0] == '- Urgência: "R\\$ 10 hoje" pede \\*pressa\\* com \\[link\\_x\\].'


def test_perguntas_do_socratico_saem_escapadas_no_dossie(monkeypatch):
    falsos.SintetizadorFalso().instalar(monkeypatch)

    texto = synthesizer.sintetizador_node(estado_mamao(socratic_questions=["O preço de R$ 10 é real?"]))["dossier"]

    assert r"1. O preço de R\$ 10 é real?" in texto


def test_link_vindo_da_noticia_e_neutralizado_no_dossie(monkeypatch):
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

    argumento, resultado = dossie_completo(state)

    assert "golpe.example" not in resultado["dossier"]
    assert '- Urgência: "veja em [link]"' in resultado["dossier"]
    assert argumento["warnings"] == [synthesizer.WARN_MODELO_INDISPONIVEL]


def test_sintetizador_sem_argumento_monta_com_o_fallback_e_nao_chama_o_modelo(monkeypatch):
    # argument None = o agente_argumento não reportou (ex.: estourou o tempo sem recuperação)
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    resultado = synthesizer.sintetizador_node(estado_mamao(argument=None))

    assert modelo.prompts == []
    assert set(resultado) == {"dossier"}
    assert titulos(resultado["dossier"]) == TITULOS
    assert '- Urgência: "URGENTE"' in resultado["dossier"]
    assert URL_LUPA in resultado["dossier"]


def test_sintetizador_usa_o_argument_do_estado_sem_chamar_o_modelo(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    resultado = synthesizer.sintetizador_node(estado_mamao(argument=["- Linha pronta do argumento."]))

    assert modelo.prompts == []
    assert f"{dossie.TITULO_ARGUMENTO}\n- Linha pronta do argumento." in resultado["dossier"]
    assert '- Urgência: "URGENTE"' not in resultado["dossier"]


def test_sintetizador_avisa_quando_a_rede_de_seguranca_remove_uma_citacao(monkeypatch):
    # a rede de segurança roda na montagem: URL fora das evidências sai do dossiê, com aviso
    falsos.SintetizadorFalso().instalar(monkeypatch)

    resultado = synthesizer.sintetizador_node(estado_mamao(argument=["- Veja https://golpe.example/x agora."]))

    assert "golpe.example" not in resultado["dossier"]
    assert resultado["warnings"] == [synthesizer.WARN_CITACAO_REMOVIDA]


def test_argumento_fallback_devolve_as_linhas_do_fallback_em_codigo(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)

    resultado = synthesizer.argumento_fallback(estado_mamao())

    assert modelo.prompts == []
    assert set(resultado) == {"argument"}
    assert '- Urgência: "URGENTE"' in resultado["argument"]
    assert dossie.TITULO_ARGUMENTO not in resultado["argument"]


def test_argumento_fallback_sem_text_report_declara_a_ausencia():
    assert synthesizer.argumento_fallback(estado_mamao(text_report=None)) == {"argument": [dossie.SEM_ESTRUTURA]}


def test_argumento_node_devolve_as_linhas_sem_o_titulo(monkeypatch):
    falsos.SintetizadorFalso().instalar(monkeypatch)

    resultado = synthesizer.argumento_node(estado_mamao())

    assert resultado == {"argument": dossie.linhas_argumento(estado_mamao(), {1: falsos.EFEITO_SINTETIZADOR})}
    assert dossie.TITULO_ARGUMENTO not in resultado["argument"]


def test_sem_text_report_argumento_nao_chama_o_modelo(monkeypatch):     # Review Focus 2
    falso = falsos.SintetizadorFalso().instalar(monkeypatch)
    assert synthesizer.argumento_node(estado_mamao(text_report=None)) == {"argument": [dossie.SEM_ESTRUTURA]}
    assert falso.prompts == []


def test_so_opinioes_sem_marcadores_nao_chama_o_modelo(monkeypatch):
    # sem marcador não há efeito a escrever: a linha de juízo de valor é código puro
    falso = falsos.SintetizadorFalso().instalar(monkeypatch)
    sem_marcadores = {"statements": [{"segment_id": "s05", "kind": "valor"}], "markers": []}

    saida = synthesizer.argumento_node(estado_mamao(text_report=sem_marcadores))

    assert falso.prompts == []
    assert saida == {"argument": ['- Juízo de valor: "Não existe nada melhor do que a natureza para cuidar da nossa saúde." '
                                  'é uma opinião e não foi checada.']}


def test_links_da_noticia_nao_chegam_ao_modelo(monkeypatch):
    modelo = falsos.SintetizadorFalso().instalar(monkeypatch)
    state = estado_mamao(
        segments=[{"id": "s01", "text": "Isso é lindo, veja https://golpe.example/v"}],
        evidence=[],
        text_report={"statements": [{"segment_id": "s01", "kind": "valor"}],
                     "markers": [{"type": "adjetivacao_extrema", "segment_id": "s01",
                                  "excerpt": "Isso é lindo, veja https://golpe.example/v", "explanation": "veja https://golpe.example/e"}]},
    )

    argumento, _ = dossie_completo(state)

    assert "golpe.example" not in modelo.prompts[0]
    assert "veja [link]" in modelo.prompts[0]
    assert "golpe.example" not in "\n".join(argumento["argument"])


def test_mamao_com_efeitos_estruturados(monkeypatch):
    seis = {"efeitos": [{"marcador": i, "efeito": "pede atenção imediata."} for i in range(1, 7)]}
    falsos.SintetizadorFalso(json.dumps(seis)).instalar(monkeypatch)
    linhas = synthesizer.argumento_node(estado_mamao())["argument"]
    assert linhas[0] == '- Urgência: "URGENTE" pede atenção imediata.'
    assert linhas[-1] == ('- Juízo de valor: "Não existe nada melhor do que a natureza para cuidar da nossa saúde." e '
                          '"Compartilhe com todos antes que apaguem este vídeo!" são opiniões e não foram checadas.')


def test_indice_invalido_ou_repetido_e_ignorado_sem_retry(monkeypatch):     # Review Focus 3
    ruins = {"efeitos": [{"marcador": 99, "efeito": "x x x"}, {"marcador": 1, "efeito": "a."}, {"marcador": 1, "efeito": "b."}]}
    falso = falsos.SintetizadorFalso(json.dumps(ruins)).instalar(monkeypatch)
    saida = synthesizer.argumento_node(estado_mamao())
    assert saida["argument"][0] == '- Urgência: "URGENTE" a.' and saida["argument"][1] == '- Generalização: "os médicos estão escondendo"'
    assert "warnings" not in saida and len(falso.prompts) == 1


def test_lista_vazia_deixa_todos_sem_efeito_sem_retry(monkeypatch):
    falso = falsos.SintetizadorFalso(json.dumps({"efeitos": []})).instalar(monkeypatch)
    saida = synthesizer.argumento_node(estado_mamao())
    assert saida["argument"][0] == '- Urgência: "URGENTE"' and len(falso.prompts) == 1
    assert "warnings" not in saida


def test_efeito_com_termo_de_fora_vai_ao_retry_e_cai_sem_efeito(monkeypatch):
    ruim = {"efeitos": [{"marcador": 1, "efeito": "segundo a OMS, exagera."}]}
    falso = falsos.SintetizadorFalso(json.dumps(ruim), json.dumps(ruim)).instalar(monkeypatch)
    saida = synthesizer.argumento_node(estado_mamao())
    assert saida["argument"][0] == '- Urgência: "URGENTE"' and saida["warnings"] == [synthesizer.WARN_GUARDRAILS]
    assert falso.prompts[1].endswith("O efeito do marcador 1 foi rejeitado. Seu texto mencionou 'oms', que não aparece na notícia.")


def test_trecho_inventado_no_efeito_dispara_retry_com_o_trecho_nomeado(monkeypatch):
    modelo = falsos.SintetizadorFalso(
        resposta((1, 'cita "corra antes que seja tarde" e pede pressa.')),
        resposta((1, "pede ação imediata.")),
    ).instalar(monkeypatch)

    argumento, resultado = dossie_completo(estado_mamao())

    assert len(modelo.prompts) == 2
    assert modelo.prompts[1].endswith(
        'O efeito do marcador 1 foi rejeitado. Seu texto citou "corra antes que seja tarde", que não está em nenhuma frase da notícia.')
    assert '- Urgência: "URGENTE" pede ação imediata.' in resultado["dossier"]
    assert "warnings" not in argumento and "warnings" not in resultado


def test_retry_nomeia_o_primeiro_marcador_reprovado(monkeypatch):
    modelo = falsos.SintetizadorFalso(
        resposta((1, "pede pressa."), (3, "é uma mentira."), (4, "cita a OMS.")), resposta((3, "soa exagerado."), (4, "não diz quem é."))
    ).instalar(monkeypatch)

    saida = synthesizer.argumento_node(estado_mamao())

    assert modelo.prompts[1].endswith("O efeito do marcador 3 foi rejeitado. Seu texto usou o termo 'mentira'.")
    assert "warnings" not in saida


def test_depois_do_retry_vale_o_melhor_efeito_de_cada_marcador_entre_as_duas_tentativas(monkeypatch):
    # 1ª: marcador 1 válido, 2 reprovado; 2ª: o 1 volta reprovado, o 2 vem válido. Os dois ficam.
    falso = falsos.SintetizadorFalso(
        resposta((1, "pede pressa."), (2, "é uma mentira.")),
        resposta((1, "é falso."), (2, "generaliza sem dizer quem.")),
    ).instalar(monkeypatch)

    saida = synthesizer.argumento_node(estado_mamao())

    assert saida["argument"][0] == '- Urgência: "URGENTE" pede pressa.'
    assert saida["argument"][1] == '- Generalização: "os médicos estão escondendo" generaliza sem dizer quem.'
    assert "warnings" not in saida and len(falso.prompts) == 2


def test_marcador_reprovado_e_corrigido_no_retry_nao_avisa_mesmo_com_outro_sem_efeito(monkeypatch):
    falsos.SintetizadorFalso(resposta((1, "é uma mentira.")), resposta((1, "pede pressa."))).instalar(monkeypatch)

    saida = synthesizer.argumento_node(estado_mamao())

    assert saida["argument"][0] == '- Urgência: "URGENTE" pede pressa.'
    assert saida["argument"][2] == '- Adjetivação extrema: "em apenas três dias"'
    assert "warnings" not in saida


def test_falha_no_retry_mantem_os_efeitos_da_primeira_tentativa(monkeypatch):
    falso = falsos.SintetizadorFalso(
        resposta((1, "pede pressa."), (2, "é uma mentira.")), ConnectionError("caiu")).instalar(monkeypatch)

    saida = synthesizer.argumento_node(estado_mamao())

    assert saida["argument"][0] == '- Urgência: "URGENTE" pede pressa.'
    assert saida["argument"][1] == '- Generalização: "os médicos estão escondendo"'
    assert saida["warnings"] == [synthesizer.WARN_GUARDRAILS] and len(falso.prompts) == 2


def test_noticia_longa_manda_no_maximo_8_marcadores_ao_modelo(monkeypatch):
    markers = [{"type": "urgencia_artificial", "segment_id": "s01", "excerpt": f"URGENTE {i}", "explanation": "x"}
               for i in range(1, 21)]
    state = estado_mamao(
        segments=[{"id": "s01", "text": " ".join(f"URGENTE {i}" for i in range(1, 21))}], evidence=[],
        text_report={"statements": [{"segment_id": "s01", "kind": "factual"}], "markers": markers})
    modelo = falsos.SintetizadorFalso(json.dumps({"efeitos": []})).instalar(monkeypatch)

    linhas = synthesizer.argumento_node(state)["argument"]

    assert "[8]" in modelo.prompts[0] and "[9]" not in modelo.prompts[0]
    assert len(linhas) == 9 and linhas[-1] == "- Outros 12 trechos repetem esses padrões e não foram listados."


def test_rotulo_falsa_dicotomia_passa_nos_guardrails_sem_retry(monkeypatch):
    # Achado com o 7B real: o rótulo de dossie.ROTULOS reprovava a síntese e o dossiê caía no fallback
    modelo = falsos.SintetizadorFalso(
        resposta((5, "Falsa dicotomia: opõe o natural ao tratamento médico."))).instalar(monkeypatch)

    argumento, resultado = dossie_completo(estado_mamao())

    assert len(modelo.prompts) == 1
    assert "warnings" not in argumento and "warnings" not in resultado
    assert '- Falsa dicotomia: "nada melhor do que a natureza" Falsa dicotomia: opõe o natural ao tratamento médico.' \
        in resultado["dossier"]


def test_rotulos_fixos_e_trecho_literal_da_noticia_passam_sem_retry(monkeypatch):
    # "Autoridade sem identificação" e "Juízo de valor" são rótulos do prompt, não termos da notícia
    modelo = falsos.SintetizadorFalso(
        resposta((4, 'Autoridade sem identificação não diz quem é, como em "plantas medicinais".'))).instalar(monkeypatch)

    argumento, resultado = dossie_completo(estado_mamao())

    assert len(modelo.prompts) == 1
    assert "warnings" not in argumento and "warnings" not in resultado


def test_problema_da_sintese_confere_citacao_e_termo_so_depois_de_vazio_veredito_e_link():
    frases = ["URGENTE: os médicos estão escondendo a cura natural da dengue!"]

    assert synthesizer.problema_da_sintese("", frases) == "Seu texto veio vazio."
    assert "o termo 'falsa'" in synthesizer.problema_da_sintese('- Falsa: "inventado" e a OMS.', frases)
    assert synthesizer.problema_da_sintese('- "inventado" veja https://x.org e a OMS.', frases) == "Seu texto incluiu um link."
    assert synthesizer.problema_da_sintese('- "inventado" e a OMS.', frases) == (
        'Seu texto citou "inventado", que não está em nenhuma frase da notícia.'
    )
    assert synthesizer.problema_da_sintese("- A OMS discorda.", frases) == (
        "Seu texto mencionou 'oms', que não aparece na notícia."
    )
    assert synthesizer.problema_da_sintese('- Urgência: "URGENTE" pede pressa.', frases) is None
