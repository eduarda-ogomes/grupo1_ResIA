import pytest
from src.state import initial_state
from src.agents.synthesizer import run

def test_synthesizer_contract():
    # Arrange
    state = initial_state("O suco de limão cura tudo")
    
    # Act
    resultado = run(state)
    
    # Assert
    assert isinstance(resultado, dict), "O agente deve retornar um dicionário"
    assert "dossier" in resultado, "O dicionário deve conter a chave 'dossier'"
    assert isinstance(resultado["dossier"], str), "O dossier deve ser uma string"
    assert len(resultado["dossier"]) > 0, "O dossier não pode ser vazio"
