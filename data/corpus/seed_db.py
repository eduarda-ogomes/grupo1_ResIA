"""Índice mínimo para teste rápido, sem a coleta de checagens e sem chave de API.

Indexa apenas os dois trechos do exemplo de ponta a ponta da Seção 4.6 do
manual (caso do chá de folha de mamão e dengue), com as URLs e vereditos
citados lá. Serve para ver o agente rodando antes de o corpus real existir.

O claim_reviewed de cada checagem foi reconstruído a partir do endereço (slug)
da URL, porque a API não foi consultada para estas duas checagens. Com ele, o
modo "alegacao" (padrão) também pode ser testado aqui. Resultado provável: a
frase s02 casa com a checagem da Lupa; a s03 (plaquetas) provavelmente não casa
com nenhuma alegação e fica sem evidência, o comportamento conservador do modo.

ATENÇÃO: usa a mesma coleção do corpus real e a recria do zero (--reset
implícito). Depois de rodar este script, rode build_index.py de novo para
voltar ao corpus completo.

Uso, a partir da raiz do repositório:
    python data/corpus/seed_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.retrieval import config  # noqa: E402

SEED = [
    {
        "id": "seed-mamao-lupa-000",
        "text": "Não existe um tratamento específico para a dengue e as formas graves da doença.",
        "metadata": {
            "source_url": "https://www.agencialupa.org/jornalismo/2024/02/06/e-falso-que-cha-de-folha-de-mamao-cura-a-dengue-em-tres-dias/",
            "source_name": "Agência Lupa",
            "agency_verdict": "Falso",
            "review_date": "2024-02-06",
            "claim_reviewed": "Chá de folha de mamão cura a dengue em três dias",
            "chunk_index": 0,
            "describes_rumor": False,
        },
    },
    {
        "id": "seed-mamao-aosfatos-000",
        "text": "não comprovam que o tratamento seja eficaz em humanos",
        "metadata": {
            "source_url": "https://www.aosfatos.org/noticias/falso-cha-folha-mamao-dengue/",
            "source_name": "Aos Fatos",
            "agency_verdict": "Falso",
            "review_date": "2024-02-16",
            "claim_reviewed": "Chá de folha de mamão cura a dengue",
            "chunk_index": 0,
            "describes_rumor": False,
        },
    },
]


def seed_database() -> None:
    from src.retrieval.chroma_client import reset_collection
    from src.retrieval.embeddings import embed_passages

    collection = reset_collection()
    collection.add(
        ids=[r["id"] for r in SEED],
        documents=[r["text"] for r in SEED],
        metadatas=[r["metadata"] for r in SEED],
        embeddings=embed_passages([r["text"] for r in SEED]),
    )
    print(
        f"Coleção '{config.collection_name()}' recriada com {collection.count()} trechos "
        f"em {config.CHROMA_PATH}."
    )


if __name__ == "__main__":
    import argparse

    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    seed_database()
