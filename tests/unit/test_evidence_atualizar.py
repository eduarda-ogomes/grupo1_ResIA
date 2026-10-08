"""Testes do script que popula o índice com as checagens novas (sem rede, sem modelos).

    python -m pytest tests/unit/test_evidence_atualizar.py
"""

import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data" / "corpus"))

import atualizar  # noqa: E402


def test_roda_coleta_download_e_indexacao_nessa_ordem():
    scripts = [c[0] for c in atualizar.comandos(14)]
    assert scripts == ["collect_factcheck_api.py", "fetch_articles.py", "build_index.py"]
    assert all((atualizar.CORPUS_DIR / s).exists() for s in scripts)
    coleta, download, indice = atualizar.comandos(14)
    assert coleta[1:] == ["--max-age-days", "14"]
    assert "checamos.afp.com" in download and indice[1:] == ["--apenas-novos"]


def test_chave_do_ambiente_tem_prioridade(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("FACTCHECK_API_KEY=do-arquivo\n", encoding="utf-8")
    monkeypatch.setenv("FACTCHECK_API_KEY", "do-ambiente")
    assert atualizar.ler_chave_api(env) == "do-ambiente"


def test_chave_lida_do_env_com_aspas_e_export(tmp_path, monkeypatch):
    monkeypatch.delenv("FACTCHECK_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("# comentário\nOUTRA=1\nexport FACTCHECK_API_KEY=\"abc123\"\n", encoding="utf-8")
    assert atualizar.ler_chave_api(env) == "abc123"
    assert atualizar.ler_chave_api(tmp_path / "nao-existe") == ""


def test_usa_o_certifi_quando_o_python_nao_tem_certificados(monkeypatch):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    sem_cafile = ssl.DefaultVerifyPaths(None, None, "", "", "", "")
    monkeypatch.setattr(ssl, "get_default_verify_paths", lambda: sem_cafile)
    env = atualizar.certificados_ssl()
    assert env["SSL_CERT_FILE"].endswith("cacert.pem") and Path(env["SSL_CERT_FILE"]).exists()

    monkeypatch.setenv("SSL_CERT_FILE", "/meu/cert.pem")             # quem já definiu manda
    assert atualizar.certificados_ssl() == {}
