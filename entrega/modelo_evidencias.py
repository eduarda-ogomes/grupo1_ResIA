"""Modelo do Agente de Evidências, empacotado para a entrega.

O que é "o modelo" deste projeto
--------------------------------
O componente de IA avaliado quantitativamente é o Agente de Evidências: para cada
frase de uma notícia, ele procura checagens já publicadas sobre a MESMA alegação e
devolve a stance (apoia / contradiz / insuficiente), o título da checagem e o link.
É um pipeline de quatro passos (docs/agents/evidencias.md):

  1. busca densa: BGE-M3 + ChromaDB (índice de trechos de checagens);
  2. termos-chave: descarta a checagem que troca um nome, número ou doença da frase;
     ancoragem lexical: a frase precisa dividir uma palavra com a alegação ou o título;
  3. NLI (mDeBERTa-v3, XNLI): frase e alegação precisam se implicar numa direção;
  4. stance pelo veredito da agência.

Nenhuma rede foi re-treinada: os dois modelos neurais são pré-treinados e públicos.
O que foi AJUSTADO com dados, e que este objeto guarda, é:

  - os limiares de decisão (similaridade mínima e entailment mínimo), calibrados no
    split de calibração do gold set e medidos uma vez no split de teste;
  - o vocabulário de nomes próprios, extraído das alegações e títulos do corpus;
  - o mapeamento veredito -> stance;
  - a identificação exata dos pesos (repositório e revisão no Hugging Face) e do
    índice vetorial usado (coleção, número de trechos), que são grandes demais para
    o Git (~2,6 GB de pesos e ~1 GB de índice).

O arquivo .pkl é criado por entrega/treinar_modelo.py e carregado no notebook com
`ModeloEvidencias.carregar(...)`. Para unpickle, a raiz do repositório precisa estar
no sys.path (o objeto usa o código de src/).
"""

from __future__ import annotations

import importlib.util
import pickle
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
FORMATO = 1  # versão do formato do .pkl

# Hiperparâmetros que o objeto aplica em src/retrieval/config.py durante a execução.
HIPERPARAMETROS = ("SIM_THRESHOLD", "CLAIM_MATCH_MIN_PROB", "MIN_CONTENT_OVERLAP", "SEARCH_K",
                   "CLAIM_CANDIDATES", "MAX_EVIDENCE_PER_SEGMENT")


def carregar_avaliador():
    """eval/avaliar_evidencias.py como módulo (a pasta eval/ não é um pacote)."""
    caminho = REPO_ROOT / "eval" / "avaliar_evidencias.py"
    spec = importlib.util.spec_from_file_location("avaliar_evidencias", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def revisao_no_cache(repo_id: str) -> str | None:
    """Commit do modelo no cache local do Hugging Face (refs/main), sem acessar a rede."""
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
    except ImportError:
        return None
    ref = Path(HF_HUB_CACHE) / f"models--{repo_id.replace('/', '--')}" / "refs" / "main"
    return ref.read_text().strip() if ref.exists() else None


def resumo_metricas(m: dict) -> dict:
    """Só os números das métricas (sem a análise por frase), para guardar no .pkl."""
    return {k: v for k, v in m.items() if k not in ("por_frase", "erros")}


@dataclass
class ModeloEvidencias:
    """Pipeline de evidências com os parâmetros ajustados. Ver o docstring do módulo."""

    embedding_model: str
    nli_model: str
    hiperparametros: dict[str, float]
    vocabulario_nomes: frozenset[str]
    mapa_veredito: dict[str, frozenset[str]]
    embedding_revision: str | None = None
    nli_revision: str | None = None
    indice: dict[str, Any] = field(default_factory=dict)
    calibracao: list[dict] = field(default_factory=list)
    criterio_selecao: str = ""
    metricas: dict[str, dict] = field(default_factory=dict)
    criado_em: str = ""
    git_commit: str | None = None
    formato: int = FORMATO

    # --- Persistência ---------------------------------------------------------------

    def salvar(self, caminho: str | Path) -> Path:
        caminho = Path(caminho)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with caminho.open("wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)
        return caminho

    @classmethod
    def carregar(cls, caminho: str | Path) -> "ModeloEvidencias":
        with Path(caminho).open("rb") as f:
            modelo = pickle.load(f)
        if not isinstance(modelo, cls):
            raise TypeError(f"{caminho} não contém um ModeloEvidencias")
        if modelo.formato != FORMATO:
            raise ValueError(f"formato {modelo.formato} do .pkl; esperado {FORMATO}")
        return modelo

    def como_dict(self) -> dict:
        """Versão legível (JSON) do objeto, sem o vocabulário inteiro."""
        d = asdict(self)
        d["vocabulario_nomes"] = {"tamanho": len(self.vocabulario_nomes),
                                  "exemplos": sorted(self.vocabulario_nomes)[:20]}
        d["mapa_veredito"] = {k: sorted(v) for k, v in self.mapa_veredito.items()}
        return d

    # --- Execução ---------------------------------------------------------------------

    @contextmanager
    def aplicado(self) -> Iterator[None]:
        """Aplica os parâmetros do modelo no código de src/ e restaura os anteriores ao sair."""
        from src.retrieval import config, etapa2

        if config.EMBEDDING_MODEL != self.embedding_model or config.NLI_MODEL != self.nli_model:
            raise RuntimeError(
                f"o ambiente usa {config.EMBEDDING_MODEL} / {config.NLI_MODEL}, e o modelo foi ajustado com "
                f"{self.embedding_model} / {self.nli_model}. Desfaça EVIDENCE_EMBEDDING_MODEL e EVIDENCE_NLI_MODEL.")
        antes_config = {nome: getattr(config, nome) for nome in HIPERPARAMETROS}
        antes_vocab = (etapa2._name_vocabulary, etapa2._name_vocabulary_loaded)
        antes_mapa = (etapa2.CONTRADIZ, etapa2.APOIA)
        try:
            for nome, valor in self.hiperparametros.items():
                setattr(config, nome, valor)
            etapa2._name_vocabulary, etapa2._name_vocabulary_loaded = set(self.vocabulario_nomes), True
            etapa2.CONTRADIZ, etapa2.APOIA = set(self.mapa_veredito["contradiz"]), set(self.mapa_veredito["apoia"])
            yield
        finally:
            for nome, valor in antes_config.items():
                setattr(config, nome, valor)
            etapa2._name_vocabulary, etapa2._name_vocabulary_loaded = antes_vocab
            etapa2.CONTRADIZ, etapa2.APOIA = antes_mapa

    def _rodar(self, segmentos: list[dict]) -> dict:
        from src.agents.evidence import run

        with self.aplicado():
            return run(SimpleNamespace(segments=segmentos))

    def prever(self, frases: Sequence[str | dict]) -> list[dict]:
        """Evidências para as frases de UMA notícia (como no grafo: todas numa chamada).

        `frases`: textos (recebem ids s01, s02...) ou dicts {"id", "text"}.
        Devolve a lista de Evidence (dicts); levanta RuntimeError se o agente falhar.
        """
        segmentos = [f if isinstance(f, dict) else {"id": f"s{i:02d}", "text": f}
                     for i, f in enumerate(frases, start=1)]
        resultado = self._rodar(segmentos)
        if resultado.get("evidence") is None:
            raise RuntimeError(f"o agente falhou: {resultado.get('warnings')}")
        return resultado["evidence"]

    def buscar(self, frases: Sequence[str], k: int = 5) -> list[list[str]]:
        """Só a busca (passo 1): as k primeiras checagens distintas de cada frase, sem limiar.
        É o ranking usado no Recall@5."""
        avaliador = carregar_avaliador()
        with self.aplicado():
            rankings = avaliador.rodar_busca(list(frases))
        return [r[:k] for r in rankings]

    def avaliar(self, gold: dict, split: str = "teste") -> tuple[dict, dict]:
        """Métricas do gold set (eval/avaliar_evidencias.py) com os parâmetros deste modelo.

        split: "calibracao", "teste" ou "todos". Devolve (métricas, tempos).
        """
        avaliador = carregar_avaliador()
        with self.aplicado():
            return avaliador.executar_avaliacao(gold, split, buscar=avaliador.rodar_busca,
                                                agente=lambda segs: self._rodar(segs))

    def verificar_ambiente(self) -> dict:
        """Confere se o índice e os pesos disponíveis nesta máquina são os do modelo."""
        from src.retrieval import config

        info: dict[str, Any] = {"chroma_path": str(config.CHROMA_PATH), "colecao": config.collection_name(),
                                "dispositivo": config.pick_device()}
        try:
            from src.retrieval.indice import get_collection

            info["trechos_no_indice"] = get_collection().count()
            info["indice_ok"] = info["trechos_no_indice"] > 0
        except Exception as exc:  # índice ausente
            info["indice_ok"], info["erro_indice"] = False, f"{type(exc).__name__}: {exc}"
        for nome, repo, esperado in (("embedding", self.embedding_model, self.embedding_revision),
                                     ("nli", self.nli_model, self.nli_revision)):
            local = revisao_no_cache(repo)
            info[f"{nome}_revisao_local"] = local
            info[f"{nome}_revisao_igual"] = None if not (local and esperado) else local == esperado
        return info

    def resumo(self) -> str:
        h = self.hiperparametros
        linhas = [
            f"ModeloEvidencias (formato {self.formato}) criado em {self.criado_em}, commit {str(self.git_commit)[:7]}",
            f"  embeddings: {self.embedding_model} @ {str(self.embedding_revision)[:10]}",
            f"  NLI:        {self.nli_model} @ {str(self.nli_revision)[:10]}",
            f"  limiares:   similaridade >= {h['SIM_THRESHOLD']}, entailment >= {h['CLAIM_MATCH_MIN_PROB']}, "
            f"ancoragem >= {h['MIN_CONTENT_OVERLAP']} palavra(s)",
            f"  busca:      {h['SEARCH_K']} trechos por frase, {h['CLAIM_CANDIDATES']} candidatas, "
            f"até {h['MAX_EVIDENCE_PER_SEGMENT']} evidências por frase",
            f"  vocabulário de nomes: {len(self.vocabulario_nomes)} palavras",
            f"  índice:     {self.indice.get('colecao')} com {self.indice.get('trechos')} trechos",
        ]
        return "\n".join(linhas)
