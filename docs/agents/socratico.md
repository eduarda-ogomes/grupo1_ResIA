# Agente Socrático

Dono: R4 · Branch: `AgenteSocratico`

## O que faz

O Agente Socrático formula de **2 a 3 perguntas reflexivas e incisivas** (maiêutica) sobre o texto da notícia (`clean_text`). O objetivo é preparar o usuário para ler a síntese e as evidências com pensamento crítico, estimulando-o a questionar a lógica interna do texto, premissas implícitas, generalizações ou saltos causais sem sustentação.

## Princípios e Regras (Manual §1.1, §4.4)

1. **Nunca emitir veredito**: Não classifica como "verdadeiro", "falso" ou "fake news".
2. **Pergunta não indutiva**: Não embute resposta nem induz conclusões (ex.: proscrito *"Você não acha suspeito que..."*).
3. **Não responder às próprias perguntas**: O papel é abrir a reflexão, não fechá-la.
4. **Ancoragem estrita no conteúdo**: Não inventa dados que não estejam presentes na notícia.
5. **Segurança contra Injeção**: O texto da notícia é recebido e tratado como dado delimitado (`<noticia>`), nunca como comando executável.

## Entrada e Saída

Lê `state.clean_text` e devolve um dicionário com `socratic_questions`:

```python
run(state) -> {
    "socratic_questions": [
        "Quais estudos o texto apresenta para sustentar a eficácia do tratamento?",
        "Quem é o especialista citado e quais são suas credenciais verificáveis?",
        "O que dizem as diretrizes oficiais de saúde sobre o tema?"
    ]
}
```

| Saída | Significado |
| --- | --- |
| `{"socratic_questions": [str, ...]}` | De 2 a 3 perguntas válidas, reflexivas e não indutivas. |
| `{"socratic_questions": None, "warnings": ["socrático: ..."]}` | Falha após 1 retry ou indisponibilidade do modelo (degradação graciosa, Manual §3.4 e §4.7). |

## Arquivos do Agente

| Arquivo | Descrição |
| --- | --- |
| `src/prompts/socratico_sistema.md` | System prompt de maiêutica versionado em arquivo (Manual §5.5). |
| `src/prompts/socratico_exemplos.json` | Exemplos few-shot para guiar a estrutura e tom do modelo. |
| `src/agents/socratic.py` | Implementação do agente, validação determinística de perguntas, detecção de perguntas indutivas e retentativa. |
| `src/stubs/socratic_stub.py` | Stub determinístico para testes e integração com o orquestrador. |
| `tests/unit/test_socratic.py` | Testes unitários de prompt, validação, casos de borda e retry. |
| `tests/contract/test_socratic_contract.py` | Testes de contrato do agente real e stub com o `PipelineState`. |

## Como rodar os testes

```bash
pytest tests/unit/test_socratic.py tests/contract/test_socratic_contract.py
```
