"""Latência do sistema (Manual §7.1): p50 e p95 por nó e ponta a ponta.

Roda o grafo real sobre as entradas de `eval/entradas_latencia.json`, descartando
as primeiras análises (aquecimento: carga do BGE-M3, do mDeBERTa e do modelo no
LM Studio), e grava o resultado em `eval/resultados/latencia_<data>.json`.

    LLM_MODEL=<id do LM Studio> python eval/medir_latencia.py --repeticoes 3

Com PHOENIX_TRACING=1 e o Phoenix no ar, cada análise também vira um trace.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from src.medicao import Execucao, executar  # noqa: E402
from src.state import initial_state  # noqa: E402

META_P50_S = 180  # Manual §7.1: p50 ponta a ponta abaixo de 3 min


def percentil(valores: list[float], p: float) -> float:
    """Percentil pelo posto mais próximo (nearest-rank)."""
    if not valores:
        raise ValueError("percentil de uma lista vazia")
    ordenados = sorted(valores)
    posto = max(1, math.ceil(p / 100 * len(ordenados)))
    return ordenados[posto - 1]


def _estatisticas(valores: list[float]) -> dict:
    return {"p50": percentil(valores, 50), "p95": percentil(valores, 95), "n": len(valores)}


def resumir(execucoes: list[Execucao]) -> dict:
    por_no: dict[str, list[float]] = {}
    for e in execucoes:
        for no, segundos in e.duracao_por_no.items():
            por_no.setdefault(no, []).append(segundos)
    return {
        "total": _estatisticas([e.total for e in execucoes]),
        "por_no": {no: _estatisticas(valores) for no, valores in por_no.items()},
    }


def medir(grafo, entradas: list[dict], repeticoes: int, aquecimento: int) -> list[tuple[str, Execucao]]:
    """Descarta `aquecimento` análises da primeira entrada; depois mede cada entrada `repeticoes` vezes."""
    for _ in range(aquecimento):
        executar(grafo, initial_state(entradas[0]["texto"]))
    return [(entrada["nome"], executar(grafo, initial_state(entrada["texto"])))
            for entrada in entradas for _ in range(repeticoes)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--entradas", type=Path, default=RAIZ / "eval" / "entradas_latencia.json")
    parser.add_argument("--repeticoes", type=int, default=3)
    parser.add_argument("--aquecimento", type=int, default=1)
    parser.add_argument("--saida", type=Path,
                        default=RAIZ / "eval" / "resultados" / f"latencia_{date.today().isoformat()}.json")
    args = parser.parse_args()

    from src.graph import sistema_multiagente
    from src.observabilidade import configurar_tracing
    from src.services.llm import LOCAL_MODEL

    configurar_tracing()
    entradas = json.loads(args.entradas.read_text(encoding="utf-8"))
    medidas = medir(sistema_multiagente, entradas, args.repeticoes, args.aquecimento)
    resumo = resumir([e for _, e in medidas])

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps({
        "data": date.today().isoformat(),
        "modelo": LOCAL_MODEL,
        "maquina": platform.platform(),
        "resumo": resumo,
        "execucoes": [{"entrada": nome, "total": e.total, "duracao_por_no": e.duracao_por_no,
                       "avisos": e.estado.warnings} for nome, e in medidas],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{'nó':<20}{'p50 (s)':>10}{'p95 (s)':>10}{'n':>5}")
    for no, est in [*resumo["por_no"].items(), ("total", resumo["total"])]:
        print(f"{no:<20}{est['p50']:>10.1f}{est['p95']:>10.1f}{est['n']:>5}")
    cumpre = "cumpre" if resumo["total"]["p50"] < META_P50_S else "NÃO cumpre"
    print(f"\np50 total {resumo['total']['p50']:.1f} s: {cumpre} a meta de {META_P50_S} s. Resultado em {args.saida}")


if __name__ == "__main__":
    main()
