"""Tempo e memória do Agente de Evidências (Manual §5.2: < 2 GB para embeddings + NLI).

Mede, na máquina em que roda:
  1. tempo para carregar o modelo de embeddings e o NLI;
  2. memória dos pesos de cada modelo e do processo;
  3. tempo por notícia: as 12 entradas do conjunto de avaliação (3 frases cada) e uma
     notícia longa com as 36 frases juntas;
  4. com --comparar-fp16 (só com GPU): o NLI em fp32 e em fp16 nos 37 pares da etapa 2,
     para saber se as decisões mudam antes de ligar EVIDENCE_NLI_FP16.

Uso, a partir da raiz do repositório (precisa do índice e dos modelos):
    python eval/medir_recursos.py [--repeticoes 3] [--comparar-fp16] [--salvar]

Para medir com o NLI em fp16: defina EVIDENCE_NLI_FP16=1 antes de rodar.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "eval"))

from src.retrieval import config  # noqa: E402

PARES_PATH = REPO_ROOT / "data" / "corpus" / "pares_etapa2.json"
GB = 1024 ** 3


# --- Funções puras (testadas sem modelos) ----------------------------------------------

def bytes_dos_pesos(modelo) -> int:
    """Memória dos parâmetros e buffers de um modelo PyTorch."""
    tensores = [*modelo.parameters(), *modelo.buffers()]
    return sum(t.numel() * t.element_size() for t in tensores)


def percentis(valores: list[float]) -> dict:
    if not valores:
        return {"n": 0, "p50": None, "p95": None, "max": None}
    ordenados = sorted(valores)
    p95 = ordenados[min(len(ordenados) - 1, round(0.95 * (len(ordenados) - 1)))]
    return {"n": len(valores), "p50": round(statistics.median(ordenados), 3), "p95": round(p95, 3),
            "max": round(ordenados[-1], 3)}


def comparar_probabilidades(fp32: list[dict], fp16: list[dict], limiar: float) -> dict:
    """Diferença de entailment entre fp32 e fp16 e quantas decisões (>= limiar) mudam."""
    diffs = [abs(a["entailment"] - b["entailment"]) for a, b in zip(fp32, fp16)]
    mudam = [i for i, (a, b) in enumerate(zip(fp32, fp16))
             if (a["entailment"] >= limiar) != (b["entailment"] >= limiar)]
    nan = sum(1 for b in fp16 for v in b.values() if v != v)
    return {"pares": len(diffs), "dif_max": round(max(diffs), 4) if diffs else None,
            "dif_media": round(sum(diffs) / len(diffs), 4) if diffs else None,
            "decisoes_que_mudam": len(mudam), "indices": mudam, "valores_nan": nan}


# --- Medição ----------------------------------------------------------------------------

def memoria_do_processo() -> dict:
    """RSS do processo (psutil, se instalado; senão o pico pelo módulo resource) e memória da GPU."""
    info = {"rss_gb": None, "pico_rss_gb": None, "gpu_gb": None, "fonte": None}
    try:
        import psutil

        info["rss_gb"] = round(psutil.Process().memory_info().rss / GB, 2)
        info["fonte"] = "psutil"
    except ImportError:
        try:
            import resource

            pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            info["pico_rss_gb"] = round(pico / (GB if sys.platform == "darwin" else 1024 ** 2), 2)
            info["fonte"] = "resource (pico)"
        except ImportError:   # Windows sem psutil
            info["fonte"] = "indisponível: pip install psutil"
    try:
        import torch

        if torch.cuda.is_available():
            info["gpu_gb"] = round(torch.cuda.max_memory_allocated() / GB, 2)
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            info["gpu_gb"] = round(torch.mps.driver_allocated_memory() / GB, 2)
    except Exception:
        pass
    return info


def carregar_modelos() -> dict:
    from src.retrieval import indice, nli

    t0 = time.perf_counter()
    indice._embed(["aquecimento"], "query")
    t_emb = time.perf_counter() - t0
    t0 = time.perf_counter()
    nli.classify([("aquecimento", "aquecimento")])
    t_nli = time.perf_counter() - t0
    pesos_emb = bytes_dos_pesos(indice._model)
    pesos_nli = bytes_dos_pesos(nli.get_nli().model)
    return {
        "dispositivo": config.pick_device(),
        "nli_fp16": config.NLI_FP16,
        "carregar_embeddings_s": round(t_emb, 2),
        "carregar_nli_s": round(t_nli, 2),
        "pesos_embeddings_gb": round(pesos_emb / GB, 2),
        "pesos_nli_gb": round(pesos_nli / GB, 2),
        "pesos_total_gb": round((pesos_emb + pesos_nli) / GB, 2),
        "orcamento_gb": 2.0,
    }


def medir_latencia(repeticoes: int) -> dict:
    import avaliar_evidencias as av
    from src.agents.evidence import run

    gold = av.carregar_json(av.GOLD_PATH)
    frases = av.selecionar_frases(gold)
    por_entrada: list[float] = []
    for _ in range(repeticoes):
        _, tempos = av.rodar_agente_por_entrada(frases, av.rodar_agente)
        por_entrada += tempos
    longa = []
    segmentos = [{"id": f"s{i + 1:02d}", "text": f["texto"]} for i, f in enumerate(frases)]
    for _ in range(repeticoes):
        t0 = time.perf_counter()
        run(SimpleNamespace(segments=segmentos))
        longa.append(time.perf_counter() - t0)
    return {"noticia_3_frases_s": percentis(por_entrada),
            f"noticia_{len(segmentos)}_frases_s": percentis(longa)}


def comparar_fp16() -> dict:
    from src.retrieval import nli
    from src.retrieval.etapa2 import normalize_claim

    if config.pick_device() not in {"cuda", "mps"}:
        return {"pulado": "sem GPU: o fp16 só vale em cuda/mps"}
    pares = json.loads(PARES_PATH.read_text(encoding="utf-8"))["pares"]
    entradas = [p for par in pares for p in ((normalize_claim(par["alegacao"]), par["frase"]),
                                             (par["frase"], normalize_claim(par["alegacao"])))]
    fp32 = nli.classify(entradas, pipe=nli.make_nli_pipeline(fp16=False))
    fp16 = nli.classify(entradas, pipe=nli.make_nli_pipeline(fp16=True))
    return comparar_probabilidades(fp32, fp16, config.CLAIM_MATCH_MIN_PROB)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repeticoes", type=int, default=3)
    parser.add_argument("--comparar-fp16", action="store_true")
    parser.add_argument("--salvar", action="store_true", help="grava eval/resultados/recursos_<data>.json")
    args = parser.parse_args(argv)

    resultado = {"modelos": carregar_modelos()}
    resultado["memoria_apos_carregar"] = memoria_do_processo()
    resultado["latencia"] = medir_latencia(args.repeticoes)
    resultado["memoria_apos_rodar"] = memoria_do_processo()
    if args.comparar_fp16:
        resultado["fp32_x_fp16"] = comparar_fp16()

    m = resultado["modelos"]
    print(f"Dispositivo: {m['dispositivo']} | NLI em fp16: {m['nli_fp16']}")
    print(f"Carregar: embeddings {m['carregar_embeddings_s']} s, NLI {m['carregar_nli_s']} s")
    print(f"Pesos: embeddings {m['pesos_embeddings_gb']} GB + NLI {m['pesos_nli_gb']} GB = "
          f"{m['pesos_total_gb']} GB (orçamento {m['orcamento_gb']} GB: "
          f"{'ok' if m['pesos_total_gb'] <= m['orcamento_gb'] else 'ACIMA'})")
    print("Memória do processo:", resultado["memoria_apos_rodar"])
    for nome, p in resultado["latencia"].items():
        print(f"Tempo por {nome.replace('_s', '')}: p50 {p['p50']} s, p95 {p['p95']} s (n={p['n']})")
    if args.comparar_fp16:
        print("NLI fp32 x fp16:", resultado["fp32_x_fp16"])

    if args.salvar:
        import avaliar_evidencias as av

        agora = datetime.now()
        caminho = av.caminho_resultado(av.RESULTADOS_DIR, agora.strftime("%Y-%m-%d"), prefixo="recursos")
        resultado = {"data": agora.isoformat(timespec="seconds"), "configuracao": av.configuracao_atual(),
                     **resultado}
        av._gravar_json(caminho, resultado)
        print(f"Resultado salvo em {av._relativo(caminho)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
