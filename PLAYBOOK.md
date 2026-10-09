# Playbook: Implantação e Execução do Dossiê IA & Evidências

Este playbook descreve o procedimento completo para configurar, executar e depurar o modelo de Inteligência Artificial e a aplicação do **Grupo 01** em um novo ambiente ou máquina local.

---

## 1. Visão Geral da Arquitetura
O sistema não utiliza chamadas para APIs externas pagas (como OpenAI ou Anthropic). Em vez disso, a arquitetura é baseada em:
*   **Modelo de Linguagem (LLM):** Executado 100% localmente através do **LM Studio** (via servidor compatível com a API da OpenAI).
*   **Orquestração:** **LangGraph** (fluxo multiagente com Agentes Ingestor, Texto, Evidência, Socrático e Sintetizador).
*   **Interface:** **Streamlit** (Front-end).
*   **Observabilidade:** **Arize Phoenix** (Rastreamento da cadeia de chamadas LangChain).

---

## 2. Pré-requisitos

Antes de iniciar, certifique-se de que a nova máquina possui:
1.  **Python 3.10 ou superior** instalado (`python --version`).
2.  **Git** instalado.
3.  **LM Studio** instalado (Faça o download em [lmstudio.ai](https://lmstudio.ai/)).

---

## 3. Configuração do Modelo de IA (LM Studio)

Como o motor do projeto roda localmente, o primeiro passo é subir o servidor de inferência.

1.  Abra o **LM Studio**.
2.  Na barra de busca, procure por **Qwen 2.5 7B Instruct** (ou outro modelo da família Llama-3/Qwen suportado).
3.  Faça o download da versão quantizada apropriada para a RAM da máquina (recomenda-se *Q4_K_M* ou *Q5_K_M* para computadores com 8GB/16GB de RAM).
4.  No LM Studio, vá até a aba **Local Server** (ícone de servidor no menu lateral ↔️).
5.  Selecione o modelo recém-baixado no topo da tela.
6.  Certifique-se de que a porta está configurada para **1234** (Padrão: `http://localhost:1234/v1`).
7.  Clique em **Start Server**.

> **Nota:** Se a sua máquina nomear o modelo de forma diferente no download (ex: `qwen2.5-7b-instruct-q4`), guarde esse nome, pois ele poderá ser passado como variável de ambiente.

---

## 4. Configuração do Ambiente de Desenvolvimento

No terminal do novo ambiente, siga os passos para isolar e instalar as dependências:

### 4.1. Clonar o Repositório
```bash
git clone https://github.com/eduarda-ogomes/grupo1_ResIA.git
cd grupo1_ResIA
```

### 4.2. Criar e Ativar Ambiente Virtual
No Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

No macOS/Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4.3. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 4.4. Modelos de NLP Tradicional
O projeto utiliza o spaCy para algumas rotinas de NLP. Baixe o pacote em português:
```bash
python -m spacy download pt_core_news_sm
```

---

## 5. Variáveis de Ambiente (Opcional)

Por padrão, a aplicação espera que o nome do modelo no LM Studio seja `qwen2.5-7b`. Se o nome diferir, configure a seguinte variável de ambiente no seu terminal antes de rodar o código:

*No macOS/Linux:*
```bash
export LLM_MODEL="qwen/qwen2.5-7b-instruct"
```
*No Windows (PowerShell):*
```powershell
$env:LLM_MODEL="qwen/qwen2.5-7b-instruct"
```

---

## 6. Execução

Você pode interagir com o modelo de duas maneiras:

### Opção A: Avaliação e Testes Diretos (Sem Interface)
Para avaliar exclusivamente o comportamento e as métricas do modelo LangGraph (Ideal para avaliação técnica):
1. Execute o Jupyter Notebook criado para avaliação:
```bash
jupyter notebook avaliacao_modelo.ipynb
```
2. Ou execute scripts de teste rodando o fluxo diretamente da pasta `src/`.

### Opção B: Interface de Usuário (Streamlit)
Para ver o sistema multiagente funcionando com a interface do usuário final:
```bash
streamlit run app/app.py
```
O navegador abrirá automaticamente em `http://localhost:8501`.

---

## 7. Rastreamento e Observabilidade (Tracing)

O projeto utiliza o **Arize Phoenix** para monitorar como a IA toma decisões e qual o tempo (latência) de cada agente.
Para visualizar os *traces* locais, execute em outro terminal:
```bash
python -m phoenix.server.main serve
```
Acesse `http://localhost:6006` no navegador para acompanhar o passo a passo da IA (prompts enviados e recebidos).

---

## 8. Troubleshooting (Erros Comuns)

| Erro / Comportamento | Causa Provável | Como Resolver |
| :--- | :--- | :--- |
| `ConnectionRefusedError` ou falha ao chamar modelo | O LM Studio não está rodando ou está na porta errada. | Abra o LM Studio, vá em "Local Server" e clique em "Start Server". Verifique se a porta é 1234. |
| Modelo retorna "Saída Inválida após 1 retry" | O LLM não seguiu a estrutura JSON exigida. | Utilize uma versão com maior capacidade (ex: de um modelo 3B para um 7B/8B). O Qwen 2.5 7B costuma ser excelente em JSON. |
| `Model not found` no terminal do LM Studio | O nome do modelo enviado pela API não bate com o arquivo carregado. | Exporte a variável `LLM_MODEL` com o nome exato que o LM Studio está exibindo. |
| Interface travada no carregamento | O servidor do LM Studio travou ou o *timeout* (120s) foi atingido. | Reinicie o servidor no LM Studio e atualize a página (`F5`). |
