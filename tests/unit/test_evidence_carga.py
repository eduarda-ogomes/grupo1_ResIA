"""Os modelos do Agente de Evidências carregam uma vez só, mesmo com duas análises ao mesmo tempo.

Com o timeout por nó (src/protecao.py), uma análise abandonada pode continuar carregando o
BGE-M3 ou o mDeBERTa em segundo plano enquanto a seguinte começa: sem trava, cada uma
carregaria a sua cópia e a memória dobraria.
"""
import sys
import threading
import time
from types import SimpleNamespace

from src.retrieval import indice, nli


def _em_paralelo(fn, n=2):
    threads = [threading.Thread(target=fn) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)


def test_nli_carrega_uma_vez_com_duas_threads(monkeypatch):
    cargas = []

    def carga_lenta():
        cargas.append(1)
        time.sleep(0.2)
        return object()

    monkeypatch.setattr(nli, "_pipeline", None)
    monkeypatch.setattr(nli, "make_nli_pipeline", carga_lenta)

    _em_paralelo(nli.get_nli)

    assert len(cargas) == 1


def test_embeddings_carregam_uma_vez_com_duas_threads(monkeypatch):
    cargas = []

    class ModeloFalso:
        def __init__(self, nome, device=None):
            cargas.append(nome)
            time.sleep(0.2)

        def half(self):
            return self

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=ModeloFalso))
    monkeypatch.setattr(indice, "_model", None)
    monkeypatch.setattr(indice.config, "pick_device", lambda: "cpu")

    _em_paralelo(indice.get_embedding_model)

    assert len(cargas) == 1
