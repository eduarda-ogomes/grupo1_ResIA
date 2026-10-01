"""Avaliação do Agente de Evidências (Manual §6.2 e §7.1).

Três comandos, sempre a partir da raiz do repositório:

    python eval/avaliar_evidencias.py sortear --n 30 [--veredito verdadeiro] [--agencia AFP] [--semente 1]
    python eval/avaliar_evidencias.py esqueleto [--semente 1] [--saida data/gold/evidencias.json] [--forcar]
    python eval/avaliar_evidencias.py completar [--refazer-textos]
    python eval/avaliar_evidencias.py validar [--gold data/gold/evidencias.json]
    python eval/avaliar_evidencias.py avaliar [--split teste|calibracao|todos] [--salvar]

- sortear: lista checagens do corpus para parafrasear (sem índice, sem modelos).
- esqueleto: gera as 12 entradas com as checagens sorteadas e as frases em branco.
- completar: monta o texto de cada entrada juntando as frases escritas.
- validar: confere o conjunto de avaliação (sem índice, sem modelos).
- avaliar: roda a busca e o agente reais e calcula as métricas (precisa do índice e dos modelos).

Métricas (definições no ADR 3, docs/agents/evidencias_decisoes.md):
- Recall@5: em frases `com_checagem`, alguma URL aceita está entre as 5 primeiras
  checagens distintas da busca, sem limiar e sem a etapa 2.
- Cobertura: em frases `com_checagem`, o agente emitiu evidência com URL aceita.
- Macro-F1 de stance: em frases `com_checagem` e `desmente`; stance prevista = a da
  primeira evidência com URL aceita, ou `insuficiente` se não houver (§4.8).
- Evidência inventada: em frases `sem_checagem`, % com qualquer evidência.
- Casamento errado: evidências cujo link não está entre as URLs aceitas da frase.

Formato do conjunto (data/gold/evidencias.json):

    {"versao": 1, "entradas": [{
        "id": "ev01", "split": "teste", "anotador": "R2", "revisor": null,
        "texto": "Texto da notícia, como o Ingestor receberia.",
        "frases": [{"id": "s01", "texto": "...", "tipo": "com_checagem",
                    "checagens_aceitas": ["https://..."], "stance_esperada": "contradiz",
                    "alegacao_original": "...", "obs": ""}]}]}

As funções de cálculo e de validação são puras (sem torch nem chromadb) e são
testadas no CI em tests/unit/test_evidence_avaliacao.py.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Iterable, NamedTuple, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.retrieval import config  # noqa: E402
from src.retrieval.etapa2 import (DISEASES, display_verdict, name_groups, normalize_text,  # noqa: E402
                                  stance_from_verdict, tokenize)

GOLD_PATH = REPO_ROOT / "data" / "gold" / "evidencias.json"
PARES_PATH = REPO_ROOT / "data" / "corpus" / "pares_etapa2.json"
RESULTADOS_DIR = REPO_ROOT / "eval" / "resultados"

TIPOS = ("com_checagem", "sem_checagem", "fato_parecido", "troca_numero", "desmente")
TIPOS_SEM_URL = {"sem_checagem", "fato_parecido", "troca_numero"}
TIPOS_COM_URL = {"com_checagem", "desmente"}
STANCES = ("apoia", "contradiz", "insuficiente")
SPLITS = ("calibracao", "teste")

K = 5                    # Recall@K
K_BUSCA = 30             # trechos buscados para montar o ranking de checagens distintas
LIMIAR_VAZAMENTO = 0.6   # fração das palavras da frase que aparecem no título ou na alegação

METAS = {
    "recall_at_5": (">=", 0.70),
    "macro_f1": (">=", 0.65),
    "evidencia_inventada": ("<=", 0.10),
    "casamento_errado": ("==", 0),
}

# Composição esperada (tabela 2.2 do plano): (rótulo, alvo, mínimo, máximo).
# A tolerância é de ±2 frases; toda linha precisa ter pelo menos 1 (apoia: pelo menos 2).
COMPOSICAO = (
    ("com_checagem, stance contradiz", 12, 10, 14),
    ("com_checagem, stance insuficiente", 4, 2, 6),
    ("com_checagem, stance apoia", 2, 2, None),
    ("com_checagem, AFP (só título)", 2, 1, None),   # URLs da AFP também entram como aceitas extras
    ("sem_checagem", 10, 8, 12),
    ("fato_parecido + troca_numero", 4, 2, 6),
    ("desmente", 2, 1, 4),
)
ENTRADAS_ALVO = (12, 10, 14)

AFP_HOST = "checamos.afp.com"
ESPELHOS = ("bol.uol.com.br", "acervo.estadao.com.br")   # republicam a checagem de outro endereço
# Checagens que são guias ou explicações, não alegações ("Como funciona o golpe do SMS").
_EXPLICATIVO = re.compile(
    r"^\s*(como\b|saiba\b|entenda\b|veja\b|o que [ée]\b|por que\b|confira\b)|\bexplica\b", re.IGNORECASE
)
_NEGATIVA = re.compile(r"^\s*n[ãa]o\b", re.IGNORECASE)
MIN_ALEGACAO_CHARS = 25
MAX_ALEGACAO_CHARS = 180   # acima disso costuma ser o post inteiro, não uma alegação


# =============================================================================
# Leitura dos dados
# =============================================================================

def carregar_json(caminho: Path) -> dict:
    with Path(caminho).open(encoding="utf-8") as f:
        return json.load(f)


def carregar_corpus(caminho: Path) -> dict[str, dict]:
    """Checagens da API (factcheck_api.jsonl), uma por URL."""
    corpus: dict[str, dict] = {}
    with Path(caminho).open(encoding="utf-8") as f:
        for linha in f:
            if linha.strip():
                registro = json.loads(linha)
                corpus.setdefault(registro["source_url"], registro)
    return corpus


def carregar_pares_urls(caminho: Path = PARES_PATH) -> set[str]:
    """URLs dos 37 pares do experimento da etapa 2 (não devem entrar no gold)."""
    if not Path(caminho).exists():
        return set()
    return {p["source_url"] for p in carregar_json(caminho).get("pares", []) if p.get("source_url")}


def chave(entrada_id: str, frase_id: str) -> str:
    return f"{entrada_id}/{frase_id}"


def selecionar_frases(gold: dict, split: str = "todos") -> list[dict]:
    """Frases do conjunto, achatadas, com a entrada de origem; split = calibracao, teste ou todos."""
    frases = []
    for entrada in gold.get("entradas", []):
        if split != "todos" and entrada.get("split") != split:
            continue
        for frase in entrada.get("frases", []):
            frases.append({
                "chave": chave(entrada["id"], frase["id"]),
                "entrada_id": entrada["id"],
                "frase_id": frase["id"],
                "split": entrada.get("split"),
                "texto": frase.get("texto", ""),
                "tipo": frase.get("tipo"),
                "aceitas": list(frase.get("checagens_aceitas") or []),
                "stance_esperada": frase.get("stance_esperada"),
            })
    return frases


def _host(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


# =============================================================================
# Validação do conjunto (pura)
# =============================================================================

class Problema(NamedTuple):
    nivel: str   # "erro" (impede a avaliação) ou "aviso"
    onde: str    # "ev01/s02", "ev01" ou "conjunto"
    msg: str


def sobreposicao(frase: str, alvo: str) -> float:
    """Fração das palavras da frase (sem stopwords, sem acentos) que aparecem no alvo."""
    minhas = set(tokenize(frase))
    if not minhas:
        return 0.0
    return len(minhas & set(tokenize(alvo))) / len(minhas)


def _normaliza_espacos(texto: str) -> str:
    return " ".join((texto or "").split())


def contar_composicao(gold: dict) -> dict[str, int]:
    """Contagens da tabela 2.2 do plano."""
    contagem = Counter()
    for frase in selecionar_frases(gold):
        tipo, stance = frase["tipo"], frase["stance_esperada"]
        if tipo == "com_checagem":
            if stance in STANCES:
                contagem[f"com_checagem, stance {stance}"] += 1
            if any(_host(u) == AFP_HOST for u in frase["aceitas"]):
                contagem["com_checagem, AFP (só título)"] += 1
        elif tipo in ("fato_parecido", "troca_numero"):
            contagem["fato_parecido + troca_numero"] += 1
        elif tipo in ("sem_checagem", "desmente"):
            contagem[tipo] += 1
    return {rotulo: contagem.get(rotulo, 0) for rotulo, *_ in COMPOSICAO}


def validar_gold(gold: dict, corpus: dict[str, dict], pares_urls: Iterable[str] = ()) -> list[Problema]:
    """Confere o conjunto de avaliação antes de rodar. Não usa índice nem modelos."""
    problemas: list[Problema] = []

    def erro(onde, msg):
        problemas.append(Problema("erro", onde, msg))

    def aviso(onde, msg):
        problemas.append(Problema("aviso", onde, msg))

    if not isinstance(gold, dict) or not isinstance(gold.get("entradas"), list):
        erro("conjunto", "o arquivo precisa ser um objeto com a lista 'entradas'")
        return problemas
    if "versao" not in gold:
        aviso("conjunto", "falta o campo 'versao'")

    pares_urls = set(pares_urls)
    ids_entradas: set[str] = set()
    sem_revisor = 0
    splits = Counter()

    for i, entrada in enumerate(gold["entradas"]):
        eid = entrada.get("id") if isinstance(entrada, dict) else None
        if not isinstance(eid, str) or not eid:
            erro(f"entrada #{i + 1}", "entrada sem 'id'")
            continue
        if eid in ids_entradas:
            erro(eid, "id de entrada repetido")
        ids_entradas.add(eid)

        if entrada.get("split") not in SPLITS:
            erro(eid, f"'split' deve ser um de {SPLITS}, veio {entrada.get('split')!r}")
        else:
            splits[entrada["split"]] += 1
        if not entrada.get("revisor"):
            sem_revisor += 1
        texto_entrada = _normaliza_espacos(entrada.get("texto", ""))
        frases = entrada.get("frases")
        if not isinstance(frases, list) or not frases:
            erro(eid, "entrada sem 'frases'")
            continue
        frases_escritas = all(isinstance(f, dict) and str(f.get("texto", "")).strip() for f in frases)
        if not texto_entrada and frases_escritas:
            erro(eid, "entrada sem 'texto' (rode o comando completar)")

        ids_frases: set[str] = set()
        for j, frase in enumerate(frases):
            fid = frase.get("id") if isinstance(frase, dict) else None
            if not isinstance(fid, str) or not fid:
                erro(f"{eid}/#{j + 1}", "frase sem 'id'")
                continue
            onde = chave(eid, fid)
            if fid in ids_frases:
                erro(onde, "id de frase repetido na entrada")
            ids_frases.add(fid)

            texto = frase.get("texto", "")
            if not str(texto).strip():
                erro(onde, "frase ainda sem 'texto'")
            elif texto_entrada and _normaliza_espacos(texto) not in texto_entrada:
                aviso(onde, "a frase não aparece igual no texto da entrada (o Ingestor não a geraria assim)")

            tipo = frase.get("tipo")
            if tipo not in TIPOS:
                erro(onde, f"'tipo' deve ser um de {TIPOS}, veio {tipo!r}")
                continue
            aceitas = frase.get("checagens_aceitas")
            if aceitas is None:
                aceitas = []
            if not isinstance(aceitas, list) or not all(isinstance(u, str) and u for u in aceitas):
                erro(onde, "'checagens_aceitas' deve ser uma lista de URLs")
                continue
            if len(set(aceitas)) != len(aceitas):
                aviso(onde, "URL repetida em 'checagens_aceitas'")
            stance = frase.get("stance_esperada")
            if stance is not None and stance not in STANCES:
                erro(onde, f"'stance_esperada' deve ser um de {STANCES} ou null, veio {stance!r}")
                continue

            # Coerência entre tipo, URLs e stance.
            if tipo in TIPOS_SEM_URL:
                if aceitas:
                    erro(onde, f"tipo {tipo} não tem checagem aceita: 'checagens_aceitas' deve ficar vazia")
                if stance is not None:
                    erro(onde, f"tipo {tipo} não deve ter evidência: 'stance_esperada' deve ser null")
            else:
                if not aceitas:
                    erro(onde, f"tipo {tipo} precisa de pelo menos uma URL em 'checagens_aceitas'")
                if stance is None:
                    erro(onde, f"tipo {tipo} precisa de 'stance_esperada'")
                elif tipo == "desmente" and stance != "apoia":
                    aviso(onde, "em 'desmente' a checagem costuma APOIAR a frase; confira a stance")
            if tipo in ("fato_parecido", "troca_numero") and not frase.get("alegacao_original"):
                aviso(onde, "preencha 'alegacao_original' com a checagem de onde veio a troca")

            # URLs: existem no corpus? Estão nos 37 pares? O veredito bate com a stance?
            for url in aceitas:
                if url not in corpus:
                    erro(onde, f"URL fora do corpus (Recall impossível): {url}")
                elif url in pares_urls:
                    aviso(onde, f"URL usada nos 37 pares da etapa 2 (resultado inflado): {url}")
            if tipo == "com_checagem" and stance is not None:
                divergentes = [
                    f"{corpus[u].get('source_name')}: {display_verdict(corpus[u].get('agency_verdict'))}"
                    for u in aceitas
                    if u in corpus and stance_from_verdict(corpus[u].get("agency_verdict")) != stance
                ]
                if divergentes:
                    aviso(onde, f"stance esperada '{stance}' difere do veredito de: {'; '.join(divergentes)}")

            # Vazamento (§6.2): a frase não pode copiar o título nem a alegação.
            alvos = [frase.get("alegacao_original") or ""]
            for url in aceitas:
                if url in corpus:
                    alvos += [corpus[url].get("claim_reviewed") or "", corpus[url].get("review_title") or ""]
            maior = max((sobreposicao(texto, a) for a in alvos if a), default=0.0)
            if maior > LIMIAR_VAZAMENTO:
                aviso(onde, f"possível vazamento: {maior:.0%} das palavras da frase estão no título ou na "
                            f"alegação; parafraseie mais")

    # Conjunto: revisão, split e composição.
    if ids_entradas and sem_revisor:
        aviso("conjunto", f"{sem_revisor} entrada(s) sem 'revisor' (a §6.2 pede uma segunda anotação)")
    n_entradas = len(ids_entradas)
    alvo, minimo, maximo = ENTRADAS_ALVO
    if not minimo <= n_entradas <= maximo:
        aviso("conjunto", f"{n_entradas} entradas (alvo: {alvo})")
    if abs(splits["calibracao"] - splits["teste"]) > 1:
        aviso("conjunto", f"split desequilibrado: {splits['calibracao']} calibração × {splits['teste']} teste")
    contagem = contar_composicao(gold)
    for rotulo, alvo, minimo, maximo in COMPOSICAO:
        n = contagem[rotulo]
        if n < minimo or (maximo is not None and n > maximo):
            faixa = f"≥ {minimo}" if maximo is None else f"{minimo}–{maximo}"
            aviso("conjunto", f"{rotulo}: {n} frase(s) (esperado {faixa}, alvo {alvo})")
    return problemas


# =============================================================================
# Métricas (puras)
# =============================================================================

def recall_at_k(ranking: Sequence[str], aceitas: Iterable[str], k: int = K) -> bool:
    """Alguma URL aceita está entre as k primeiras checagens do ranking?"""
    aceitas = set(aceitas)
    return any(url in aceitas for url in list(ranking)[:k])


def prever_stance(evidencias: Iterable[dict], aceitas: Iterable[str]) -> str:
    """Stance da primeira evidência com URL aceita; sem nenhuma, 'insuficiente' (§4.8)."""
    aceitas = set(aceitas)
    for ev in evidencias or []:
        if ev.get("source_url") in aceitas:
            return ev.get("stance")
    return "insuficiente"


def macro_f1(pares: Sequence[tuple[str, str]], classes: Sequence[str] = STANCES) -> dict:
    """Precisão, revocação e F1 por classe e a média (macro) sobre as classes com exemplo anotado.

    pares = [(esperada, prevista), ...]. Uma classe sem nenhum exemplo anotado sai da
    média, e o resultado traz um aviso.
    """
    por_classe = {}
    for c in classes:
        tp = sum(1 for e, p in pares if e == c and p == c)
        fp = sum(1 for e, p in pares if e != c and p == c)
        fn = sum(1 for e, p in pares if e == c and p != c)
        suporte = tp + fn
        precisao = tp / (tp + fp) if tp + fp else 0.0
        if suporte:
            revocacao = tp / suporte
            f1 = 2 * precisao * revocacao / (precisao + revocacao) if precisao + revocacao else 0.0
        else:
            revocacao = f1 = None
        por_classe[c] = {"precisao": precisao, "revocacao": revocacao, "f1": f1, "suporte": suporte,
                         "previstas": tp + fp}
    na_media = [c for c in classes if por_classe[c]["suporte"]]
    valor = sum(por_classe[c]["f1"] for c in na_media) / len(na_media) if na_media else None
    avisos = [f"classe '{c}' sem exemplo anotado: fora da média" for c in classes if c not in na_media]
    return {"valor": valor, "classes_na_media": na_media, "por_classe": por_classe, "n": len(pares),
            "avisos": avisos}


def matriz_confusao(pares: Sequence[tuple[str, str]], classes: Sequence[str] = STANCES) -> dict:
    """{esperada: {prevista: n}}."""
    matriz = {e: {p: 0 for p in classes} for e in classes}
    for e, p in pares:
        matriz.setdefault(e, {q: 0 for q in classes})
        matriz[e][p] = matriz[e].get(p, 0) + 1
    return matriz


def _taxa(acertos: int, total: int) -> dict:
    return {"acertos": acertos, "total": total, "valor": acertos / total if total else None}


def calcular_metricas(frases: Sequence[dict], rankings: dict[str, list[str]],
                      saidas: dict[str, list[dict]]) -> dict:
    """Junta tudo. frases vêm de selecionar_frases; rankings e saidas são indexados pela chave da frase."""
    detalhes, erros = [], []
    pares_stance: list[tuple[str, str]] = []
    recall_ok = recall_total = cobertas = inventadas = total_sem = 0
    errados_por_tipo: Counter = Counter()
    frases_com_errado = 0

    for f in frases:
        k = f["chave"]
        evidencias = saidas.get(k, []) or []
        ranking = list(rankings.get(k, []))[:K]
        aceitas = set(f["aceitas"])
        urls_emitidas = [ev.get("source_url") for ev in evidencias]
        nao_aceitas = [u for u in urls_emitidas if u not in aceitas]
        posicao = next((i + 1 for i, u in enumerate(ranking) if u in aceitas), None)
        d = {
            "chave": k, "tipo": f["tipo"], "texto": f["texto"], "aceitas": sorted(aceitas),
            "stance_esperada": f["stance_esperada"], "ranking_top5": ranking, "posicao_aceita": posicao,
            "evidencias": [{"source_url": ev.get("source_url"), "stance": ev.get("stance"),
                            "agency_verdict": ev.get("agency_verdict")} for ev in evidencias],
            "urls_nao_aceitas": nao_aceitas,
        }
        curto = f"[{k}] {f['texto'][:90]}"

        if f["tipo"] == "com_checagem":
            recall_total += 1
            d["no_top5"] = posicao is not None
            recall_ok += d["no_top5"]
            if not d["no_top5"]:
                erros.append(f"{curto}\n    Recall@5: nenhuma URL aceita no top 5")
            d["coberta"] = any(u in aceitas for u in urls_emitidas)
            cobertas += d["coberta"]
            if not d["coberta"]:
                erros.append(f"{curto}\n    Cobertura: o agente não emitiu a checagem esperada")

        if f["tipo"] in TIPOS_COM_URL:
            prevista = prever_stance(evidencias, aceitas)
            d["stance_prevista"] = prevista
            pares_stance.append((f["stance_esperada"], prevista))
            if prevista != f["stance_esperada"]:
                erros.append(f"{curto}\n    Stance: esperada {f['stance_esperada']}, prevista {prevista}")

        if f["tipo"] == "sem_checagem":
            total_sem += 1
            d["inventada"] = bool(evidencias)
            inventadas += d["inventada"]
            if evidencias:
                erros.append(f"{curto}\n    Evidência inventada: {', '.join(urls_emitidas)}")

        if nao_aceitas:
            errados_por_tipo[f["tipo"]] += len(nao_aceitas)
            frases_com_errado += 1
            if f["tipo"] != "sem_checagem":   # em sem_checagem já foi listada como inventada
                erros.append(f"{curto}\n    Casamento errado: {', '.join(nao_aceitas)}")
        detalhes.append(d)

    f1 = macro_f1(pares_stance)
    return {
        "n_frases": len(frases),
        "n_por_tipo": dict(Counter(f["tipo"] for f in frases)),
        "recall_at_5": _taxa(recall_ok, recall_total),
        "cobertura": _taxa(cobertas, recall_total),
        "macro_f1": f1,
        "matriz_confusao": matriz_confusao(pares_stance),
        "evidencia_inventada": _taxa(inventadas, total_sem),
        "casamento_errado": {"evidencias": sum(errados_por_tipo.values()), "frases": frases_com_errado,
                             "por_tipo": dict(errados_por_tipo)},
        "por_frase": detalhes,
        "erros": erros,
    }


# =============================================================================
# Execução: busca e agente (injetáveis, para testar sem modelos)
# =============================================================================

Buscar = Callable[[list[str]], list[list[str]]]
Agente = Callable[[list[dict]], dict]


def rodar_busca(textos: list[str]) -> list[list[str]]:
    """Para cada frase, as K primeiras checagens distintas, sem limiar e sem a etapa 2."""
    from src.agents.evidence import group_hits_by_url
    from src.retrieval.indice import search

    hits_por_frase = search(textos, k=K_BUSCA)
    return [[str(g[0].metadata.get("source_url")) for g in group_hits_by_url(hits, threshold=float("-inf"), max_urls=K)]
            for hits in hits_por_frase]


def rodar_agente(segmentos: list[dict]) -> dict:
    """Uma chamada ao agente real com as frases de uma entrada, como no grafo."""
    from src.agents.evidence import run

    return run(SimpleNamespace(segments=segmentos))


def executar_avaliacao(gold: dict, split: str = "todos", buscar: Buscar = rodar_busca,
                       agente: Agente = rodar_agente) -> tuple[dict, dict]:
    """Roda a busca (todas as frases de uma vez) e o agente (uma chamada por entrada)."""
    frases = selecionar_frases(gold, split)
    if not frases:
        raise ValueError(f"nenhuma frase no split '{split}'")

    t0 = time.perf_counter()
    rankings_lista = buscar([f["texto"] for f in frases])
    tempo_busca = time.perf_counter() - t0
    rankings = {f["chave"]: r for f, r in zip(frases, rankings_lista)}

    saidas: dict[str, list[dict]] = {f["chave"]: [] for f in frases}
    tempos_agente = []
    por_entrada: dict[str, list[dict]] = defaultdict(list)
    for f in frases:
        por_entrada[f["entrada_id"]].append(f)
    for entrada_id, fs in por_entrada.items():
        t0 = time.perf_counter()
        resultado = agente([{"id": f["frase_id"], "text": f["texto"]} for f in fs])
        tempos_agente.append(time.perf_counter() - t0)
        evidencias = resultado.get("evidence")
        if evidencias is None:
            raise RuntimeError(f"o agente falhou na entrada {entrada_id}: {resultado.get('warnings')}")
        for ev in evidencias:
            k = chave(entrada_id, ev.get("segment_id"))
            if k in saidas:
                saidas[k].append(ev)

    tempos = {
        "busca_s": round(tempo_busca, 3),
        "agente_primeira_entrada_s": round(tempos_agente[0], 3),
        "agente_demais_entradas_s": [round(t, 3) for t in tempos_agente[1:]],
        "observacao": "a busca inclui o carregamento do modelo de embeddings; a primeira entrada do agente, o do NLI",
    }
    return calcular_metricas(frases, rankings, saidas), tempos


# =============================================================================
# Sorteio de checagens para anotar (puro)
# =============================================================================

_VEREDITOS = {"falso": "contradiz", "verdadeiro": "apoia", "enganoso": "insuficiente", "outros": "insuficiente",
              "contradiz": "contradiz", "apoia": "apoia", "insuficiente": "insuficiente"}


def marcas_checagem(registro: dict) -> list[str]:
    """Alertas para quem vai anotar."""
    marcas = []
    url = registro.get("source_url", "")
    if _host(url) == AFP_HOST:
        marcas.append("só título no índice")
    if any(d in url for d in ESPELHOS):
        marcas.append("espelho (BOL/Acervo)")
    claim = (registro.get("claim_reviewed") or "").strip()
    if _EXPLICATIVO.search(claim) or _EXPLICATIVO.search(registro.get("review_title") or ""):
        marcas.append("explicativo? (não é alegação)")
    if _NEGATIVA.match(claim):
        marcas.append("alegação negativa: confira a stance")
    if len(claim) < MIN_ALEGACAO_CHARS:
        marcas.append("alegação curta ou truncada")
    elif len(claim) > MAX_ALEGACAO_CHARS or "?" in claim or re.search(r"https?://|www\.", claim):
        marcas.append("pergunta, link ou texto longo (não é uma alegação só)")
    return marcas


def checagem_utilizavel(registro: dict) -> bool:
    """Boa para virar frase do conjunto: alegação concreta, que não é guia, espelho nem negativa."""
    return not [m for m in marcas_checagem(registro) if m != "só título no índice"]


def sortear(corpus: dict[str, dict], n: int, excluir: Iterable[str] = (), veredito: str | None = None,
            agencia: str | None = None, semente: int = 1) -> list[dict]:
    """Amostra estratificada por agência e stance, reproduzível pela semente; sem espelhos (BOL, Acervo)."""
    excluir = set(excluir)
    stance = _VEREDITOS.get((veredito or "").lower()) if veredito else None
    if veredito and stance is None:
        raise ValueError(f"veredito desconhecido: {veredito!r} (use falso, verdadeiro ou enganoso)")
    estratos: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for url in sorted(corpus):
        r = corpus[url]
        s = stance_from_verdict(r.get("agency_verdict"))
        if url in excluir or (stance and s != stance) or any(d in url for d in ESPELHOS):
            continue  # espelhos repetem a checagem original
        if agencia and agencia.lower() not in f"{r.get('source_name', '')} {url}".lower():
            continue
        estratos[(r.get("source_name") or "", s)].append(r)

    rng = random.Random(semente)
    filas = []
    for k in sorted(estratos):
        itens = list(estratos[k])
        rng.shuffle(itens)
        filas.append(itens)
    rng.shuffle(filas)
    escolhidos = []
    while len(escolhidos) < n and any(filas):
        for fila in filas:
            if fila and len(escolhidos) < n:
                escolhidos.append(fila.pop())
    return escolhidos


def urls_do_gold(gold: dict) -> set[str]:
    return {u for f in selecionar_frases(gold) for u in f["aceitas"]}


# =============================================================================
# Esqueleto do conjunto e montagem dos textos (puros)
# =============================================================================

# Vagas do esqueleto: (tipo, stance esperada, quantidade, de onde vem a checagem).
# 36 frases = 12 entradas de 3; segue a tabela 2.2 do plano (±2 por linha).
VAGAS = (
    ("com_checagem", "contradiz", 11, "falso"),
    ("com_checagem", "contradiz", 2, "afp"),
    ("com_checagem", "insuficiente", 4, "enganoso"),
    ("com_checagem", "apoia", 2, "verdadeiro"),
    ("sem_checagem", None, 11, None),
    ("fato_parecido", None, 2, "nome_ou_doenca"),
    ("troca_numero", None, 2, "numero"),
    ("desmente", "apoia", 2, "falso"),
)
FRASES_POR_ENTRADA = 3

INSTRUCOES = {
    "com_checagem": "Parafraseie a alegação AFIRMANDO o boato, sem copiar palavras do título. Depois rode "
                    "diagnostico.py com a sua frase e acrescente em checagens_aceitas as outras URLs da MESMA alegação.",
    "sem_checagem": "Escreva um fato plausível, do mesmo universo de temas (saúde, política, STF), que nenhuma "
                    "checagem do corpus cubra. Confirme com diagnostico.py.",
    "fato_parecido": "Reescreva a alegação trocando um nome próprio ou a doença: outro fato, parecido. "
                     "checagens_aceitas fica vazia.",
    "troca_numero": "Reescreva a alegação trocando o número: outro fato, parecido. checagens_aceitas fica vazia.",
    "desmente": "Escreva uma frase que DESMENTE este boato (por exemplo, 'não é verdade que...'). "
                "A checagem apoia a frase.",
}
SEM_CHECAGEM_DISPONIVEL = ("Nenhuma checagem disponível para esta vaga: escolha uma com o sortear e preencha "
                           "checagens_aceitas, alegacao_original e stance_esperada.")


def _tem_numero(claim: str) -> bool:
    return any(t.isdigit() for t in tokenize(claim))


def _tem_nome_ou_doenca(claim: str) -> bool:
    return bool(name_groups(claim)) or any(t in DISEASES for t in tokenize(claim))


_ORIGENS: dict[str, Callable[[dict], bool]] = {
    "falso": lambda r: stance_from_verdict(r.get("agency_verdict")) == "contradiz" and _host(r["source_url"]) != AFP_HOST,
    "afp": lambda r: stance_from_verdict(r.get("agency_verdict")) == "contradiz" and _host(r["source_url"]) == AFP_HOST,
    "enganoso": lambda r: stance_from_verdict(r.get("agency_verdict")) == "insuficiente",
    "verdadeiro": lambda r: stance_from_verdict(r.get("agency_verdict")) == "apoia",
    "numero": lambda r: (stance_from_verdict(r.get("agency_verdict")) == "contradiz"
                         and _tem_numero(r.get("claim_reviewed") or "")),
    "nome_ou_doenca": lambda r: (stance_from_verdict(r.get("agency_verdict")) == "contradiz"
                                 and _tem_nome_ou_doenca(r.get("claim_reviewed") or "")),
}
# Origens mais restritas primeiro, para não gastarem as checagens das mais amplas.
_ORDEM_ORIGENS = ("verdadeiro", "afp", "numero", "nome_ou_doenca", "enganoso", "falso")


def _titulo_normalizado(registro: dict) -> str:
    return " ".join(normalize_text(registro.get("review_title") or "").split())


def indice_titulos(corpus: dict[str, dict]) -> dict[str, list[str]]:
    """Título normalizado -> URLs com esse título."""
    indice: dict[str, list[str]] = defaultdict(list)
    for u, r in corpus.items():
        titulo = _titulo_normalizado(r)
        if titulo:
            indice[titulo].append(u)
    return indice


def urls_mesma_checagem(corpus: dict[str, dict], url: str, indice: dict[str, list[str]] | None = None) -> list[str]:
    """A URL e os espelhos com o mesmo título (BOL x UOL, Acervo x Estadão), o original primeiro."""
    indice = indice_titulos(corpus) if indice is None else indice
    iguais = indice.get(_titulo_normalizado(corpus[url]), [])
    return sorted(set(iguais) | {url}, key=lambda u: (any(d in u for d in ESPELHOS), u != url, u))


def _vaga(tipo: str, stance: str | None, registro: dict | None, corpus: dict[str, dict],
          indice: dict[str, list[str]]) -> dict:
    frase = {"id": "", "texto": "", "tipo": tipo, "checagens_aceitas": [], "stance_esperada": None}
    if tipo != "sem_checagem":
        frase["alegacao_original"] = (registro or {}).get("claim_reviewed", "")
    frase["obs"] = ""
    if registro is None and tipo != "sem_checagem":
        frase["_instrucao"] = SEM_CHECAGEM_DISPONIVEL
        return frase
    if registro is not None:
        frase["_veredito"] = f"{registro.get('source_name')}: {display_verdict(registro.get('agency_verdict'))}"
        if tipo in TIPOS_COM_URL:
            frase["checagens_aceitas"] = urls_mesma_checagem(corpus, registro["source_url"], indice)
            frase["stance_esperada"] = stance
        else:
            frase["_base"] = registro["source_url"]   # de onde veio a troca (para a análise de erros)
    frase["_instrucao"] = INSTRUCOES[tipo]
    return frase


def gerar_esqueleto(corpus: dict[str, dict], excluir: Iterable[str] = (), semente: int = 1,
                    vagas: Sequence[tuple] = VAGAS) -> tuple[dict, list[str]]:
    """Monta as entradas com as checagens sorteadas e os campos de frase vazios.

    Devolve (gold, avisos). Cada checagem é usada uma vez só. As vagas de cada linha
    da tabela se alternam entre os splits, e as frases sem checagem completam as
    entradas, para que cada entrada tenha pelo menos uma frase ligada a uma checagem.
    """
    usados = set(excluir)
    indice = indice_titulos(corpus)
    utilizaveis = {u: r for u, r in corpus.items() if checagem_utilizavel(r)}
    escolhidos: dict[int, list[dict]] = {}
    avisos: list[str] = []
    ordem = sorted(range(len(vagas)), key=lambda i: _ORDEM_ORIGENS.index(vagas[i][3]) if vagas[i][3] else 99)
    for i in ordem:
        tipo, stance, qtd, origem = vagas[i]
        if origem is None:
            escolhidos[i] = [None] * qtd
            continue
        pool = {u: r for u, r in utilizaveis.items() if u not in usados and _ORIGENS[origem](r)}
        lista = sortear(pool, qtd, semente=semente + i)
        for r in lista:
            usados.update(urls_mesma_checagem(corpus, r["source_url"], indice))
        if len(lista) < qtd:
            avisos.append(f"{tipo} ({origem}): só {len(lista)} de {qtd} checagens disponíveis; complete à mão")
        escolhidos[i] = lista + [None] * (qtd - len(lista))

    # Distribui as vagas entre os splits, alternando dentro de cada linha da tabela.
    rng = random.Random(semente)
    por_split: dict[str, list[dict]] = {"teste": [], "calibracao": []}
    lado = 0
    for i, (tipo, stance, _qtd, _origem) in enumerate(vagas):
        for registro in escolhidos[i]:
            por_split[SPLITS[::-1][lado % 2]].append(_vaga(tipo, stance, registro, corpus, indice))
            lado += 1

    entradas_por_split = {}
    for split, vs in por_split.items():
        n_entradas = max(1, -(-len(vs) // FRASES_POR_ENTRADA))
        ligadas = [v for v in vs if v["tipo"] != "sem_checagem"]
        soltas = [v for v in vs if v["tipo"] == "sem_checagem"]
        rng.shuffle(ligadas)
        grupos: list[list[dict]] = [[] for _ in range(n_entradas)]
        for j, v in enumerate(ligadas + soltas):
            grupos[j % n_entradas].append(v)
        for g in grupos:
            rng.shuffle(g)
        entradas_por_split[split] = grupos

    entradas = []
    teste, calib = entradas_por_split["teste"], entradas_por_split["calibracao"]
    intercaladas = [(s, g) for par in zip(teste, calib) for s, g in zip(("teste", "calibracao"), par)]
    intercaladas += [("teste", g) for g in teste[len(calib):]] + [("calibracao", g) for g in calib[len(teste):]]
    for n, (split, grupo) in enumerate(intercaladas, 1):
        for k, frase in enumerate(grupo, 1):
            frase["id"] = f"s{k:02d}"
        entradas.append({"id": f"ev{n:02d}", "split": split, "anotador": "R2", "revisor": None,
                         "texto": "", "frases": grupo})

    gold = {
        "_sobre": ("Conjunto de avaliação do Agente de Evidências (parte de evidências do gold set, Manual §6.2). "
                   "Gerado pelo comando esqueleto: escreva o 'texto' de cada frase seguindo o '_instrucao', "
                   "rode 'completar' para montar o texto das entradas e 'validar' até sair sem erros. "
                   "Campos com '_' são só de apoio e o avaliar os ignora."),
        "versao": 1,
        "_gerado": {"comando": "esqueleto", "semente": semente, "data": datetime.now().date().isoformat()},
        "entradas": entradas,
    }
    return gold, avisos


_FIM_DE_FRASE = re.compile(r"[.!?…][\"'”’)]*$")


def completar(gold: dict, refazer: bool = False) -> tuple[int, list[str]]:
    """Monta o 'texto' de cada entrada juntando as frases e tira o '_instrucao' das frases escritas.

    Só monta entradas com todas as frases escritas; com refazer, remonta mesmo as que já têm texto.
    Devolve (entradas montadas, avisos).
    """
    montadas, avisos = 0, []
    for entrada in gold.get("entradas", []):
        frases = entrada.get("frases") or []
        for f in frases:
            if str(f.get("texto", "")).strip():
                f.pop("_instrucao", None)
                if not _FIM_DE_FRASE.search(f["texto"].strip()):
                    avisos.append(f"{chave(entrada.get('id'), f.get('id'))}: a frase não termina com pontuação; "
                                  f"o Ingestor pode juntá-la com a seguinte")
        pendentes = [f.get("id") for f in frases if not str(f.get("texto", "")).strip()]
        if pendentes:
            avisos.append(f"{entrada.get('id')}: frases ainda sem texto: {', '.join(pendentes)}")
            continue
        if refazer or not str(entrada.get("texto", "")).strip():
            entrada["texto"] = " ".join(f["texto"].strip() for f in frases)
            montadas += 1
    return montadas, avisos


# =============================================================================
# Saída no terminal e arquivo de resultado
# =============================================================================

def _num(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}".replace(".", ",")


def _status(nome: str, valor) -> str:
    if valor is None or nome not in METAS:
        return ""
    op, meta = METAS[nome]
    ok = valor >= meta if op == ">=" else valor <= meta if op == "<=" else valor == meta
    return "ok" if ok else "ABAIXO DA META" if op == ">=" else "ACIMA DA META"


def formatar_relatorio(m: dict, split: str) -> str:
    linhas = [f"Avaliação do Agente de Evidências | split: {split} | {m['n_frases']} frases {m['n_por_tipo']}", ""]
    linhas.append(f"{'Métrica':28s} {'Valor':>16s}   {'Meta':8s}")
    r, c, inv = m["recall_at_5"], m["cobertura"], m["evidencia_inventada"]
    f1, ce = m["macro_f1"], m["casamento_errado"]
    linhas += [
        f"{'Recall@5 (busca)':28s} {r['acertos']:>4d}/{r['total']:<4d}{_num(r['valor']):>7s}   ≥ 0,70    "
        f"{_status('recall_at_5', r['valor'])}",
        f"{'Cobertura (agente)':28s} {c['acertos']:>4d}/{c['total']:<4d}{_num(c['valor']):>7s}   —",
        f"{'Macro-F1 de stance':28s} {str(len(f1['classes_na_media'])) + ' classes':>9s}"
        f"{_num(f1['valor']):>7s}   ≥ 0,65    {_status('macro_f1', f1['valor'])}",
        f"{'Evidência inventada':28s} {inv['acertos']:>4d}/{inv['total']:<4d}{_num(inv['valor']):>7s}   ≤ 0,10    "
        f"{_status('evidencia_inventada', inv['valor'])}",
        f"{'Casamento errado':28s} {ce['evidencias']:>9d} ev.{'':4s}   = 0       "
        f"{_status('casamento_errado', ce['evidencias'])}",
    ]
    for a in f1["avisos"]:
        linhas.append(f"  aviso: {a}")
    linhas += ["", "Stance por classe (precisão / revocação / F1 / suporte):"]
    for cls, v in f1["por_classe"].items():
        linhas.append(f"  {cls:13s} {_num(v['precisao'])} / {_num(v['revocacao'])} / {_num(v['f1'])} / {v['suporte']}")
    linhas += ["", "Matriz de confusão (linha = esperada, coluna = prevista):",
               "  " + " " * 13 + "".join(f"{p:>14s}" for p in STANCES)]
    for e in STANCES:
        linhas.append(f"  {e:13s}" + "".join(f"{m['matriz_confusao'][e][p]:>14d}" for p in STANCES))
    if m["erros"]:
        linhas += ["", f"Erros ({len(m['erros'])}):"] + [f"  {e}" for e in m["erros"]]
    else:
        linhas += ["", "Erros: nenhum"]
    return "\n".join(linhas)


def configuracao_atual() -> dict:
    """Modelos, limiares e índice usados na rodada, para comparar rodadas e máquinas."""
    from importlib import metadata

    from src.retrieval.indice import get_collection

    def versao(pacote):
        try:
            return metadata.version(pacote)
        except metadata.PackageNotFoundError:
            return None

    def git(*args):
        try:
            return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                                  timeout=10).stdout.strip() or None
        except Exception:
            return None

    commit = git("rev-parse", "HEAD")
    return {
        "embedding_model": config.EMBEDDING_MODEL,
        "nli_model": config.NLI_MODEL,
        "device": config.pick_device(),
        "sim_threshold": config.SIM_THRESHOLD,
        "claim_match_min_prob": config.CLAIM_MATCH_MIN_PROB,
        "search_k": config.SEARCH_K,
        "claim_candidates": config.CLAIM_CANDIDATES,
        "max_evidence_per_segment": config.MAX_EVIDENCE_PER_SEGMENT,
        "recall_k": K,
        "recall_k_busca": K_BUSCA,
        "colecao": config.collection_name(),
        "trechos_no_indice": get_collection().count(),
        "chromadb": versao("chromadb"),
        "python": sys.version.split()[0],
        "git_commit": commit,
        "git_alteracoes_locais": bool(git("status", "--porcelain")) if commit else None,
    }


def caminho_resultado(pasta: Path, dia: str) -> Path:
    """eval/resultados/evidencias_<dia>.json; se já existir, _2, _3..."""
    caminho = pasta / f"evidencias_{dia}.json"
    n = 2
    while caminho.exists():
        caminho = pasta / f"evidencias_{dia}_{n}.json"
        n += 1
    return caminho


# =============================================================================
# Linha de comando
# =============================================================================

def _imprimir_problemas(problemas: list[Problema]) -> None:
    for nivel in ("erro", "aviso"):
        lista = [p for p in problemas if p.nivel == nivel]
        if lista:
            print(f"\n{nivel.upper()}S ({len(lista)}):")
            for p in lista:
                print(f"  [{p.onde}] {p.msg}")


def cmd_validar(args) -> int:
    if not args.claims.exists():
        print(f"Corpus não encontrado em {args.claims}. Rode antes collect_factcheck_api.py.")
        return 1
    gold = carregar_json(args.gold)
    problemas = validar_gold(gold, carregar_corpus(args.claims), carregar_pares_urls())
    frases = selecionar_frases(gold)
    entradas = gold.get("entradas", []) if isinstance(gold, dict) else []
    print(f"{args.gold}: {len(entradas)} entradas, {len(frases)} frases")
    print("Por split (entradas):", dict(Counter(e.get("split") for e in entradas if isinstance(e, dict))))
    print("Por tipo (frases):", dict(Counter(f["tipo"] for f in frases)))
    print("\nComposição (tabela 2.2 do plano):")
    contagem = contar_composicao(gold)
    for rotulo, alvo, minimo, maximo in COMPOSICAO:
        print(f"  {rotulo:36s} {contagem[rotulo]:3d}  (alvo {alvo})")
    _imprimir_problemas(problemas)
    erros = sum(p.nivel == "erro" for p in problemas)
    print(f"\n{'OK' if not erros else 'COM ERROS'}: {erros} erro(s), {len(problemas) - erros} aviso(s).")
    return 1 if erros else 0


def cmd_sortear(args) -> int:
    if not args.claims.exists():
        print(f"Corpus não encontrado em {args.claims}. Rode antes collect_factcheck_api.py.")
        return 1
    corpus = carregar_corpus(args.claims)
    excluir = carregar_pares_urls()
    if args.gold.exists():
        excluir |= urls_do_gold(carregar_json(args.gold))
    amostra = sortear(corpus, args.n, excluir, args.veredito, args.agencia, args.semente)
    print(f"{len(amostra)} checagens (semente {args.semente}; excluídas {len(excluir)} URLs do gold e dos 37 pares)\n")
    for i, r in enumerate(amostra, 1):
        stance = stance_from_verdict(r.get("agency_verdict"))
        marcas = marcas_checagem(r)
        print(f"{i:3d}. {r.get('source_name')} | {display_verdict(r.get('agency_verdict'))} -> {stance} | "
              f"{(r.get('review_date') or 'sem data')[:10]}" + (f" | {'; '.join(marcas)}" if marcas else ""))
        print(f"     alegação: {r.get('claim_reviewed')}")
        print(f"     título:   {r.get('review_title')}")
        print(f"     {r.get('source_url')}\n")
    return 0


def _gravar_json(caminho: Path, dados: dict) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
        f.write("\n")


def cmd_esqueleto(args) -> int:
    if not args.claims.exists():
        print(f"Corpus não encontrado em {args.claims}. Rode antes collect_factcheck_api.py.")
        return 1
    if args.saida.exists() and carregar_json(args.saida).get("entradas") and not args.forcar:
        print(f"{args.saida} já tem entradas. Use --forcar para sobrescrever (o conteúdo atual será perdido) "
              f"ou --saida para gravar em outro arquivo.")
        return 1
    corpus = carregar_corpus(args.claims)
    gold, avisos = gerar_esqueleto(corpus, carregar_pares_urls(), args.semente)
    _gravar_json(args.saida, gold)
    frases = selecionar_frases(gold)
    print(f"Esqueleto gravado em {_relativo(args.saida)}: {len(gold['entradas'])} entradas, {len(frases)} frases "
          f"(semente {args.semente}).")
    print("Por tipo:", dict(Counter(f["tipo"] for f in frases)))
    for a in avisos:
        print(f"  aviso: {a}")
    print("\nPróximos passos: escreva o 'texto' de cada frase (veja '_instrucao'), rode o diagnostico.py para "
          "achar as outras URLs aceitas, depois 'completar' e 'validar'.")
    return 0


def cmd_completar(args) -> int:
    gold = carregar_json(args.gold)
    montadas, avisos = completar(gold, args.refazer_textos)
    _gravar_json(args.gold, gold)
    print(f"{montadas} entrada(s) com o texto montado em {_relativo(args.gold)}.")
    for a in avisos:
        print(f"  {a}")
    return 0


def cmd_avaliar(args) -> int:
    gold = carregar_json(args.gold)
    if args.claims.exists():
        problemas = validar_gold(gold, carregar_corpus(args.claims), carregar_pares_urls())
        erros = [p for p in problemas if p.nivel == "erro"]
        if erros:
            _imprimir_problemas(erros)
            print("\nCorrija os erros (python eval/avaliar_evidencias.py validar) antes de avaliar.")
            return 1
    else:
        print(f"Aviso: corpus não encontrado em {args.claims}; avaliando sem validar o conjunto.")

    try:
        metricas, tempos = executar_avaliacao(gold, args.split)
    except ValueError as exc:
        print(f"Nada a avaliar: {exc}. Preencha {args.gold}.")
        return 1
    print(formatar_relatorio(metricas, args.split))
    print(f"\nTempos: busca {tempos['busca_s']} s; agente, 1ª entrada {tempos['agente_primeira_entrada_s']} s "
          f"(inclui carregar o NLI)")

    if args.salvar:
        configuracao = configuracao_atual()
        agora = datetime.now()
        RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)
        caminho = caminho_resultado(RESULTADOS_DIR, agora.strftime("%Y-%m-%d"))
        resultado = {
            "data": agora.isoformat(timespec="seconds"),
            "split": args.split,
            "gold": _relativo(args.gold),
            "gold_versao": gold.get("versao"),
            "configuracao": configuracao,
            "tempos": tempos,
            "metricas": metricas,
        }
        with caminho.open("w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        print(f"\nResultado salvo em {_relativo(caminho)}")
    return 0


def _relativo(caminho: Path) -> str:
    caminho = Path(caminho).resolve()
    return str(caminho.relative_to(REPO_ROOT)) if caminho.is_relative_to(REPO_ROOT) else str(caminho)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True)

    def comum(p):
        p.add_argument("--gold", type=Path, default=GOLD_PATH)
        p.add_argument("--claims", type=Path, default=config.RAW_DIR / "factcheck_api.jsonl")

    p = sub.add_parser("sortear", help="lista checagens do corpus para parafrasear")
    comum(p)
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--veredito", help="falso, verdadeiro ou enganoso (= qualquer outro rótulo)")
    p.add_argument("--agencia", help="trecho do nome ou do domínio da agência (ex.: AFP, aosfatos)")
    p.add_argument("--semente", type=int, default=1)
    p.set_defaults(func=cmd_sortear)

    p = sub.add_parser("esqueleto", help="gera as entradas com as checagens sorteadas e as frases em branco")
    comum(p)
    p.add_argument("--saida", type=Path, default=GOLD_PATH)
    p.add_argument("--semente", type=int, default=1)
    p.add_argument("--forcar", action="store_true", help="sobrescreve um arquivo que já tem entradas")
    p.set_defaults(func=cmd_esqueleto)

    p = sub.add_parser("completar", help="monta o texto das entradas a partir das frases escritas")
    comum(p)
    p.add_argument("--refazer-textos", action="store_true", help="remonta também as entradas que já têm texto")
    p.set_defaults(func=cmd_completar)

    p = sub.add_parser("validar", help="confere o conjunto de avaliação")
    comum(p)
    p.set_defaults(func=cmd_validar)

    p = sub.add_parser("avaliar", help="roda busca e agente reais e calcula as métricas")
    comum(p)
    p.add_argument("--split", choices=("todos", *SPLITS), default="todos")
    p.add_argument("--salvar", action="store_true", help="grava eval/resultados/evidencias_<data>.json")
    p.set_defaults(func=cmd_avaliar)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
