"""Testes unitários do Agente Socrático (R4)."""
import json
import pytest

from src.agents import socratic as agent
from src.state import PipelineState, Segment, Statement, TextReport, initial_state


def test_carregar_prompt_sistema():
    prompt = agent.carregar_prompt_sistema()
    assert "Você é um filósofo socrático" in prompt
    assert "Não diga se a notícia é verdadeira ou falsa" in prompt
    assert "<noticia>" in prompt


def test_carregar_exemplos():
    exemplos = agent.carregar_exemplos()
    assert isinstance(exemplos, list)
    assert len(exemplos) >= 1
    assert "entrada" in exemplos[0]
    assert "saida" in exemplos[0]
    assert "socratic_questions" in exemplos[0]["saida"]


def test_montar_mensagens_delimita_texto_como_dado():
    mensagens = agent.montar_mensagens("Texto suspeito sobre saúde.")
    # Primeira mensagem deve ser o system prompt
    assert mensagens[0][0] == "system"
    # Última mensagem deve ser do usuário contendo a notícia delimitada
    role_final, conteudo_final = mensagens[-1]
    assert role_final == "user"
    assert "<noticia>\nTexto suspeito sobre saúde.\n</noticia>" in conteudo_final


MAMAO = "O chá da folha de mamão cura a dengue em apenas três dias. Um especialista garante que salva vidas."


def test_validar_perguntas_com_sucesso():
    perguntas = [
        "Quais evidências científicas comprovam que essa substância cura a doença?",
        "Quem são os especialistas citados e onde essas pesquisas foram publicadas?",
    ]
    validadas = agent.validar_perguntas(perguntas, MAMAO)
    assert len(validadas) == 2
    assert validadas == perguntas


def test_validar_perguntas_trunca_excesso():
    perguntas = [
        "Pergunta 1 com tamanho adequado?",
        "Pergunta 2 com tamanho adequado?",
        "Pergunta 3 com tamanho adequado?",
        "Pergunta 4 com tamanho adequado excedente?",
    ]
    validadas = agent.validar_perguntas(perguntas, "Pergunta 1, 2, 3 e 4 do questionário.")
    assert len(validadas) == 3


def test_validar_perguntas_rejeita_menos_de_duas():
    with pytest.raises(agent.PerguntaInvalida, match="mínimo 2 perguntas"):
        agent.validar_perguntas(["Apenas uma pergunta?"], MAMAO)


def test_validar_perguntas_rejeita_pergunta_indutiva():
    # Exemplo extraído do caso de borda tests/fixtures/bordas/socratico_pergunta_indutiva.json
    pergunta_indutiva = "Você não acha suspeito que os médicos escondam uma cura tão simples?"
    with pytest.raises(agent.PerguntaInvalida, match="Pergunta indutiva detectada"):
        agent.validar_perguntas([
            pergunta_indutiva,
            "Quais estudos comprovam esse método?",
        ], MAMAO)


def test_validar_perguntas_rejeita_veredito():
    pergunta_com_veredito = "Por que isso é falso segundo os especialistas?"
    with pytest.raises(agent.PerguntaInvalida, match="veredito proibido"):
        agent.validar_perguntas([
            pergunta_com_veredito,
            "Quais estudos comprovam esse método?",
        ], MAMAO)


def test_pergunta_com_entidade_de_fora_e_descartada(caplog):
    perguntas = [
        "Quem é o especialista citado e onde ele publicou seus estudos?",
        "O que diz a OMS sobre o chá de mamão?",
        "Quais estudos sustentam a cura da dengue em três dias?",
    ]
    with caplog.at_level("WARNING", logger=agent.logger.name):
        assert agent.validar_perguntas(perguntas, MAMAO) == [perguntas[0], perguntas[2]]
    assert "oms" in caplog.text.lower()
    assert perguntas[1] in caplog.text


def test_sobra_menos_de_duas_perguntas_dispara_retry():
    with pytest.raises(agent.PerguntaInvalida, match="'oms'"):
        agent.validar_perguntas([
            "O que diz a OMS sobre isso?",
            "E o Ministério da Saúde, o que diz?",
            "Quem é o especialista citado na notícia?",
        ], MAMAO)


def test_mensagem_de_erro_cita_o_termo_e_a_pergunta_descartada():
    pergunta = "O que diz a OMS sobre isso?"
    with pytest.raises(agent.PerguntaInvalida) as erro:
        agent.validar_perguntas([pergunta, "Quem é o especialista citado na notícia?"], MAMAO)
    assert str(erro.value) == f"Pergunta menciona 'oms', que não aparece na notícia: '{pergunta}'"


def test_descarta_antes_de_cortar_em_tres():
    # 4 perguntas, a primeira com termo de fora: sobram 3, todas mantidas (descartar vem antes de cortar)
    perguntas = [
        "O que diz a OMS sobre isso?",
        "Quem é o especialista citado na notícia?",
        "Quais estudos sustentam a cura da dengue em três dias?",
        "Que evidências mostram que a folha de mamão salva vidas?",
    ]
    assert agent.validar_perguntas(perguntas, MAMAO) == perguntas[1:]


def test_pergunta_com_numero_de_fora_e_descartada():
    perguntas = [
        "Por que a cura levaria 30 dias e não três?",
        "Quem é o especialista citado na notícia?",
        "Quais estudos sustentam a cura da dengue em três dias?",
    ]
    assert agent.validar_perguntas(perguntas, MAMAO) == perguntas[1:]


def test_pergunta_com_doenca_de_fora_e_descartada():
    perguntas = [
        "O chá também funcionaria contra a malária?",
        "Quem é o especialista citado na notícia?",
        "Quais estudos sustentam a cura da dengue em três dias?",
    ]
    assert agent.validar_perguntas(perguntas, MAMAO) == perguntas[1:]


def test_extrair_e_validar_aplica_o_g4():
    bruto = json.dumps({"socratic_questions": [
        "O que diz a OMS sobre isso?",
        "Quem é o especialista citado na notícia?",
    ]})
    with pytest.raises(agent.PerguntaInvalida, match="'oms'"):
        agent.extrair_e_validar(bruto, MAMAO)

    bruto_ok = json.dumps({"perguntas": [
        "Quem é o especialista citado na notícia?",
        "Quais estudos sustentam a cura da dengue em três dias?",
    ]})
    assert len(agent.extrair_e_validar(bruto_ok, MAMAO)) == 2


def test_analisar_texto_faz_retry_quando_g4_deixa_menos_de_duas(monkeypatch):
    respostas = [
        {"socratic_questions": ["O que diz a OMS sobre isso?", "Quem é o especialista citado na notícia?"]},
        {"socratic_questions": ["Quem é o especialista citado na notícia?",
                                "Quais estudos sustentam a cura da dengue em três dias?"]},
    ]
    mensagens_vistas = []

    def mock_chamar(msgs):
        mensagens_vistas.append(msgs)
        return json.dumps(respostas[len(mensagens_vistas) - 1])

    monkeypatch.setattr(agent, "chamar_modelo", mock_chamar)

    perguntas = agent.analisar_texto(MAMAO, MAMAO)
    assert len(perguntas) == 2
    assert len(mensagens_vistas) == 2
    assert "'oms'" in mensagens_vistas[1][-1][1]  # o retry informa ao modelo o motivo da rejeição


def test_socratic_node_degrada_quando_g4_reprova_nas_duas_tentativas(monkeypatch):
    saida = json.dumps({"socratic_questions": [
        "O que diz a OMS sobre isso?", "E o que diz a Fiocruz sobre isso?",
    ]})
    monkeypatch.setattr(agent, "chamar_modelo", lambda msgs: saida)

    state = PipelineState(**initial_state("t", clean_text=MAMAO))
    resultado = agent.socratic_node(state)

    assert resultado["socratic_questions"] is None
    assert agent.WARN_SAIDA_INVALIDA in resultado["warnings"]


def test_exemplos_few_shot_passam_no_g4_com_a_propria_entrada():
    for ex in agent.carregar_exemplos():
        perguntas = ex["saida"]["socratic_questions"]
        assert agent.validar_perguntas(perguntas, ex["entrada"]) == perguntas


def test_socratic_node_texto_vazio():
    state = PipelineState(**initial_state(""))
    res = agent.socratic_node(state)
    assert res == {"socratic_questions": []}


def test_analisar_texto_sucesso(monkeypatch):
    saida_mock = json.dumps({
        "socratic_questions": [
            "Quais dados sustentam que a medida reduz a criminalidade?",
            "Foram avaliados outros fatores sociais antes dessa conclusão?",
        ]
    })
    monkeypatch.setattr(agent, "chamar_modelo", lambda msgs: saida_mock)

    perguntas = agent.analisar_texto("Texto de notícia sobre criminalidade", "Texto de notícia sobre criminalidade")
    assert len(perguntas) == 2


def test_analisar_texto_retry_com_recuperacao(monkeypatch):
    tentativas = 0

    def mock_chamar(msgs):
        nonlocal tentativas
        tentativas += 1
        if tentativas == 1:
            # Primeira tentativa: pergunta indutiva (deve disparar retry)
            return json.dumps({
                "socratic_questions": [
                    "Você não acha que o prefeito está errado?",
                    "Quais são os dados?",
                ]
            })
        # Segunda tentativa: recuperada
        return json.dumps({
            "socratic_questions": [
                "Quais dados sustentam a afirmação do prefeito?",
                "Quais outras medidas foram implementadas no período?",
            ]
        })

    monkeypatch.setattr(agent, "chamar_modelo", mock_chamar)

    perguntas = agent.analisar_texto("Texto sobre o prefeito", "Texto sobre o prefeito")
    assert len(perguntas) == 2
    assert tentativas == 2


def test_socratic_node_saida_invalida_apos_retry(monkeypatch):
    # Retorna JSON inválido nas duas tentativas
    monkeypatch.setattr(agent, "chamar_modelo", lambda msgs: "Isto não é um JSON")

    state = PipelineState(**initial_state("Texto de teste", clean_text="Texto válido"))
    resultado = agent.socratic_node(state)

    assert resultado["socratic_questions"] is None
    assert agent.WARN_SAIDA_INVALIDA in resultado["warnings"]


def test_socratic_node_modelo_indisponivel(monkeypatch):
    def mock_falha(msgs):
        raise ConnectionError("Connection refused: 1234")

    monkeypatch.setattr(agent, "chamar_modelo", mock_falha)

    state = PipelineState(**initial_state("Texto de teste", clean_text="Texto válido"))
    resultado = agent.socratic_node(state)

    assert resultado["socratic_questions"] is None
    assert agent.WARN_MODELO_INDISPONIVEL in resultado["warnings"]


# --- Resumo da notícia para o Socrático -------------------------------------------------------------


def _estado_resumo(frases, factuais=(), title="Chá cura dengue", com_report=True):
    segmentos = [Segment(id=f"s{i:02d}", text=t) for i, t in enumerate(frases, start=1)]
    report = None
    if com_report:
        report = TextReport(
            statements=[
                Statement(segment_id=s.id, kind="factual" if s.id in factuais else "valor") for s in segmentos
            ],
            markers=[],
        )
    return PipelineState(**initial_state(
        "t", clean_text=" ".join(frases), title=title, segments=segmentos, text_report=report,
    ))


def test_resumo_titulo_inicio_e_factuais():
    frases = [f"Frase s{i:02d} da notícia." for i in range(1, 9)]
    estado = _estado_resumo(frases, factuais={"s07"})
    assert agent.resumo_para_socratico(estado) == (
        "Chá cura dengue\nFrase s01 da notícia. Frase s02 da notícia. Frase s03 da notícia. Frase s07 da notícia."
    )


def test_resumo_sem_repetir_frase_inicial_factual():
    frases = [f"Frase s{i:02d} da notícia." for i in range(1, 6)]
    resumo = agent.resumo_para_socratico(_estado_resumo(frases, factuais={"s02", "s05"}))
    assert resumo.count("Frase s02") == 1
    assert resumo.endswith("Frase s03 da notícia. Frase s05 da notícia.")


def test_resumo_sem_titulo_de_texto_colado():
    frases = ["Primeira frase da notícia.", "Segunda frase."]
    resumo = agent.resumo_para_socratico(_estado_resumo(frases, title="Texto Inserido Manualmente"))
    assert not resumo.startswith("Texto Inserido")
    assert resumo == "Primeira frase da notícia. Segunda frase."
    assert agent.TITULO_TEXTO_COLADO == "Texto Inserido Manualmente"


def test_resumo_sem_titulo_none():
    resumo = agent.resumo_para_socratico(_estado_resumo(["Uma frase."], title=None))
    assert resumo == "Uma frase."


def test_resumo_sem_text_report_usa_frases_em_ordem_ate_o_limite():
    frases = [" ".join(f"p{i}w{j}" for j in range(10)) + "." for i in range(60)]
    estado = _estado_resumo(frases, title=None, com_report=False)
    resumo = agent.resumo_para_socratico(estado)
    assert len(resumo.split()) == 400
    assert resumo == " ".join(frases[:40])  # cortado em fim de frase


def test_resumo_respeita_limite_contando_o_titulo():
    frases = [" ".join(["palavra"] * 10) + "." for _ in range(60)]
    resumo = agent.resumo_para_socratico(_estado_resumo(frases, title="Um dois três", com_report=False))
    assert len(resumo.split()) <= agent.LIMITE_PALAVRAS_SOCRATICO
    assert resumo.startswith("Um dois três\n")
    assert len(resumo.split()) == 3 + 390


def test_resumo_primeira_frase_maior_que_o_limite_e_truncada():
    frase = " ".join(["x"] * 500) + "."
    resumo = agent.resumo_para_socratico(_estado_resumo([frase], title=None))
    assert len(resumo.split()) == 400


def test_resumo_sem_segmentos_usa_o_texto_limpo():
    estado = PipelineState(**initial_state("t", clean_text="Texto sem segmentos."))
    assert agent.resumo_para_socratico(estado) == "Texto sem segmentos."


def test_socratic_node_envia_o_resumo_ao_modelo(monkeypatch):
    frases = [f"Frase s{i:02d} da notícia." for i in range(1, 9)]
    estado = _estado_resumo(frases, factuais={"s07"})
    vistas = []

    def mock_chamar(msgs):
        vistas.append(msgs)
        return json.dumps({"socratic_questions": [
            "Quais evidências sustentam a frase s01?", "Que fatores a notícia deixa de considerar?",
        ]})

    monkeypatch.setattr(agent, "chamar_modelo", mock_chamar)
    agent.socratic_node(estado)
    usuario = vistas[0][-1][1]
    assert "Frase s07 da notícia." in usuario
    assert "Frase s05 da notícia." not in usuario


def test_g4_valida_contra_a_noticia_inteira(monkeypatch):
    # "Fiocruz" aparece só no fim da notícia (fora do resumo): a pergunta é aceita
    frases = [f"Frase número {i} sem nomes próprios." for i in range(1, 6)] + [
        "A Fiocruz não confirmou o resultado."
    ]
    estado = _estado_resumo(frases, title=None)
    estado = estado.model_copy(update={"text_report": TextReport(statements=[], markers=[])})
    assert "Fiocruz" not in agent.resumo_para_socratico(estado)

    saida = json.dumps({"socratic_questions": [
        "O que a Fiocruz disse sobre o resultado?", "Que evidências sustentam esse resultado?",
    ]})
    monkeypatch.setattr(agent, "chamar_modelo", lambda msgs: saida)
    resultado = agent.socratic_node(estado)
    assert resultado["socratic_questions"] is not None
    assert len(resultado["socratic_questions"]) == 2


def test_g4_aceita_entidade_que_so_aparece_no_titulo(monkeypatch):
    saida = json.dumps({"socratic_questions": [
        "O que a Fiocruz diz sobre o chá da folha de mamão?",
        "Quais estudos sustentam a cura da dengue em três dias?",
    ]})
    monkeypatch.setattr(agent, "chamar_modelo", lambda msgs: saida)

    state = PipelineState(**initial_state("t", clean_text=MAMAO, title="Fiocruz contesta chá de mamão"))
    resultado = agent.socratic_node(state)

    assert resultado["socratic_questions"][0].startswith("O que a Fiocruz")
