"""Ajusta (calibra) o modelo do Agente de Evidências e salva o .pkl da entrega.

O "treino" deste modelo não mexe em pesos de rede neural (BGE-M3 e mDeBERTa são
pré-treinados). Ele ajusta, com dados, os parâmetros de decisão do pipeline:

  1. vocabulário de nomes próprios: palavras que o corpus de checagens usa como nome
     (gerado pelo data/corpus/build_index.py em data/corpus/nomes_proprios.txt);
  2. limiares: busca em grade de SIM_THRESHOLD x CLAIM_MATCH_MIN_PROB SÓ no split de
     calibração do gold set. Critério: menos casamentos errados -> mais cobertura ->
     centro do platô de empates (ver escolher_limiares);
  3. medição única no split de teste com os limiares escolhidos (e no conjunto todo,
     só como referência).

Uso, a partir da raiz do repositório (precisa do índice chroma_data/ e dos modelos):

    python entrega/treinar_modelo.py
    python entrega/treinar_modelo.py --sim 0.55 --nli 0.5 0.6 0.7 0.8 0.9

Saídas:
    entrega/modelo/modelo_evidencias.pkl        o modelo (objeto ModeloEvidencias)
    entrega/modelo/modelo_evidencias.json       o mesmo conteúdo, legível
    entrega/resultados/treino_<data>.json       grade de calibração e métricas completas
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from entrega.modelo_evidencias import (HIPERPARAMETROS, ModeloEvidencias, carregar_avaliador,  # noqa: E402
                                       resumo_metricas, revisao_no_cache)
from src.retrieval import config, etapa2  # noqa: E402

PASTA = Path(__file__).resolve().parent
CRITERIO = ("menos casamentos errados no split de calibração; empate: mais cobertura; "
            "empate: o centro do platô de limiares empatados (margem dos dois lados quando o índice muda)")


def escolher_limiares(linhas: list[dict]) -> dict:
    """Melhores combinações pelo critério do eval/avaliar_evidencias.py (menos casamentos errados,
    depois mais cobertura); entre as empatadas, a do meio.

    O `sugerir_limiares` do eval desempata pelo limiar mais baixo. Aqui o desempate é o centro do
    platô: em 01/10, no índice de 32 mil trechos, 0,7 casava errado onde 0,8 não; a borda de
    baixo do platô é a primeira a piorar quando o índice cresce.
    """
    def chave(l):
        m = l["metricas"]
        return m["casamento_errado"]["evidencias"], -m["cobertura"]["acertos"]

    melhor = min(chave(l) for l in linhas)
    empatadas = sorted((l for l in linhas if chave(l) == melhor),
                       key=lambda l: (l["sim_threshold"], l["claim_match_min_prob"]))
    return empatadas[(len(empatadas) - 1) // 2]


def _git_commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip() or None
    except Exception:
        return None


def _info_indice() -> dict:
    """Coleção e tamanho do índice usado (contados no próprio índice, não no manifest.json)."""
    from importlib import metadata

    from src.retrieval.indice import get_collection

    return {"colecao": config.collection_name(), "trechos": get_collection().count(),
            "chromadb": metadata.version("chromadb")}


def modelo_base(sim: float, nli: float) -> ModeloEvidencias:
    """Modelo com os parâmetros atuais de src/retrieval/config.py e os limiares dados."""
    vocabulario = etapa2.load_name_vocabulary()
    if not vocabulario:
        raise SystemExit(f"Vocabulário de nomes não encontrado em {etapa2.NAME_VOCABULARY_PATH}")
    hiper = {nome: getattr(config, nome) for nome in HIPERPARAMETROS}
    hiper.update(SIM_THRESHOLD=sim, CLAIM_MATCH_MIN_PROB=nli)
    return ModeloEvidencias(
        embedding_model=config.EMBEDDING_MODEL,
        nli_model=config.NLI_MODEL,
        hiperparametros=hiper,
        vocabulario_nomes=frozenset(vocabulario),
        mapa_veredito={"contradiz": frozenset(etapa2.CONTRADIZ), "apoia": frozenset(etapa2.APOIA)},
        embedding_revision=revisao_no_cache(config.EMBEDDING_MODEL),
        nli_revision=revisao_no_cache(config.NLI_MODEL),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sim", type=float, nargs="+", default=[config.SIM_THRESHOLD])
    parser.add_argument("--nli", type=float, nargs="+", default=[0.5, 0.6, 0.7, 0.8, 0.9])
    parser.add_argument("--gold", type=Path, default=REPO_ROOT / "data" / "gold" / "evidencias.json")
    parser.add_argument("--saida", type=Path, default=PASTA / "modelo" / "modelo_evidencias.pkl")
    args = parser.parse_args(argv)

    avaliador = carregar_avaliador()
    gold = avaliador.carregar_json(args.gold)

    # 1. Calibração: grade de limiares só no split de calibração.
    print(f"Calibração | SIM {args.sim} x NLI {args.nli} | split calibracao")
    provisorio = modelo_base(args.sim[0], args.nli[0])
    with provisorio.aplicado():
        linhas = avaliador.executar_calibracao(gold, args.sim, args.nli, "calibracao")
    print(avaliador.formatar_calibracao(linhas, "calibracao"))
    escolha = escolher_limiares(linhas)
    print(f"\nEscolha da entrega ({CRITERIO}): SIM {escolha['sim_threshold']}, "
          f"NLI {escolha['claim_match_min_prob']}")

    # 2. Modelo final com os limiares escolhidos.
    modelo = modelo_base(escolha["sim_threshold"], escolha["claim_match_min_prob"])
    modelo.calibracao = [{"sim_threshold": l["sim_threshold"], "claim_match_min_prob": l["claim_match_min_prob"],
                          **resumo_metricas(l["metricas"])} for l in linhas]
    modelo.criterio_selecao = CRITERIO
    modelo.indice = _info_indice()
    modelo.criado_em = datetime.now().isoformat(timespec="seconds")
    modelo.git_commit = _git_commit()

    # 3. Medição única no teste; o conjunto todo fica como referência.
    completas, tempos = {}, {}
    for split in ("teste", "calibracao", "todos"):
        completas[split], tempos[split] = modelo.avaliar(gold, split)
        modelo.metricas[split] = resumo_metricas(completas[split])
        print(f"\n{avaliador.formatar_relatorio(completas[split], split)}")

    modelo.salvar(args.saida)
    args.saida.with_suffix(".json").write_text(
        json.dumps(modelo.como_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    resultados = PASTA / "resultados"
    resultados.mkdir(parents=True, exist_ok=True)
    caminho = avaliador.caminho_resultado(resultados, datetime.now().strftime("%Y-%m-%d"), prefixo="treino")
    caminho.write_text(json.dumps({
        "criado_em": modelo.criado_em, "git_commit": modelo.git_commit, "criterio": CRITERIO,
        "escolha": {"sim_threshold": escolha["sim_threshold"],
                    "claim_match_min_prob": escolha["claim_match_min_prob"]},
        "indice": modelo.indice, "dispositivo": config.pick_device(),
        "calibracao": modelo.calibracao, "metricas": completas, "tempos": tempos,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{modelo.resumo()}\n\nModelo salvo em {args.saida.relative_to(REPO_ROOT)}"
          f"\nResultados em {caminho.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
