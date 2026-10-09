"""Popula o índice com as checagens novas: roda os três comandos do corpus em sequência.

1. collect_factcheck_api.py --max-age-days N   (checagens dos últimos N dias; as já coletadas são puladas)
2. fetch_articles.py --pular-sites ...          (texto das novas, sem os sites que bloqueiam o download)
3. build_index.py --apenas-novos                (embeddings só dos trechos que faltam no índice)

Para no primeiro comando que falhar. Todos podem ser repetidos sem duplicar nada.

A chave da API vem de FACTCHECK_API_KEY ou de uma linha FACTCHECK_API_KEY=... no .env da raiz.

Uso, a partir da raiz do repositório:
    python data/corpus/atualizar.py
    python data/corpus/atualizar.py --max-age-days 90
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent
REPO_ROOT = CORPUS_DIR.parents[1]
SITES_BLOQUEADOS = ["checamos.afp.com", "noticias.uol.com.br", "bol.uol.com.br"]  # ver evidencias_decisoes.md


def ler_chave_api(env_path: Path) -> str:
    """FACTCHECK_API_KEY do ambiente ou, se não houver, do .env."""
    chave = os.getenv("FACTCHECK_API_KEY", "").strip()
    if chave or not env_path.exists():
        return chave
    for linha in env_path.read_text(encoding="utf-8").splitlines():
        nome, sep, valor = linha.strip().removeprefix("export ").partition("=")
        if sep and nome.strip() == "FACTCHECK_API_KEY":
            return valor.strip().strip("\"'")
    return ""


def certificados_ssl() -> dict[str, str]:
    """SSL_CERT_FILE do certifi quando o Python não acha certificados próprios.

    O Python do instalador do python.org no macOS vem sem certificados (até alguém rodar o
    "Install Certificates.command"), e toda consulta HTTPS falha com CERTIFICATE_VERIFY_FAILED.
    """
    import ssl

    if os.getenv("SSL_CERT_FILE") or ssl.get_default_verify_paths().cafile:
        return {}
    try:
        import certifi
    except ImportError:
        return {}
    return {"SSL_CERT_FILE": certifi.where()}


def comandos(max_age_days: int) -> list[list[str]]:
    return [
        ["collect_factcheck_api.py", "--max-age-days", str(max_age_days)],
        ["fetch_articles.py", "--pular-sites", *SITES_BLOQUEADOS],
        ["build_index.py", "--apenas-novos"],
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max-age-days", type=int, default=30,
                        help="janela da coleta em dias (padrão: 30; 0 = sem limite, demora bem mais)")
    args = parser.parse_args()

    chave = ler_chave_api(REPO_ROOT / ".env")
    if not chave:
        print("Defina FACTCHECK_API_KEY no ambiente ou no .env da raiz.")
        return 1
    env = {**os.environ, "FACTCHECK_API_KEY": chave, **certificados_ssl()}

    for script, *opcoes in comandos(args.max_age_days):
        print(f"\n=== {script} {' '.join(opcoes)}", flush=True)
        resultado = subprocess.run([sys.executable, str(CORPUS_DIR / script), *opcoes], cwd=REPO_ROOT, env=env)
        if resultado.returncode != 0:
            print(f"\n{script} falhou (código {resultado.returncode}); os comandos seguintes não rodaram.")
            return resultado.returncode
    print("\nÍndice atualizado. Se data/corpus/nomes_proprios.txt mudou, faça o commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
