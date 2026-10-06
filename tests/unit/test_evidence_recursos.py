"""Testes das funções puras do eval/medir_recursos.py (sem torch, sem modelos).

    python -m pytest tests/unit/test_evidence_recursos.py
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

_SCRIPT = Path(__file__).resolve().parents[2] / "eval" / "medir_recursos.py"
_spec = importlib.util.spec_from_file_location("medir_recursos", _SCRIPT)
mr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mr)


def _tensor(n, tamanho):
    return SimpleNamespace(numel=lambda: n, element_size=lambda: tamanho)


def test_bytes_dos_pesos_soma_parametros_e_buffers():
    modelo = SimpleNamespace(parameters=lambda: [_tensor(10, 4), _tensor(5, 2)], buffers=lambda: [_tensor(3, 4)])
    assert mr.bytes_dos_pesos(modelo) == 40 + 10 + 12


def test_percentis():
    p = mr.percentis([1.0, 2.0, 3.0, 4.0, 10.0])
    assert (p["n"], p["p50"], p["max"]) == (5, 3.0, 10.0)
    assert p["p95"] == 10.0
    assert mr.percentis([])["p50"] is None


def test_comparar_probabilidades_conta_decisoes_que_mudam_e_nan():
    fp32 = [{"entailment": 0.90}, {"entailment": 0.52}, {"entailment": 0.10}]
    fp16 = [{"entailment": 0.89}, {"entailment": 0.48}, {"entailment": float("nan")}]
    r = mr.comparar_probabilidades(fp32, fp16, 0.5)
    assert r["pares"] == 3 and r["decisoes_que_mudam"] == 1 and r["indices"] == [1]
    assert r["valores_nan"] == 1
