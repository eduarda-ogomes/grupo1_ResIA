# Fixtures de exemplo

## Caso principal: `caso_mamao_dengue/`

Caso real de desinformação em saúde que circulou no início de 2024: vídeos e correntes afirmando que o chá de folha de mamão cura a dengue e aumenta as plaquetas.

Checagens usadas:
- Agência Lupa, 06/02/2024: https://www.agencialupa.org/jornalismo/2024/02/06/e-falso-que-cha-de-folha-de-mamao-cura-a-dengue-em-tres-dias/
- Aos Fatos, 16/02/2024: https://www.aosfatos.org/noticias/falso-cha-folha-mamao-dengue/

**Sobre o texto de entrada:** o conteúdo original era vídeo. O texto de `00_entrada.json` é uma reconstrução das alegações descritas nas checagens, escrita para este exemplo; não é transcrição do post original. Os campos `excerpt` são citações literais e curtas das checagens.

Os arquivos seguem o schema do State (Manual §3.3), em ordem de execução:

| Arquivo | Uso |
| --- | --- |
| `00_entrada.json` | Entrada do grafo |
| `01_ingestor_saida.json` | Saída do Ingestor; também é a entrada dos três ramos |
| `02_evidencias_saida.json` | Saída do Agente de Evidências |
| `03_texto_saida.json` | Saída do Agente de Texto |
| `04_socratico_saida.json` | Saída do Agente Socrático |
| `05_sintetizador_entrada.json` | State completo que chega ao Sintetizador |
| `05_sintetizador_saida.json` | Dossiê final |
| `05_sintetizador_guardrails.json` | Resultado esperado dos guardrails |

## Como usar

- **Stubs (`src/stubs/`):** cada stub pode simplesmente carregar o `0X_..._saida.json` do próprio agente e devolvê-lo.
- **Testes de contrato (`tests/contract/`):** alimente o agente com a entrada do arquivo anterior e valide a saída contra o schema Pydantic. O conteúdo exato não precisa bater para agentes com LLM; o formato, sim.

## Casos de borda: `bordas/`

Um arquivo por situação de falha ou borda, com a entrada, a saída esperada e o efeito no grafo. Os casos `evidencias_fato_parecido` e `sintetizador_parafrase` devem entrar no gold set.
