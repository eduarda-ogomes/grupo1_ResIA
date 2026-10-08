"""Testes da etapa "mesma alegação" (src/retrieval/etapa2.py): normalização da
alegação, termos-chave e vereditos (formatos encontrados no corpus real).

    python -m pytest tests/unit/test_evidence_etapa2.py
"""

import pytest

from src.retrieval.etapa2 import (content_overlap, display_verdict, key_terms, key_terms_present, name_groups,
                                  normalize_claim, normalize_text, stance_from_verdict)

# --- Normalização e termos-chave -------------------------------------------------


@pytest.mark.parametrize(
    "claim, expected",
    [
        ("Foto mostra Edson Fachin apontando o dedo para Alexandre de Moraes em discussão",
         "Edson Fachin apontando o dedo para Alexandre de Moraes em discussão"),
        ("Vídeo mostra que Lula recebeu refugiados", "Lula recebeu refugiados"),
        ("Vídeos mostram ajuda humanitária da China em Gaza", "Ajuda humanitária da China em Gaza"),
        ("Imagens provam que Lula tem um sósia", "Lula tem um sósia"),
        ("Em áudio, Lula parabeniza Moraes pela prisão de Bolsonaro", "Lula parabeniza Moraes pela prisão de Bolsonaro"),
        ("Vídeo publicado no TikTok mostra multidão na Paulista", "Multidão na Paulista"),
        # Sem enquadramento de mídia: não muda.
        ("Lula morreu após hemorragia cerebral", "Lula morreu após hemorragia cerebral"),
        ("Fotógrafo mostra o Rio", "Fotógrafo mostra o Rio"),
        ("", ""),
    ],
)
def test_normalize_claim(claim, expected):
    assert normalize_claim(claim) == expected


def test_normalize_text_numeros():
    assert normalize_text("R$ 5.000, R$ 5 mil, 1,5 mil e 1.800") == "r$ 5000, r$ 5000, 1500 e 1800"


@pytest.mark.parametrize(
    "sentence, terms",
    [
        ("Fachin apontou o dedo para Moraes durante uma discussão no STF.", ["fachin", "moraes", "stf"]),
        ("Eduardo Bolsonaro foi fotografado ao lado de um elefante morto.", ["eduardo", "bolsonaro"]),
        ("Lewandowski não tomou vacina contra a Covid-19.", ["lewandowski", "covid"]),
        ("Governo Lula anunciou um novo programa.", ["lula"]),        # "Governo" é palavra comum de início
        ("O chá da folha de mamão cura a chikungunya em apenas três dias.", ["chikungunya"]),
        ("A Receita vai taxar Pix acima de R$ 5 mil.", ["receita", "pix", "5000"]),
        ("Os beneficiários vão receber R$ 1.800 no dia 20 de julho.", ["1800", "20"]),
        ("Não existe nada melhor do que a natureza.", []),
    ],
)
def test_key_terms(sentence, terms):
    assert key_terms(sentence) == terms


def test_nomes_compostos_formam_um_grupo():
    assert name_groups("Imagem mostra Edson Fachin apontando para Alexandre de Moraes") == [
        ["edson", "fachin"], ["alexandre", "moraes"]]


CHECAGEM_PARAGUAI = ["Presidente do Paraguai agradece Lula pela migração de empresas brasileiras",
                     "É falso que presidente do Paraguai agradeceu a Lula na ONU"]
ALEGACAO_PARAGUAI = "Presidente do Paraguai agradece Lula pela migração de empresas brasileiras"


@pytest.mark.parametrize(
    "sentence, texts, claim, expected",
    [
        # Paráfrase (o radical tolera "paraguaio").
        ("O presidente paraguaio agradeceu a Lula pela ida de empresas ao Paraguai.",
         CHECAGEM_PARAGUAI, ALEGACAO_PARAGUAI, (True, [], [])),
        # Troca de nome: falta "argentina" e a alegação tem "paraguai", ausente da frase.
        ("O presidente argentino agradeceu a Lula pela ida de empresas à Argentina.",
         CHECAGEM_PARAGUAI, ALEGACAO_PARAGUAI, (False, ["argentina"], ["paraguai"])),
        # Contexto a mais sem troca: "STF" não está no título, mas não há nome sobrando na alegação.
        ("Fachin apontou o dedo para Moraes durante uma discussão acalorada no STF.",
         ["Imagem de Fachin apontando dedo para Moraes é falsa e criada por IA"],
         "Imagem mostra Fachin apontando o dedo para Moraes", (True, ["stf"], [])),
        # Troca de nome no início da frase da alegação (Lewandowski) e da frase (Fux, no meio).
        ("O ministro Fux nunca se vacinou contra a Covid.",
         ["Lewandowski tomou, sim, vacina contra a Covid-19"], "Lewandowski não tomou vacina contra a Covid-19",
         (False, ["fux"], ["lewandowski"])),
        # Troca de doença e de número.
        ("O chá de mamão cura a chikungunya em três dias.", ["Não existe tratamento para a dengue"],
         "Chá de folha de mamão cura a dengue em três dias", (False, ["chikungunya"], ["dengue"])),
        ("A Receita Federal vai cobrar imposto sobre Pix acima de R$ 50 mil.",
         ["É falso que Pix acima de R$ 5.000 será taxado pela Receita Federal"],
         "Pix acima de R$ 5.000 será taxado pela Receita Federal", (False, ["50000"], ["5000"])),
    ],
)
def test_key_terms_present_com_alegacao(sentence, texts, claim, expected):
    assert key_terms_present(sentence, texts, claim) == expected


def test_sem_alegacao_a_regra_e_estrita():
    """Sem a alegação, qualquer termo ausente reprova (contexto a mais também)."""
    result = key_terms_present("Fachin apontou o dedo para Moraes no STF.", ["Imagem de Fachin e Moraes é falsa"])
    assert result == (False, ["stf"], [])


# --- Ancoragem lexical (G2) ------------------------------------------------------

def test_frase_e_alegacao_sem_palavra_em_comum_tem_sobreposicao_zero():
    frase = "Isso resultou em acúmulo de material combustível."
    titulo = "Vídeo de aeronave tomada por névoa foi gravado na China, não na Amazônia"
    assert content_overlap(frase, [titulo]) == 0


def test_sobreposicao_tolera_flexao_e_acento():
    assert content_overlap("O chá da folha de mamão cura a dengue.", ["Chá de folhas de mamão não cura dengue"]) == 5


def test_sobreposicao_conta_cada_radical_da_frase_uma_vez_e_soma_os_textos():
    frase = "Lula visitou Lula e o Paraguai."
    assert content_overlap(frase, ["Lula não foi", "Paraguaio disse"]) == 2
    assert content_overlap(frase, []) == 0
    assert content_overlap("", ["Lula"]) == 0


# --- Vereditos -------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, stance",
    [
        ("falso", "contradiz"),
        ("Falso", "contradiz"),
        ("Falso: Na verdade, uma empresa subsidiária de uma estatal chinesa adquiriu uma mineradora.", "contradiz"),
        ("Montagem", "contradiz"),
        ("verdadeiro", "apoia"),
        ("Comprovado", "apoia"),
        ("Enganoso", "insuficiente"),
        ("Enganoso: O conteúdo foi tirado de contexto para parecer atual.", "insuficiente"),
        ("não_é_bem_assim", "insuficiente"),
        ("Falta contexto", "insuficiente"),
        ("Contextualizando: Lula recebe aposentadoria especial como anistiado desde 1993.", "insuficiente"),
        ("Sátira", "insuficiente"),
        ("verdadeiro, mas impreciso", "insuficiente"),
        ("É mentirosa a afirmação de que Moraes ordenou a troca de 48 urnas.", "insuficiente"),  # texto livre: conservador
        ("", "insuficiente"),
        (None, "insuficiente"),
    ],
)
def test_stance_from_verdict(raw, stance):
    assert stance_from_verdict(raw) == stance


@pytest.mark.parametrize(
    "raw, shown",
    [
        ("falso", "Falso"),
        ("não_é_bem_assim", "Não é bem assim"),
        ("Falso: Na verdade, uma empresa adquiriu uma mineradora.", "Falso"),
        ("Contextualizando: Lula recebe aposentadoria.", "Contextualizando"),
        ("A prefeita não foi alvo de operação da PF: diz o site.", "A prefeita não foi alvo de operação da PF: diz o site."),
        ("", None),
        (None, None),
    ],
)
def test_display_verdict(raw, shown):
    assert display_verdict(raw) == shown


# --- Vocabulário de nomes do corpus (primeira palavra, pontuação, siglas) ---------------------

from src.retrieval import etapa2  # noqa: E402


@pytest.fixture
def vocabulario(monkeypatch):
    """Vocabulário fixo, para o teste não depender do data/corpus/nomes_proprios.txt."""
    voc = {"lula", "bolsonaro", "moraes", "janja", "stf", "cop30", "natal", "carmen", "lucia"}
    monkeypatch.setattr(etapa2, "_name_vocabulary", voc)
    monkeypatch.setattr(etapa2, "_name_vocabulary_loaded", True)
    return voc


def test_vocabulario_usa_so_maiuscula_fora_do_inicio_e_ignora_grito():
    textos = [
        "Vídeo mostra Lula em Natal com a Janja",            # Vídeo: início de frase, não conta
        "Foto de Lula. Vacina causa autismo",                 # Vacina: início da 2ª frase
        "Post diz que a vacina mata e que o STF votou",       # vacina em minúscula; STF é sigla
        "Indígenas fazem protesto na COP30 sobre Indígenas",  # 2 maiúsculas no meio...
        "os indígenas e os indígenas e os indígenas",         # ...mas 3 minúsculas: fica de fora
        "É URGENTE: compartilhe",                             # grito, não nome
    ]
    voc = etapa2.build_name_vocabulary(textos)
    assert {"lula", "natal", "janja", "stf", "cop30"} <= voc
    assert not {"video", "vacina", "indigenas", "urgente", "a", "de"} & voc


def test_primeira_palavra_so_e_nome_se_o_corpus_usa_como_nome(vocabulario):
    assert etapa2.name_groups("Aviões americanos pousaram em Natal.") == [["natal"]]
    assert etapa2.name_groups("Lula disse que vai taxar o Pix.") == [["lula"], ["pix"]]


def test_pontuacao_separa_grupos_e_sigla_com_numero_fica_inteira(vocabulario):
    assert etapa2.name_groups("Arrependida, Cármen Lúcia defende a anistia.") == [["carmen", "lucia"]]
    assert etapa2.name_groups("Indígenas protestaram na COP30 contra a Janja.") == [["cop30"], ["janja"]]


def test_casos_da_avaliacao_passam_e_troca_no_inicio_continua_barrada(vocabulario):
    # F-15: "Aviões" não é nome, então a checagem certa não é rejeitada como troca
    assert key_terms_present("Aviões de caça F-15 pousaram em Natal.",
                             ["Caças F-15 dos EUA pousaram em Natal"], "Caças F-15 dos EUA pousaram em Natal").ok
    # Cármen Lúcia: "Arrependida" não é nome nem gruda no nome dela
    assert key_terms_present("Arrependida, Cármen Lúcia admitiu que apoia a anistia.",
                             ["Ministra Cármen Lúcia admite apoiar anistia no Congresso"],
                             "Ministra Cármen Lúcia admite apoiar anistia no Congresso").ok
    # COP30 bate com COP30
    assert key_terms_present("Indígenas protestaram na COP30 por um barco igual ao da Janja.",
                             ["índios protestam na COP30 querendo navio igual da Janja"],
                             "índios protestam na COP30 querendo navio igual da Janja").ok
    # Troca de nome na primeira palavra continua barrada: "Lula" está no vocabulário
    resultado = key_terms_present("Lula prometeu taxar o Pix.", ["Bolsonaro prometeu taxar o Pix"],
                                  "Bolsonaro prometeu taxar o Pix")
    assert not resultado.ok and resultado.missing == ["lula"]


def test_sem_vocabulario_vale_a_regra_antiga(monkeypatch, tmp_path):
    monkeypatch.setattr(etapa2, "_name_vocabulary_loaded", False)
    monkeypatch.setattr(etapa2, "_name_vocabulary", None)
    assert etapa2.load_name_vocabulary(tmp_path / "nao_existe.txt") is None
    assert etapa2.name_groups("Aviões pousaram em Natal.") == [["avioes"], ["natal"]]


def test_vocabulario_versionado_existe_e_tem_os_nomes_principais():
    voc = set(etapa2.NAME_VOCABULARY_PATH.read_text(encoding="utf-8").split())
    assert {"lula", "bolsonaro", "moraes", "stf"} <= voc
    assert not {"avioes", "arrependida", "vacina", "governo"} & voc
