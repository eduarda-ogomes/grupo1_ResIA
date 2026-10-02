"""Testes do script de avaliação do Agente de Evidências (sem índice, sem modelos).

    python -m pytest tests/unit/test_evidence_avaliacao.py
"""

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "avaliar_evidencias.py"
_spec = importlib.util.spec_from_file_location("avaliar_evidencias", _SCRIPT)
av = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(av)

URL_FACHIN = "https://www.aosfatos.org/noticias/foto-fachin/"
URL_FACHIN_AFP = "https://checamos.afp.com/doc.afp.com.FACHIN"
URL_PIX = "https://www.estadao.com.br/estadao-verifica/pix/"
URL_DENGUE = "https://www.aosfatos.org/noticias/cha-cura-dengue/"
URL_VERDADE = "https://www.estadao.com.br/estadao-verifica/f15/"

CORPUS = {
    URL_FACHIN: {"source_url": URL_FACHIN, "source_name": "Aos Fatos", "agency_verdict": "falso",
                 "claim_reviewed": "Foto mostra Edson Fachin apontando o dedo para Alexandre de Moraes",
                 "review_title": "Imagem de Fachin apontando dedo para Moraes foi criada por IA"},
    URL_FACHIN_AFP: {"source_url": URL_FACHIN_AFP, "source_name": "AFP Checamos", "agency_verdict": "Falso",
                     "claim_reviewed": "Fachin aponta o dedo para Moraes", "review_title": "Imagem gerada por IA"},
    URL_PIX: {"source_url": URL_PIX, "source_name": "Estadão", "agency_verdict": "Enganoso",
              "claim_reviewed": "Pix acima de R$ 5.000 será taxado", "review_title": "Receita não vai taxar o Pix"},
    URL_DENGUE: {"source_url": URL_DENGUE, "source_name": "Aos Fatos", "agency_verdict": "falso",
                 "claim_reviewed": "Chá cura a dengue em três dias", "review_title": "Chá não cura dengue"},
    URL_VERDADE: {"source_url": URL_VERDADE, "source_name": "Estadão", "agency_verdict": "Verdadeiro",
                  "claim_reviewed": "Caças F-15 dos EUA pousaram em Natal",
                  "review_title": "Caças F-15 pousaram em Natal em exercício"},
}


def frase(fid, texto, tipo, aceitas=(), stance=None, **extra):
    return {"id": fid, "texto": texto, "tipo": tipo, "checagens_aceitas": list(aceitas),
            "stance_esperada": stance, **extra}


def entrada(eid, frases, split="teste", revisor="R1"):
    return {"id": eid, "split": split, "anotador": "R2", "revisor": revisor,
            "texto": " ".join(f["texto"] for f in frases), "frases": frases}


def gold_sintetico():
    """3 entradas: com checagem, sem checagem e fato parecido (mais um desmente)."""
    return {"versao": 1, "entradas": [
        entrada("ev01", [
            frase("s01", "Ministro do STF encarou colega com o indicador em riste no plenário.", "com_checagem",
                  [URL_FACHIN, URL_FACHIN_AFP], "contradiz"),
            frase("s02", "A Receita vai cobrar imposto de quem receber transferências altas.", "com_checagem",
                  [URL_PIX], "insuficiente"),
        ]),
        entrada("ev02", [
            frase("s01", "Prefeitura anunciou ontem uma nova linha de ônibus noturna.", "sem_checagem"),
            frase("s02", "A agência confirmou que aquela imagem do plenário é montagem.", "desmente",
                  [URL_FACHIN], "apoia"),
        ], split="calibracao"),
        entrada("ev03", [
            frase("s01", "Infusão caseira elimina a chikungunya em poucos dias.", "fato_parecido",
                  alegacao_original="Chá cura a dengue em três dias"),
        ]),
    ]}


def ev(url, stance, segment_id="s01"):
    return {"segment_id": segment_id, "source_url": url, "stance": stance, "excerpt": "x",
            "source_name": "A", "agency_verdict": "Falso"}


# --- recall_at_k ------------------------------------------------------------------

def test_recall_conta_posicao_5_e_nao_conta_6():
    ranking = ["u1", "u2", "u3", "u4", "certa", "u6"]
    assert av.recall_at_k(ranking, ["certa"], k=5)
    assert not av.recall_at_k(["u1", "u2", "u3", "u4", "u5", "certa"], ["certa"], k=5)


def test_recall_aceita_qualquer_url_aceita():
    assert av.recall_at_k(["outra", "espelho"], ["original", "espelho"])
    assert not av.recall_at_k([], ["original"])


# --- macro_f1 -----------------------------------------------------------------------

def test_macro_f1_calculado_a_mao():
    pares = [("contradiz", "contradiz"), ("contradiz", "contradiz"), ("contradiz", "insuficiente"),
             ("insuficiente", "insuficiente"), ("apoia", "contradiz")]
    r = av.macro_f1(pares)
    # contradiz: P = 2/3, R = 2/3, F1 = 2/3; insuficiente: P = 1/2, R = 1, F1 = 2/3; apoia: P = 0, R = 0, F1 = 0
    assert r["por_classe"]["contradiz"]["f1"] == pytest.approx(2 / 3)
    assert r["por_classe"]["insuficiente"]["f1"] == pytest.approx(2 / 3)
    assert r["por_classe"]["apoia"]["f1"] == 0.0
    assert r["valor"] == pytest.approx((2 / 3 + 2 / 3 + 0) / 3)
    assert r["avisos"] == []


def test_macro_f1_classe_sem_exemplo_sai_da_media_com_aviso():
    r = av.macro_f1([("contradiz", "contradiz"), ("insuficiente", "apoia")])
    assert r["classes_na_media"] == ["contradiz", "insuficiente"]
    assert r["por_classe"]["apoia"]["f1"] is None
    assert r["valor"] == pytest.approx((1.0 + 0.0) / 2)
    assert any("apoia" in a for a in r["avisos"])


def test_macro_f1_vazio():
    assert av.macro_f1([])["valor"] is None


# --- prever_stance --------------------------------------------------------------------

def test_prever_stance_ignora_url_nao_aceita_e_sem_evidencia_e_insuficiente():
    assert av.prever_stance([ev("errada", "contradiz")], ["certa"]) == "insuficiente"
    assert av.prever_stance([], ["certa"]) == "insuficiente"
    assert av.prever_stance([ev("errada", "apoia"), ev("certa", "contradiz")], ["certa"]) == "contradiz"


# --- calcular_metricas ------------------------------------------------------------------

def test_calcular_metricas_em_gold_sintetico():
    frases = av.selecionar_frases(gold_sintetico())
    rankings = {
        "ev01/s01": [URL_FACHIN_AFP, "x", "y"],             # AFP no top 5: acerto
        "ev01/s02": ["a", "b", "c", "d", "e", URL_PIX],     # na 6ª posição: erro
        "ev02/s01": ["a"], "ev02/s02": [URL_FACHIN], "ev03/s01": [URL_DENGUE],
    }
    saidas = {
        "ev01/s01": [ev(URL_FACHIN, "contradiz")],                       # coberta, stance certa
        "ev01/s02": [],                                                   # não coberta; prevê insuficiente
        "ev02/s01": [ev("https://inventada", "contradiz")],               # evidência inventada
        "ev02/s02": [],                                                   # desmente: esperado apoia, prevê insuficiente
        "ev03/s01": [ev(URL_DENGUE, "contradiz")],                        # casamento errado
    }
    m = av.calcular_metricas(frases, rankings, saidas)

    assert (m["recall_at_5"]["acertos"], m["recall_at_5"]["total"]) == (1, 2)
    assert (m["cobertura"]["acertos"], m["cobertura"]["total"]) == (1, 2)
    assert (m["evidencia_inventada"]["acertos"], m["evidencia_inventada"]["total"]) == (1, 1)
    assert m["casamento_errado"]["evidencias"] == 2                     # inventada + fato parecido
    assert m["casamento_errado"]["por_tipo"] == {"sem_checagem": 1, "fato_parecido": 1}
    # stance: (contradiz, contradiz), (insuficiente, insuficiente), (apoia, insuficiente)
    assert m["matriz_confusao"]["apoia"]["insuficiente"] == 1
    assert m["macro_f1"]["valor"] == pytest.approx((1.0 + 2 / 3 + 0.0) / 3)
    detalhe = {d["chave"]: d for d in m["por_frase"]}
    assert detalhe["ev01/s01"]["posicao_aceita"] == 1
    assert detalhe["ev01/s02"]["posicao_aceita"] is None
    # stance nas cobertas: só ev01/s01 citou uma URL aceita, e acertou
    assert (m["stance_cobertas"]["acertos"], m["stance_cobertas"]["total"]) == (1, 1)
    assert len(m["erros"]) == 5   # recall e cobertura (ev01/s02); inventada; stance (desmente); casamento errado


def test_stance_nas_cobertas_separa_stance_errada_de_checagem_perdida():
    frases = av.selecionar_frases(gold_sintetico())
    saidas = {
        "ev01/s01": [ev(URL_FACHIN, "apoia")],                   # citou a certa, stance errada
        "ev01/s02": [ev("https://outra", "insuficiente")],       # citou só uma errada: não entra
        "ev02/s02": [ev(URL_FACHIN, "contradiz")],               # desmente: citou a certa, stance errada
    }
    m = av.calcular_metricas(frases, {}, saidas)
    assert (m["stance_cobertas"]["acertos"], m["stance_cobertas"]["total"]) == (0, 2)
    # o macro-F1 conta ev01/s02 como acerto de 'insuficiente', mesmo com a checagem perdida
    assert m["matriz_confusao"]["insuficiente"]["insuficiente"] == 1


def test_relatorio_formata_sem_erro():
    frases = av.selecionar_frases(gold_sintetico())
    m = av.calcular_metricas(frases, {}, {})
    texto = av.formatar_relatorio(m, "todos")
    assert "Recall@5" in texto and "Matriz de confusão" in texto and "Stance nas cobertas" in texto


def test_listar_frases_para_o_diagnostico():
    linhas = av.listar_frases(gold_sintetico(), "calibracao")
    assert linhas == ["# ev02/s01 sem_checagem", "Prefeitura anunciou ontem uma nova linha de ônibus noturna.",
                      "# ev02/s02 desmente", "A agência confirmou que aquela imagem do plenário é montagem."]


def test_comando_frases_grava_utf8(tmp_path):
    gold, saida = tmp_path / "gold.json", tmp_path / "sub" / "frases.txt"
    gold.write_text(json.dumps(gold_sintetico(), ensure_ascii=False), encoding="utf-8")
    assert av.main(["frases", "--gold", str(gold), "--saida", str(saida)]) == 0
    texto = saida.read_text(encoding="utf-8")
    assert texto.count("\n# ") == 4 and "ônibus" in texto


# --- executar_avaliacao com busca e agente simulados -------------------------------------------

def test_executar_avaliacao_uma_chamada_por_entrada_e_filtra_split():
    chamadas = []

    def buscar(textos):
        return [[URL_FACHIN] for _ in textos]

    def agente(segmentos):
        chamadas.append([s["id"] for s in segmentos])
        return {"evidence": [ev(URL_FACHIN, "contradiz", segment_id=segmentos[0]["id"])]}

    m, tempos = av.executar_avaliacao(gold_sintetico(), "teste", buscar, agente)
    assert chamadas == [["s01", "s02"], ["s01"]]          # ev01 e ev03; ev02 é calibração
    assert m["n_frases"] == 3
    assert m["recall_at_5"]["acertos"] == 1
    assert "busca_s" in tempos


def test_executar_avaliacao_falha_se_o_agente_falhar():
    with pytest.raises(RuntimeError):
        av.executar_avaliacao(gold_sintetico(), "todos", lambda t: [[] for _ in t],
                              lambda s: {"evidence": None, "warnings": ["evidencias: índice ausente"]})


def test_executar_avaliacao_sem_frases():
    with pytest.raises(ValueError):
        av.executar_avaliacao({"versao": 1, "entradas": []}, "todos", lambda t: [], lambda s: {})


# --- validar_gold ---------------------------------------------------------------------------

def _erros(problemas):
    return [p for p in problemas if p.nivel == "erro"]


def _avisos(problemas):
    return [p for p in problemas if p.nivel == "aviso"]


def test_gold_sintetico_sem_erros():
    assert _erros(av.validar_gold(gold_sintetico(), CORPUS)) == []


def test_validar_pega_url_fora_do_corpus():
    gold = gold_sintetico()
    gold["entradas"][0]["frases"][0]["checagens_aceitas"].append("https://nao-existe")
    assert any("fora do corpus" in p.msg for p in _erros(av.validar_gold(gold, CORPUS)))


def test_validar_pega_stance_invalida():
    gold = gold_sintetico()
    gold["entradas"][0]["frases"][0]["stance_esperada"] = "falso"
    assert any("stance_esperada" in p.msg for p in _erros(av.validar_gold(gold, CORPUS)))


def test_validar_pega_sem_checagem_com_url_e_com_stance():
    gold = gold_sintetico()
    f = gold["entradas"][1]["frases"][0]
    f["checagens_aceitas"], f["stance_esperada"] = [URL_PIX], "contradiz"
    msgs = [p.msg for p in _erros(av.validar_gold(gold, CORPUS))]
    assert any("vazia" in m for m in msgs) and any("null" in m for m in msgs)


def test_validar_pega_com_checagem_sem_url():
    gold = gold_sintetico()
    gold["entradas"][0]["frases"][0]["checagens_aceitas"] = []
    assert any("pelo menos uma URL" in p.msg for p in _erros(av.validar_gold(gold, CORPUS)))


def test_validar_pega_ids_repetidos():
    gold = gold_sintetico()
    gold["entradas"][1]["id"] = "ev01"
    gold["entradas"][0]["frases"][1]["id"] = "s01"
    msgs = [p.msg for p in _erros(av.validar_gold(gold, CORPUS))]
    assert any("entrada repetido" in m for m in msgs) and any("frase repetido" in m for m in msgs)


def test_validar_pega_tipo_e_split_invalidos():
    gold = gold_sintetico()
    gold["entradas"][0]["split"] = "treino"
    gold["entradas"][2]["frases"][0]["tipo"] = "outro"
    msgs = [p.msg for p in _erros(av.validar_gold(gold, CORPUS))]
    assert any("'split'" in m for m in msgs) and any("'tipo'" in m for m in msgs)


def test_validar_avisa_vazamento_quando_frase_copia_o_titulo():
    gold = gold_sintetico()
    titulo = CORPUS[URL_FACHIN]["review_title"]
    gold["entradas"][0]["frases"][0]["texto"] = titulo
    gold["entradas"][0]["texto"] = titulo
    assert any("vazamento" in p.msg for p in _avisos(av.validar_gold(gold, CORPUS)))


def test_validar_avisa_url_dos_37_pares_e_stance_divergente():
    gold = gold_sintetico()
    gold["entradas"][0]["frases"][1]["stance_esperada"] = "contradiz"   # o veredito é Enganoso
    avisos = [p.msg for p in _avisos(av.validar_gold(gold, CORPUS, pares_urls={URL_FACHIN}))]
    assert any("37 pares" in m for m in avisos)
    assert any("difere do veredito" in m for m in avisos)


def test_validar_avisa_frase_fora_do_texto_e_sem_revisor():
    gold = gold_sintetico()
    gold["entradas"][0]["texto"] = "Outro texto."
    gold["entradas"][0]["revisor"] = None
    avisos = [p.msg for p in _avisos(av.validar_gold(gold, CORPUS))]
    assert any("não aparece igual" in m for m in avisos)
    assert any("sem 'revisor'" in m for m in avisos)


def test_validar_arquivo_sem_entradas():
    assert _erros(av.validar_gold({"versao": 1}, CORPUS))


def test_validar_avisa_composicao_incompleta():
    avisos = [p.msg for p in _avisos(av.validar_gold(gold_sintetico(), CORPUS))]
    assert any("stance apoia" in m for m in avisos)


def test_contar_composicao():
    c = av.contar_composicao(gold_sintetico())
    assert c["com_checagem, stance contradiz"] == 1
    assert c["com_checagem, AFP (só título)"] == 1
    assert c["fato_parecido + troca_numero"] == 1
    assert c["desmente"] == 1 and c["sem_checagem"] == 1


def test_gold_versionado_e_valido():
    """O arquivo do repositório precisa ser JSON válido no formato (mesmo que ainda vazio)."""
    gold = json.loads((_SCRIPT.parents[1] / "data" / "gold" / "evidencias.json").read_text(encoding="utf-8"))
    assert gold.get("versao") == 1 and isinstance(gold.get("entradas"), list)


# --- sortear ----------------------------------------------------------------------------------

def test_sortear_reproduzivel_exclui_e_filtra():
    a = av.sortear(CORPUS, 3, excluir={URL_PIX}, semente=7)
    b = av.sortear(CORPUS, 3, excluir={URL_PIX}, semente=7)
    assert [r["source_url"] for r in a] == [r["source_url"] for r in b]
    assert URL_PIX not in {r["source_url"] for r in a}
    assert len(a) == 3
    verdadeiras = av.sortear(CORPUS, 10, veredito="verdadeiro")
    assert [r["source_url"] for r in verdadeiras] == [URL_VERDADE]
    assert {r["source_name"] for r in av.sortear(CORPUS, 10, agencia="afp")} == {"AFP Checamos"}


def test_sortear_estratifica_por_agencia_e_stance():
    # 4 estratos (agência x stance): AFP/contradiz, Aos Fatos/contradiz, Estadão/insuficiente, Estadão/apoia.
    # Com n = 4, sai um de cada: a stance rara (apoia) não fica de fora.
    amostra = av.sortear(CORPUS, 4, semente=1)
    assert len({r["source_name"] for r in amostra}) == 3
    assert {av.stance_from_verdict(r["agency_verdict"]) for r in amostra} == {"contradiz", "insuficiente", "apoia"}


def test_sortear_veredito_desconhecido():
    with pytest.raises(ValueError):
        av.sortear(CORPUS, 3, veredito="talvez")


def test_marcas_checagem():
    assert "explicativo? (não é alegação)" in av.marcas_checagem(
        {"source_url": "https://x", "claim_reviewed": "Como funciona o golpe do SMS"})
    assert "só título no índice" in av.marcas_checagem({"source_url": URL_FACHIN_AFP})
    assert "espelho (BOL/Acervo)" in av.marcas_checagem({"source_url": "https://www.bol.uol.com.br/noticias/x"})


# --- arquivo de resultado ------------------------------------------------------------------------

def test_caminho_resultado_nao_sobrescreve(tmp_path):
    primeiro = av.caminho_resultado(tmp_path, "2026-10-01")
    assert primeiro.name == "evidencias_2026-10-01.json"
    primeiro.write_text("{}")
    assert av.caminho_resultado(tmp_path, "2026-10-01").name == "evidencias_2026-10-01_2.json"


# --- esqueleto e completar ------------------------------------------------------------------

def corpus_grande():
    """Corpus sintético com checagens suficientes para todas as vagas do esqueleto."""
    corpus = {}

    def add(url, nome, veredito, claim, titulo=None):
        corpus[url] = {"source_url": url, "source_name": nome, "agency_verdict": veredito,
                       "claim_reviewed": claim, "review_title": titulo or f"Checagem: {claim}"}

    for i in range(20):
        add(f"https://www.aosfatos.org/noticias/f{i}/", "Aos Fatos", "falso",
            f"Ministro Fulano{i} anunciou corte de {i + 10} mil vagas na saúde pública")
    for i in range(5):
        add(f"https://checamos.afp.com/doc.afp.com.F{i}", "AFP Checamos", "Falso",
            f"Vídeo mostra Beltrano{i} discursando contra a vacina da dengue")
    for i in range(6):
        add(f"https://www.estadao.com.br/estadao-verifica/e{i}/", "Estadão", "Enganoso",
            f"Prefeitura de Cidade{i} vai cobrar taxa nova sobre aplicativos")
    for i in range(3):
        add(f"https://www.estadao.com.br/estadao-verifica/v{i}/", "Estadão", "Verdadeiro",
            f"Caças estrangeiros pousaram na base aérea número {i + 1} em exercício")
    # Não utilizáveis: guia, alegação negativa, alegação curta, espelho.
    add("https://x/guia", "UOL Notícias", "Comprovado", "Como funciona o golpe do pix errado no celular")
    add("https://x/negativa", "Projeto Comprova", "Comprovado", "Não é Moraes no avião do empresário investigado")
    add("https://x/curta", "BOL", "Falso", "Nosso representante..")
    add("https://x/link", "Estadão", "Falso", "https://www.instagram.com/reel/ABCDEF123456/")
    add("https://x/pergunta", "UOL Notícias", "Falso", "O que você faria se pudesse receber uma estatueta grátis?")
    add("https://x/longa", "UOL Notícias", "Falso", "Texto enorme de corrente de WhatsApp " * 8)
    add("https://www.bol.uol.com.br/noticias/espelho", "BOL - UOL", "Verdadeiro",
        "Foto do senador com o presidente americano na Casa Branca", titulo="Foto é real")
    add("https://noticias.uol.com.br/confere/original", "UOL Notícias", "Verdadeiro",
        "Foto do senador com o presidente americano na Casa Branca", titulo="Foto é real")
    return corpus


def test_checagem_utilizavel_descarta_guia_negativa_curta_e_espelho():
    c = corpus_grande()
    assert not av.checagem_utilizavel(c["https://x/guia"])
    assert not av.checagem_utilizavel(c["https://x/negativa"])
    assert not av.checagem_utilizavel(c["https://x/curta"])
    assert not av.checagem_utilizavel(c["https://x/pergunta"])
    assert not av.checagem_utilizavel(c["https://x/link"])
    assert not av.checagem_utilizavel(c["https://x/longa"])
    assert not av.checagem_utilizavel(c["https://www.bol.uol.com.br/noticias/espelho"])
    assert av.checagem_utilizavel(c["https://checamos.afp.com/doc.afp.com.F0"])   # só título não impede


def test_urls_mesma_checagem_inclui_espelho_com_original_primeiro():
    c = corpus_grande()
    urls = av.urls_mesma_checagem(c, "https://noticias.uol.com.br/confere/original")
    assert urls == ["https://noticias.uol.com.br/confere/original", "https://www.bol.uol.com.br/noticias/espelho"]


def test_esqueleto_segue_a_tabela_e_equilibra_os_splits():
    gold, avisos = av.gerar_esqueleto(corpus_grande(), semente=3)
    assert avisos == []
    assert len(gold["entradas"]) == 12
    assert all(len(e["frases"]) == 3 for e in gold["entradas"])
    assert [e["split"] for e in gold["entradas"]][:4] == ["teste", "calibracao", "teste", "calibracao"]
    composicao = av.contar_composicao(gold)
    assert composicao == {
        "com_checagem, stance contradiz": 13, "com_checagem, stance insuficiente": 4,
        "com_checagem, stance apoia": 2, "com_checagem, AFP (só título)": 2, "sem_checagem": 11,
        "fato_parecido + troca_numero": 4, "desmente": 2,
    }
    frases = av.selecionar_frases(gold)
    for split in ("teste", "calibracao"):
        assert sum(f["split"] == split for f in frases) == 18
    # Toda entrada tem pelo menos uma frase ligada a uma checagem.
    assert all(any(f["tipo"] != "sem_checagem" for f in e["frases"]) for e in gold["entradas"])
    # Cada checagem é usada uma vez só, e só checagens utilizáveis entram.
    urls = [u for f in frases for u in f["aceitas"]] + [f.get("_base") for e in gold["entradas"]
                                                         for f in e["frases"] if f.get("_base")]
    assert len(urls) == len(set(urls))
    assert not {"https://x/guia", "https://x/negativa", "https://x/curta", "https://x/pergunta",
                "https://x/longa"} & set(urls)
    # Vagas de troca de número vêm de alegações com número.
    trocas = [f for e in gold["entradas"] for f in e["frases"] if f["tipo"] == "troca_numero"]
    assert all(any(ch.isdigit() for ch in f["alegacao_original"]) for f in trocas)


def test_esqueleto_reproduzivel_e_exclui_urls():
    a, _ = av.gerar_esqueleto(corpus_grande(), semente=5)
    b, _ = av.gerar_esqueleto(corpus_grande(), semente=5)
    a["_gerado"] = b["_gerado"] = None
    assert a == b
    excluir = {f"https://www.estadao.com.br/estadao-verifica/v{i}/" for i in range(3)}
    gold, avisos = av.gerar_esqueleto(corpus_grande(), excluir=excluir, semente=5)
    apoia = [f for f in av.selecionar_frases(gold) if f["tipo"] == "com_checagem" and f["stance_esperada"] == "apoia"]
    # Sobra só a checagem do UOL (com o espelho do BOL nas aceitas) para 2 vagas.
    assert [f["aceitas"] for f in apoia if f["aceitas"]] == [["https://noticias.uol.com.br/confere/original",
                                                               "https://www.bol.uol.com.br/noticias/espelho"]]
    assert any("só 1 de 2" in a for a in avisos)


def test_esqueleto_valida_so_com_erros_de_frase_vazia():
    corpus = corpus_grande()
    gold, _ = av.gerar_esqueleto(corpus, semente=2)
    erros = _erros(av.validar_gold(gold, corpus))
    assert erros and all("ainda sem 'texto'" in p.msg for p in erros)
    assert len(erros) == 36


def test_completar_monta_texto_e_tira_instrucao():
    corpus = corpus_grande()
    gold, _ = av.gerar_esqueleto(corpus, semente=2)
    primeira = gold["entradas"][0]
    for k, f in enumerate(primeira["frases"]):
        f["texto"] = f"Frase escrita número {k}."
    primeira["frases"][2]["texto"] = "Frase sem ponto"
    montadas, avisos = av.completar(gold)
    assert montadas == 1
    assert primeira["texto"] == "Frase escrita número 0. Frase escrita número 1. Frase sem ponto"
    assert all("_instrucao" not in f for f in primeira["frases"])
    assert "_instrucao" in gold["entradas"][1]["frases"][0]
    assert any("não termina com pontuação" in a for a in avisos)
    assert any(a.startswith("ev02: frases ainda sem texto") for a in avisos)
    # Não remonta um texto já escrito, a menos que peça.
    primeira["texto"] = "Texto editado à mão."
    assert av.completar(gold)[0] == 0 and primeira["texto"] == "Texto editado à mão."
    assert av.completar(gold, refazer=True)[0] == 1
    erros_ev01 = [p for p in _erros(av.validar_gold(gold, corpus)) if p.onde.startswith("ev01")]
    assert erros_ev01 == []


def test_comando_esqueleto_nao_sobrescreve(tmp_path):
    claims = tmp_path / "claims.jsonl"
    claims.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in corpus_grande().values()), encoding="utf-8")
    saida = tmp_path / "gold.json"
    assert av.main(["esqueleto", "--claims", str(claims), "--saida", str(saida)]) == 0
    assert len(json.loads(saida.read_text(encoding="utf-8"))["entradas"]) == 12
    assert av.main(["esqueleto", "--claims", str(claims), "--saida", str(saida)]) == 1
    assert av.main(["esqueleto", "--claims", str(claims), "--saida", str(saida), "--forcar"]) == 0
    assert av.main(["completar", "--gold", str(saida)]) == 0
