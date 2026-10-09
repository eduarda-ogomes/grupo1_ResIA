"""Testes do modelo empacotado da entrega (entrega/modelo_evidencias.py), sem modelos nem índice.

    python -m pytest tests/unit/test_entrega_modelo.py
"""

import pickle

import pytest

from entrega.modelo_evidencias import HIPERPARAMETROS, ModeloEvidencias
from src.agents import evidence as agent
from src.retrieval import config, etapa2
from tests.evidence_fakes import FakeClassify, FakeSearch, hit, patch_agent

FRASE = "O chá da folha de mamão cura a dengue em três dias."
ALEGACAO = "Chá de folha de mamão cura a dengue"
URL = "https://exemplo.org/checagem-mamao"


def _modelo(nli: float = 0.8, vocabulario=("lula", "mamao")) -> ModeloEvidencias:
    hiper = {nome: getattr(config, nome) for nome in HIPERPARAMETROS}
    hiper.update(SIM_THRESHOLD=0.5, CLAIM_MATCH_MIN_PROB=nli)
    return ModeloEvidencias(
        embedding_model=config.EMBEDDING_MODEL,
        nli_model=config.NLI_MODEL,
        hiperparametros=hiper,
        vocabulario_nomes=frozenset(vocabulario),
        mapa_veredito={"contradiz": frozenset({"falso"}), "apoia": frozenset({"verdadeiro"})},
    )


def _com_entailment(monkeypatch, valor: float):
    """Uma checagem da mesma alegação, com o entailment dado nas duas direções."""
    hits = [hit(ALEGACAO, 0.7, URL, verdict="Falso", claim_reviewed=ALEGACAO, review_title="É falso que chá cura dengue")]
    probs = {"entailment": valor, "neutral": 1 - valor, "contradiction": 0.0}
    patch_agent(monkeypatch, agent, FakeSearch({FRASE: hits}), FakeClassify({}, default=probs))


def test_pickle_ida_e_volta(tmp_path):
    modelo = _modelo()
    caminho = modelo.salvar(tmp_path / "modelo.pkl")
    carregado = ModeloEvidencias.carregar(caminho)
    assert carregado == modelo


def test_carregar_recusa_outro_objeto(tmp_path):
    caminho = tmp_path / "outro.pkl"
    caminho.write_bytes(pickle.dumps({"nao": "é modelo"}))
    with pytest.raises(TypeError):
        ModeloEvidencias.carregar(caminho)


def test_aplicado_troca_e_restaura_parametros():
    antes = {nome: getattr(config, nome) for nome in HIPERPARAMETROS}
    vocab_antes = etapa2._name_vocabulary
    modelo = _modelo(nli=0.42)
    with modelo.aplicado():
        assert config.CLAIM_MATCH_MIN_PROB == 0.42
        assert config.SIM_THRESHOLD == 0.5
        assert etapa2.load_name_vocabulary() == {"lula", "mamao"}
        assert etapa2.CONTRADIZ == {"falso"}
    assert {nome: getattr(config, nome) for nome in HIPERPARAMETROS} == antes
    assert etapa2._name_vocabulary is vocab_antes


def test_aplicado_restaura_mesmo_com_erro():
    antes = config.CLAIM_MATCH_MIN_PROB
    with pytest.raises(RuntimeError):
        with _modelo(nli=0.11).aplicado():
            raise RuntimeError("falha no meio")
    assert config.CLAIM_MATCH_MIN_PROB == antes


def test_aplicado_recusa_outro_modelo_de_embedding(monkeypatch):
    modelo = _modelo()  # ajustado com o embedding padrão
    monkeypatch.setattr(config, "EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
    with pytest.raises(RuntimeError, match="ajustado com"):
        with modelo.aplicado():
            pass


@pytest.mark.parametrize("limiar, esperadas", [(0.7, 1), (0.8, 0)])
def test_prever_usa_o_limiar_do_modelo(monkeypatch, limiar, esperadas):
    _com_entailment(monkeypatch, 0.75)
    evidencias = _modelo(nli=limiar).prever([FRASE])
    assert len(evidencias) == esperadas
    if esperadas:
        assert evidencias[0]["stance"] == "contradiz"
        assert evidencias[0]["source_url"] == URL


def test_prever_levanta_quando_o_agente_falha():
    # Sem dublês, o tests/conftest.py faz a busca recusar: o agente devolve evidence=None.
    with pytest.raises(RuntimeError, match="falhou"):
        _modelo().prever([FRASE])
