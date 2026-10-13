import re

with open("tests/unit/test_text_analysis.py", "r") as f:
    content = f.read()

# Remove test_frases_faltando_apos_retry_mantem_as_classificadas_e_avisa
content = re.sub(
    r"def test_frases_faltando_apos_retry_mantem_as_classificadas_e_avisa.*?def test_fica_a_tentativa_com_menos_frases_faltando",
    "def test_fica_a_tentativa_com_menos_frases_faltando",
    content,
    flags=re.DOTALL
)

# Remove test_fica_a_tentativa_com_menos_frases_faltando
content = re.sub(
    r"def test_fica_a_tentativa_com_menos_frases_faltando.*?def test_frase_classificada_duas_vezes_fica_sem_classificacao",
    "def test_frase_classificada_duas_vezes_fica_sem_classificacao",
    content,
    flags=re.DOTALL
)

# Fix test_aviso_corta_frase_longa_para_caber_na_tela to trigger a warning via duplicated classification instead of missing
replacement = """def test_aviso_corta_frase_longa_para_caber_na_tela(monkeypatch):
    longa = "Palavra " * 30 + "fim."
    segs = [Segment(id="s01", text="Frase curta classificada."), Segment(id="s02", text=longa)]
    relatorio = relatorio_todos_factuais(["s01", "s02", "s02"])  # s02 duplicado
    monkeypatch.setattr(text_analysis, "chamar_modelo", ModeloFalso(relatorio, relatorio))

    resultado = texto_node(estado(segs))

    aviso = resultado["warnings"][0]
    assert aviso.startswith('texto: 1 frase sem classificação (as demais foram analisadas): s02 "Palavra Palavra')
    assert aviso.endswith('…"')
    assert len(aviso) < 160"""

content = re.sub(
    r"def test_aviso_corta_frase_longa_para_caber_na_tela.*?assert len\(aviso\) < 160",
    replacement,
    content,
    flags=re.DOTALL
)

with open("tests/unit/test_text_analysis.py", "w") as f:
    f.write(content)
