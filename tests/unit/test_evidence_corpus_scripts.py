"""Testes dos scripts do corpus (sem rede, sem modelos).

    python -m pytest tests/unit/test_evidence_corpus_scripts.py
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data" / "corpus"))

import build_index  # noqa: E402
import experimento_etapa2  # noqa: E402
import fetch_articles  # noqa: E402
import import_factckbr  # noqa: E402
import import_lupa  # noqa: E402


# --- build_index: divisão em trechos ----------------------------------------------

def test_split_paragraphs_descarta_curtos_e_normaliza_espacos():
    text = "Título\n\nPrimeiro   parágrafo com texto suficiente para entrar no índice.\n\nOk.\n"
    assert build_index.split_paragraphs(text, min_chars=20) == ["Primeiro parágrafo com texto suficiente para entrar no índice."]


def test_respeita_tamanho_maximo_com_sobreposicao():
    paragraphs = [f"Parágrafo número {i} com algum conteúdo de conclusão da checagem." for i in range(6)]
    chunks = build_index.build_chunks("\n".join(paragraphs), max_chars=150, overlap=1, min_chars=10)
    assert len(chunks) > 1
    assert all(len(c) <= 150 for c in chunks)
    for previous, current in zip(chunks, chunks[1:]):   # o último parágrafo de um trecho abre o seguinte
        assert current.split("\n")[0] == previous.split("\n")[-1]
    joined = "\n".join(chunks)
    assert all(p in joined for p in paragraphs)          # nenhum parágrafo se perde


def test_texto_curto_vira_um_trecho_e_texto_vazio_nenhum():
    assert build_index.build_chunks("Um parágrafo com texto suficiente para o índice.", min_chars=10) == [
        "Um parágrafo com texto suficiente para o índice."]
    assert build_index.build_chunks("") == []


# --- build_index: trecho de título ---------------------------------------------

def test_toda_checagem_ganha_trecho_de_titulo_mesmo_sem_texto():
    claims = [
        {"source_url": "https://checamos.afp.com/x", "source_name": "AFP Checamos", "agency_verdict": "Falso",
         "review_title": "É falso que presidente do Paraguai agradeceu a Lula", "claim_reviewed": "Presidente agradece Lula"},
        {"source_url": "https://www.aosfatos.org/y", "source_name": "Aos Fatos", "agency_verdict": "falso",
         "review_title": "Foto de briga entre Fachin e Moraes não é real", "claim_reviewed": "Foto mostra Fachin"},
    ]
    articles = [{"source_url": "https://www.aosfatos.org/y",
                 "text": "Foi gerada por IA a foto que mostra uma discussão entre dois ministros do STF.\n"
                         "A imagem circula nas redes sociais como se fosse um registro verdadeiro."}]
    records = build_index.build_records(claims, articles)
    kinds = [(r["metadata"]["source_url"].split("/")[-1], r["metadata"]["chunk_kind"], r["metadata"]["chunk_index"])
             for r in records]
    assert kinds == [("x", "titulo", -1), ("y", "titulo", -1), ("y", "texto", 0)]
    assert records[0]["text"] == claims[0]["review_title"]
    assert records[0]["id"].endswith("-tit") and records[2]["id"].endswith("-000")
    assert all(r["metadata"]["review_title"] for r in records)
    assert len({r["id"] for r in records}) == len(records)
    for r in records:  # o Chroma só aceita str/int/float/bool nos metadados
        assert all(isinstance(v, (str, int, float, bool)) for v in r["metadata"].values())


def test_checagem_sem_titulo_nem_texto_nao_gera_trecho():
    assert build_index.build_records([{"source_url": "https://x.org/1", "review_title": ""}], []) == []


# --- fetch_articles: desiste de um site depois de falhas seguidas -------------

def test_download_desiste_do_site_que_recusa(tmp_path, monkeypatch):
    claims = [{"source_url": f"https://checamos.afp.com/doc{i}"} for i in range(30)]
    claims += [{"source_url": f"https://www.estadao.com.br/a{i}"} for i in range(3)]
    (tmp_path / "c.jsonl").write_text("\n".join(json.dumps(c) for c in claims), encoding="utf-8")
    calls = []

    def fake_fetch(url, retries):
        calls.append(url)
        if "afp" in url:
            raise RuntimeError("download falhou")
        return "texto", "título"

    monkeypatch.setattr(fetch_articles, "fetch_text", fake_fetch)
    monkeypatch.setattr(fetch_articles.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["x", "--claims", str(tmp_path / "c.jsonl"), "--out", str(tmp_path / "a.jsonl"),
                                      "--failures", str(tmp_path / "f.jsonl"), "--max-falhas-seguidas", "5"])
    fetch_articles.main()
    assert sum("afp" in u for u in calls) == 5          # desistiu depois de 5 falhas seguidas
    assert len((tmp_path / "a.jsonl").read_text(encoding="utf-8").splitlines()) == 3


def test_download_apenas_dos_sites_pedidos(tmp_path, monkeypatch):
    claims = [{"source_url": f"https://checamos.afp.com/doc{i}"} for i in range(3)]
    claims += [{"source_url": f"https://noticias.uol.com.br/confere/a{i}.htm"} for i in range(8)]
    (tmp_path / "c.jsonl").write_text("\n".join(json.dumps(c) for c in claims), encoding="utf-8")
    calls = []
    monkeypatch.setattr(fetch_articles, "fetch_text", lambda url, retries: calls.append(url) or ("texto", "t"))
    monkeypatch.setattr(fetch_articles.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["x", "--claims", str(tmp_path / "c.jsonl"), "--out", str(tmp_path / "a.jsonl"),
                                      "--failures", str(tmp_path / "f.jsonl"),
                                      "--apenas-sites", "www.noticias.uol.com.br", "--limit", "5"])
    fetch_articles.main()
    assert len(calls) == 5 and all("uol" in u for u in calls)


# --- experimento_etapa2: lógica das variantes ---------------------------------

@pytest.fixture
def scored_pairs():
    pairs = [
        {"id": "p1", "tipo": "parafrase_midia", "mesma_alegacao": True, "source_url": "u1",
         "alegacao": "Foto mostra Fachin apontando o dedo para Moraes", "frase": "Fachin apontou o dedo para Moraes no STF."},
        {"id": "p2", "tipo": "troca_nome", "mesma_alegacao": False, "source_url": "u2",
         "alegacao": "Chá de mamão cura a dengue", "frase": "O chá de mamão cura a chikungunya."},
    ]

    def fake_classify(inputs):
        out = []
        for premise, hypothesis in inputs:
            # "Foto mostra" derruba o entailment; troca de doença não (como no modelo real).
            e = 0.01 if premise.startswith("Foto mostra") or hypothesis.startswith("Foto mostra") else 0.97
            out.append({"entailment": e, "neutral": 1 - e, "contradiction": 0.0})
        return out

    pairs = experimento_etapa2.score_pairs(pairs, fake_classify)
    claims = {"u1": {"review_title": "Foto de briga entre Fachin e Moraes no STF não é real"},
              "u2": {"review_title": "É falso que chá de mamão cura dengue"}}
    return experimento_etapa2.add_key_terms(pairs, claims, {})


def test_experimento_compara_variantes(scored_pairs):
    p1, p2 = scored_pairs
    assert p1["alegacao_normalizada"] == "Fachin apontando o dedo para Moraes"
    assert (p1["ent_original"], p1["ent_normalizada"]) == (0.01, 0.97)
    assert p2["termos_ok"] is False and p2["termos_ausentes"] == "chikungunya"
    decisions = {v: (experimento_etapa2.decide(p1, v, 0.5), experimento_etapa2.decide(p2, v, 0.5))
                 for v in experimento_etapa2.VARIANTS}
    assert decisions == {
        "A": (False, True),   # perde a paráfrase e casa a troca de nome
        "B": (True, True),    # normalização recupera a paráfrase
        "C": (False, False),  # termos-chave barram a troca
        "D": (True, False),   # as duas correções juntas
        "E": (True, False),
    }
    summary = experimento_etapa2.summarize(scored_pairs, "A", 0.5)
    assert summary["casou_errado"] == ["p2"] and summary["paráfrases_perdidas"] == ["p1"]


def test_pares_do_experimento_sao_validos():
    data = json.loads(experimento_etapa2.PAIRS_FILE.read_text(encoding="utf-8"))
    pairs = data["pares"]
    assert len(pairs) >= 30 and len({p["id"] for p in pairs}) == len(pairs)
    assert {p["tipo"] for p in pairs} <= set(experimento_etapa2.TYPES)
    assert all(p["source_url"].startswith("https://") and p["alegacao"] and p["frase"] for p in pairs)
    assert all(p["mesma_alegacao"] == p["tipo"].startswith("parafrase") for p in pairs)


# --- build_index: só os trechos novos ------------------------------------------

def test_apenas_novos_pula_ids_que_ja_estao_no_indice():
    records = [{"id": "a-tit"}, {"id": "a-000"}, {"id": "b-tit"}]
    assert build_index.only_new(records, {"a-tit", "a-000"}) == [{"id": "b-tit"}]


# --- republicações (BOL) fora do índice -----------------------------------------

@pytest.mark.parametrize("url, excluida", [
    ("https://www.bol.uol.com.br/noticias/2022/09/16/imagem-de-flavio.htm", True),
    ("https://bol.uol.com.br/noticias/2026/09/25/falso-imagem.amp.htm", True),
    ("https://noticias.uol.com.br/confere/ultimas-noticias/2022/09/16/imagem-de-flavio.htm", False),
    ("https://www.aosfatos.org/noticias/bol-uol-com-br/", False),
])
def test_url_excluida_so_pelo_dominio(url, excluida):
    from src.retrieval import config
    assert config.url_excluida(url) is excluida


def test_republicacoes_nao_geram_trecho_e_sao_listadas_para_apagar():
    claims = [{"source_url": "https://noticias.uol.com.br/a.htm", "review_title": "Original"},
              {"source_url": "https://www.bol.uol.com.br/a.htm", "review_title": "Cópia"}]
    articles = [{"source_url": "https://www.bol.uol.com.br/b.htm", "text": "x" * 100}]
    claims_ok, articles_ok, excluidas = build_index.separar_excluidas(claims, articles)
    assert [c["source_url"] for c in claims_ok] == ["https://noticias.uol.com.br/a.htm"]
    assert articles_ok == []
    assert excluidas == ["https://www.bol.uol.com.br/a.htm", "https://www.bol.uol.com.br/b.htm"]


# --- variantes de URL da mesma página (UOL: .htm, .ghtm, .amp.htm) ------------------

@pytest.mark.parametrize("url, canonica", [
    ("https://noticias.uol.com.br/confere/2024/12/20/nikolas.htm", "https://noticias.uol.com.br/confere/2024/12/20/nikolas"),
    ("https://noticias.uol.com.br/confere/2024/12/20/nikolas.ghtm", "https://noticias.uol.com.br/confere/2024/12/20/nikolas"),
    ("https://noticias.uol.com.br/confere/2024/12/20/nikolas.amp.htm", "https://noticias.uol.com.br/confere/2024/12/20/nikolas"),
    ("https://noticias.uol.com.br/a/b.htm?cmpid=x", "https://noticias.uol.com.br/a/b"),
    ("https://www.estadao.com.br/estadao-verifica/x/", "https://www.estadao.com.br/estadao-verifica/x"),
    ("https://saude.uol.com.br/noticias/doenca.html", "https://saude.uol.com.br/noticias/doenca.html"),  # .html fica
])
def test_url_canonica_junta_as_variantes(url, canonica):
    assert build_index.url_canonica(url) == canonica


def test_unifica_variantes_mantem_htm_e_completa_campos_vazios():
    base = "https://noticias.uol.com.br/confere/2024/12/20/nikolas"
    claims = [
        {"source_url": base + ".amp.htm", "review_title": "É falso que Nikolas…", "review_date": "2024-12-20"},
        {"source_url": base + ".htm", "review_title": "É falso que Nikolas…", "review_date": ""},
        {"source_url": base + ".ghtm", "review_title": "É falso que Nikolas…", "review_date": "2024-12-20"},
        {"source_url": "https://www.aosfatos.org/noticias/outra/", "review_title": "Outra"},
    ]
    articles = [{"source_url": base + ".ghtm", "text": "Texto baixado pela variante .ghtm."}]
    claims_ok, articles_ok, removidas = build_index.unificar_variantes(claims, articles)
    assert [c["source_url"] for c in claims_ok] == [base + ".htm", "https://www.aosfatos.org/noticias/outra/"]
    assert claims_ok[0]["review_date"] == "2024-12-20"                   # veio de outra variante
    assert articles_ok == [{"source_url": base + ".htm", "text": "Texto baixado pela variante .ghtm."}]
    assert sorted(removidas) == [base + ".amp.htm", base + ".ghtm"]


def test_mesma_url_em_duas_fontes_nao_e_removida_nem_misturada():
    url = "https://www.aosfatos.org/noticias/insulina/"
    claims = [{"source_url": url, "review_title": "Da API", "claim_reviewed": ""},
              {"source_url": url, "review_title": "Do FACTCK.BR", "claim_reviewed": "Alegação", "corpus": "factckbr"},
              {"source_url": url.rstrip("/"), "review_title": "Sem barra"}]
    claims_ok, _, removidas = build_index.unificar_variantes(claims, [])
    assert claims_ok == [{"source_url": url, "review_title": "Da API", "claim_reviewed": ""}]   # como antes
    assert removidas == [url.rstrip("/")]                       # a URL que fica nunca é apagada do índice


def test_textos_da_mesma_url_passam_como_estao():
    url = "https://www.aosfatos.org/noticias/comprovante/"
    articles = [{"source_url": url, "text": "Texto da API."}, {"source_url": url, "text": "Texto do FACTCK.BR."}]
    _, articles_ok, _ = build_index.unificar_variantes([{"source_url": url, "review_title": "T"}], articles)
    assert articles_ok == articles          # build_records continua usando o último, como antes


def test_unifica_variantes_sem_htm_fica_a_ghtm():
    base = "https://noticias.uol.com.br/confere/2026/09/25/video"
    claims = [{"source_url": base + ".amp.htm", "review_title": "T"}, {"source_url": base + ".ghtm", "review_title": "T"}]
    claims_ok, _, removidas = build_index.unificar_variantes(claims, [])
    assert [c["source_url"] for c in claims_ok] == [base + ".ghtm"] and removidas == [base + ".amp.htm"]


def test_trecho_registra_a_fonte_do_corpus():
    claims = [{"source_url": "https://x.org/1", "review_title": "Título", "corpus": "factckbr"},
              {"source_url": "https://x.org/2", "review_title": "Outro"}]
    corpus = {r["metadata"]["source_url"]: r["metadata"]["corpus"] for r in build_index.build_records(claims, [])}
    assert corpus == {"https://x.org/1": "factckbr", "https://x.org/2": "factcheck_api"}


def test_checagem_antiga_leva_o_ano_no_nome_da_agencia():
    antes = build_index.config.SOURCE_YEAR_BEFORE - 1
    claims = [
        {"source_url": "https://x.org/antiga", "source_name": "Aos Fatos", "review_title": "T",
         "review_date": f"{antes}-05-02T00:00:00Z"},
        {"source_url": "https://x.org/recente", "source_name": "Aos Fatos", "review_title": "T",
         "review_date": f"{build_index.config.SOURCE_YEAR_BEFORE}-01-10T00:00:00Z"},
        {"source_url": "https://x.org/sem-data", "source_name": "Aos Fatos", "review_title": "T"},
        {"source_url": "https://x.org/factckbr", "source_name": "Agência Lupa (2018)", "review_title": "T",
         "review_date": "2018-03-01"},
    ]
    nomes = {r["metadata"]["source_url"].split("/")[-1]: r["metadata"]["source_name"]
             for r in build_index.build_records(claims, [])}
    assert nomes == {"antiga": f"Aos Fatos ({antes})", "recente": "Aos Fatos",
                     "sem-data": "Aos Fatos", "factckbr": "Agência Lupa (2018)"}


# --- import_factckbr: filtros e correções ----------------------------------------

def _linha(url, agencia, claim="Alegação curta sobre o fato", titulo="Título", rotulo="Falso",
           data="2019-03-01 00:00:00", texto="Texto da checagem."):
    return {"URL": url, "agencia": agencia, "claimReviewed": claim, "title": titulo, "alternativeName": rotulo,
            "data": data, "texto_completo": texto}


def test_importa_so_lupa_e_aos_fatos_com_uma_alegacao_por_pagina():
    linhas = [
        _linha("https://piaui.folha.uol.com.br/lupa/2019/01/14/verificamos-acucar-cancer/", "Lupa"),
        _linha("https://aosfatos.org/noticias/insulina/", "Aos Fatos", data="2018-07-22 00:00:00"),
        _linha("https://apublica.org/2018/10/fala/", "Truco"),                         # fica para depois
        _linha("https://piaui.folha.uol.com.br/lupa/2018/10/05/debate/", "Lupa"),     # 2 alegações na página
        _linha("https://piaui.folha.uol.com.br/lupa/2018/10/05/debate/", "Lupa", rotulo="Verdadeiro"),
        _linha("https://aosfatos.org/noticias/vazia/", "Aos Fatos", claim=""),          # sem alegação
        _linha("https://aosfatos.org/noticias/longa/", "Aos Fatos", claim=" ".join(["palavra"] * 61)),
    ]
    checagens, textos, descartes = import_factckbr.converter(linhas)
    assert [c["source_url"] for c in checagens] == [
        "https://www.agencialupa.org/jornalismo/2019/01/14/verificamos-acucar-cancer/",
        "https://www.aosfatos.org/noticias/insulina/",
    ]
    assert [c["source_name"] for c in checagens] == ["Agência Lupa (2019)", "Aos Fatos (2018)"]
    assert all(c["corpus"] == "factckbr" for c in checagens) and len(textos) == 2
    assert checagens[0]["url_original"].startswith("https://piaui.folha.uol.com.br/lupa/")
    assert descartes["página com várias alegações"] == 2 and descartes["sem alegação"] == 1
    assert sum(descartes.values()) == 5


@pytest.mark.parametrize("bruto, limpo", [
    ("#Verificamos:  falso que Honduras proíba cidadãos de terem armas",
     "É falso que Honduras proíba cidadãos de terem armas"),                       # o "É" perdido volta
    ("#VerificamosENEM:  verdade que Av. Paulista só fecha às 13h", "É verdade que Av. Paulista só fecha às 13h"),
    ("#Verificamos: Charge que mostra Bolsonaro não foi publicada na Time",
     "Charge que mostra Bolsonaro não foi publicada na Time"),                     # só tira a marca
    ("Damares não cancelou indenizações de anistiados políticos | Aos Fatos",
     "Damares não cancelou indenizações de anistiados políticos"),
    ("Açúcar não causa câncer; limão e óleo de coco não substituem químio",
     "Açúcar não causa câncer; limão e óleo de coco não substituem químio"),       # sem mudança
])
def test_limpar_titulo(bruto, limpo):
    assert import_factckbr.limpar_titulo(bruto) == limpo


def test_alegacao_perde_as_aspas_e_veredito_fica_como_publicado():
    [c], _, _ = import_factckbr.converter([_linha("https://aosfatos.org/noticias/a/", "Aos Fatos",
                                                  claim="'Ciro Gomes vota em Bolsonaro'", rotulo="falso")])
    assert c["claim_reviewed"] == "Ciro Gomes vota em Bolsonaro" and c["agency_verdict"] == "falso"


def test_descarta_verdadeiro_com_titulo_que_desmente():
    linhas = [
        _linha("https://piaui.folha.uol.com.br/lupa/2018/09/01/verificamos-freixo/", "Lupa", rotulo="Verdadeiro",
               titulo="#Verificamos:  falso que Freixo recebe auxílio-moradia"),            # "É" restaurado
        _linha("https://aosfatos.org/noticias/terco/", "Aos Fatos", rotulo="verdadeiro",
               titulo="Papa Francisco não enviou terço a Lula; Vaticano desmente boato | Aos Fatos"),
        _linha("https://piaui.folha.uol.com.br/lupa/2018/11/04/verificamos-enem/", "Lupa", rotulo="Verdadeiro",
               titulo="#VerificamosENEM:  verdade que Av. Paulista só fecha às 13h"),        # fica
        _linha("https://aosfatos.org/noticias/damares/", "Aos Fatos", rotulo="falso",
               titulo="Damares não cancelou indenizações de anistiados políticos"),          # só vale para apoia
    ]
    checagens, _, descartes = import_factckbr.converter(linhas)
    assert [c["review_title"] for c in checagens] == [
        "É verdade que Av. Paulista só fecha às 13h",
        "Damares não cancelou indenizações de anistiados políticos",
    ]
    assert descartes["veredito verdadeiro com título que desmente"] == 2


def test_importador_le_o_csv_e_grava_os_dois_arquivos(tmp_path):
    import csv

    caminho = tmp_path / "factckbr.csv"
    linha = _linha("https://aosfatos.org/noticias/a/", "Aos Fatos", texto="Linha 1\nLinha 2 com, vírgula")
    with caminho.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linha))
        w.writeheader()
        w.writerow(linha)
    claims, articles = tmp_path / "c.jsonl", tmp_path / "a.jsonl"
    assert import_factckbr.main(["--csv", str(caminho), "--claims", str(claims), "--articles", str(articles)]) == 0
    [art] = [json.loads(l) for l in articles.read_text(encoding="utf-8").splitlines()]
    assert art["text"] == "Linha 1\nLinha 2 com, vírgula"
    assert json.loads(claims.read_text(encoding="utf-8"))["source_url"] == "https://www.aosfatos.org/noticias/a/"



# --- import_lupa: checagens da Agência Lupa pelo sitemap ---------------------------

@pytest.mark.parametrize("url, candidata", [
    ("https://www.agencialupa.org/verificacao/2026/10/08/e-falso-que-mesarios-na-bahia/", True),
    ("https://www.agencialupa.org/checagem/2025/03/01/qualquer-coisa/", True),
    ("https://www.agencialupa.org/eleicoes/2026/10/08/video-antigo-de-lula-e-editado/", True),
    ("https://www.agencialupa.org/jornalismo/2023/03/29/e-falso-que-oms-mudou-a-classificacao/", True),
    ("https://www.agencialupa.org/jornalismo/2020/11/25/verificamos-cafeteira-3-coracoes/", True),
    ("https://www.agencialupa.org/jornalismo/2024/05/02/e-verdade-que-o-salario-minimo/", True),
    ("https://www.agencialupa.org/jornalismo/2021/06/10/entrevista-com-diretora/", False),   # reportagem
    ("https://www.agencialupa.org/noticias/2025/09/25/vai-dar-namoro/", False),
    ("https://www.agencialupa.org/institucional/2020/01/01/e-falso-que-x/", False),
])
def test_lupa_candidatas_pelo_endereco(url, candidata):
    assert import_lupa.eh_candidata(url) is candidata


@pytest.mark.parametrize("titulo, esperado", [
    ("É falso que OMS mudou a classificação de jovens e idosos",
     ("Falso", "OMS mudou a classificação de jovens e idosos")),
    ("É verdade que o salário mínimo subiu 7% em 2024.", ("Verdade", "O salário mínimo subiu 7% em 2024")),
    ("#Verificamos: É enganoso que vacina cause autismo", ("Enganoso", "Vacina cause autismo")),
    ("É FALSO que Lula foi preso em 2025", ("Falso", "Lula foi preso em 2025")),
    ("É golpe mensagem que oferece cafeteiras gratuitas", None),   # sem "É <rótulo> que <alegação>"
    ("Vídeo antigo de Lula é editado para sugerir críticas", None),
    ("É falso que", None),
])
def test_lupa_veredito_e_alegacao_saem_do_titulo(titulo, esperado):
    assert import_lupa.alegacao_do_titulo(titulo) == esperado


def test_lupa_limpa_titulo_e_data_vem_da_url():
    assert import_lupa.limpar_titulo("#Verificamos:  É falso que X • Lupa") == "É falso que X"
    assert import_lupa.data_da_url("https://www.agencialupa.org/jornalismo/2020/11/25/x/") == "2020-11-25"
    assert import_lupa.data_da_url("https://www.agencialupa.org/sobre/") == ""


def test_lupa_monta_checagem_no_formato_do_corpus():
    url = "https://www.agencialupa.org/jornalismo/2020/11/25/e-falso-que-x/"
    checagem, texto, motivo = import_lupa.montar(url, "É falso que X fechou o STF • Lupa", "Texto da checagem.")
    assert motivo is None
    assert checagem == {
        "source_url": url, "source_name": "Agência Lupa", "review_title": "É falso que X fechou o STF",
        "review_date": "2020-11-25", "agency_verdict": "Falso", "claim_reviewed": "X fechou o STF",
        "language": "pt", "corpus": "lupa",
    }
    assert texto == {"source_url": url, "title": "É falso que X fechou o STF", "text": "Texto da checagem.",
                     "corpus": "lupa"}


def test_lupa_descarta_sem_padrao_sem_texto_e_verdade_que_desmente():
    url = "https://www.agencialupa.org/verificacao/2026/01/02/a/"
    assert import_lupa.montar(url, "É golpe mensagem que oferece cafeteiras", "Texto.")[2] == "título sem 'É <rótulo> que'"
    assert import_lupa.montar(url, "É falso que X fechou o STF", "")[2] == "sem texto"
    assert import_lupa.montar(url, "É verdade que Lula não cortou o Bolsa Família", "Texto.")[2] == \
        "veredito verdadeiro com título que desmente"


def test_lupa_pendentes_pulam_feitas_descartadas_e_factckbr():
    urls = ["https://www.agencialupa.org/jornalismo/2019/01/14/verificamos-acucar/",
            "https://www.agencialupa.org/jornalismo/2020/01/01/e-falso-que-a/",
            "https://www.agencialupa.org/jornalismo/2020/01/02/e-falso-que-b/",
            "https://www.agencialupa.org/jornalismo/2020/01/03/e-falso-que-c"]
    ja = {"https://www.agencialupa.org/jornalismo/2019/01/14/verificamos-acucar",   # FACTCK.BR, sem a barra
          "https://www.agencialupa.org/jornalismo/2020/01/01/e-falso-que-a/"}       # já baixada
    assert import_lupa.pendentes(urls, ja) == urls[2:]
