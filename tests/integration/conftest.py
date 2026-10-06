import pytest


@pytest.fixture(autouse=True)
def sem_modelos():
    """Os testes de integração usam os modelos reais: anula o bloqueio de tests/conftest.py."""
    yield
