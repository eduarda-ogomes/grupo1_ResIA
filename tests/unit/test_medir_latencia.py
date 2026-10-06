"""Funções do eval/medir_latencia.py (Manual §7.1: p50 e p95 ponta a ponta), sem modelos."""
import importlib.util
from pathlib import Path

import pytest

from src.medicao import Execucao

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
    e1 = Execucao(None, {}, {"ingestor": 1.0, "sintetizador": 3.0}, 10.0, None)
    e2 = Execucao(None, {}, {"ingestor": 2.0, "sintetizador": 5.0}, 20.0, None)

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


def test_entradas_padrao_tem_o_mamao_e_o_carrefour():
    import json

    entradas = json.loads((_SCRIPT.parent / "entradas_latencia.json").read_text(encoding="utf-8"))
    assert [e["nome"] for e in entradas] == ["mamao_dengue", "carrefour_osasco"]
    assert all(e["texto"].strip() for e in entradas)
