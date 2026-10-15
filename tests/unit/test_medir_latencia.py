"""Funções do eval/medir_latencia.py (Manual §7.1: p50 e p95 ponta a ponta), sem modelos."""
import importlib.util
from pathlib import Path

import pytest

from src.pipeline.medicao import Execucao
from src.state import PipelineState, initial_state

_SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "medir_latencia.py"
_spec = importlib.util.spec_from_file_location("medir_latencia", _SCRIPT)
ml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ml)


def test_percentil_posto_mais_proximo():
    assert ml.percentil([5, 1, 3, 2, 4], 50) == 3
    assert ml.percentil(list(range(1, 21)), 95) == 19


def test_percentil_com_um_valor():
    assert ml.percentil([42.0], 50) == ml.percentil([42.0], 95) == 42.0


def test_percentil_sem_valores():
    with pytest.raises(ValueError, match="lista vazia"):
        ml.percentil([], 50)


def test_resumir_por_no_e_total():
    estado = PipelineState.model_validate(initial_state("Texto qualquer."))
    e1 = Execucao(estado, {}, {"ingestor": 1.0, "sintetizador": 3.0}, 10.0, None)
    e2 = Execucao(estado, {}, {"ingestor": 2.0, "sintetizador": 5.0}, 20.0, None)

    r = ml.resumir([e1, e2])

    assert r["total"] == {"p50": 10.0, "p95": 20.0, "n": 2}
    assert r["por_no"]["ingestor"] == {"p50": 1.0, "p95": 2.0, "n": 2}
    assert r["por_no"]["sintetizador"] == {"p50": 3.0, "p95": 5.0, "n": 2}


class GrafoContador:
    def __init__(self):
        self.chamadas = 0

    def stream(self, estado):
        self.chamadas += 1
        yield {"ingestor": {"segments": [{"id": "s01", "text": estado["raw_input"]}]}}
        yield {"sintetizador": {"dossier": "## Limites desta análise"}}


def test_aquecimento_nao_entra_na_medicao():
    grafo = GrafoContador()
    entradas = [{"nome": "a", "texto": "Uma frase."}, {"nome": "b", "texto": "Outra frase."}]

    medidas = ml.medir(grafo, entradas, repeticoes=2, aquecimento=1)

    assert grafo.chamadas == 5
    assert [nome for nome, _ in medidas] == ["a", "a", "b", "b"]
    assert all(isinstance(e, Execucao) for _, e in medidas)


def execucao(avisos):
    estado = PipelineState.model_validate(initial_state("Texto qualquer.", warnings=list(avisos)))
    return Execucao(estado, {}, {"ingestor": 1.0}, 10.0, None)


def test_resumir_conta_avisos_por_prefixo():
    execs = [execucao(avisos=["texto: saída inválida após 1 retry", "sintetizador: síntese livre reprovada"]),
             execucao(avisos=[]), execucao(avisos=["texto: timeout"])]
    assert ml.resumir(execs)["avisos"] == {"execucoes_com_aviso": 2, "por_prefixo": {"texto": 2, "sintetizador": 1}}


def test_entradas_padrao_tem_o_mamao_o_carrefour_e_a_noticia_longa():
    import json

    entradas = json.loads((_SCRIPT.parent / "entradas_latencia.json").read_text(encoding="utf-8"))
    assert [e["nome"] for e in entradas] == ["mamao_dengue", "carrefour_osasco", "noticia_longa"]
    assert all(e["texto"].strip() for e in entradas)


def test_noticia_longa_repete_tres_vezes_o_bloco_do_spec():
    import json

    raiz = _SCRIPT.parents[1]
    entradas = {e["nome"]: e["texto"] for e in
                json.loads((_SCRIPT.parent / "entradas_latencia.json").read_text(encoding="utf-8"))}
    desastre = json.loads((raiz / "tests/fixtures/bordas/texto_noticia_desastre.json").read_text(encoding="utf-8"))
    bloco = " ".join([entradas["mamao_dengue"], entradas["carrefour_osasco"],
                      *(s["text"] for s in desastre["segments"])])
    assert entradas["noticia_longa"] == " ".join([bloco] * 3)
