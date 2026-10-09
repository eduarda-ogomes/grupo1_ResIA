import sys
from pathlib import Path

# `streamlit run app/app.py` só coloca app/ no sys.path; adiciona a raiz para importar `src`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os

import streamlit as st
from src import medicao
from src.agents.dossie import escapar_markdown, tabela_frases
from src.graph import RAMOS, sistema_multiagente
from src.observabilidade import configurar_tracing
from src.state import PipelineState, initial_state


@st.cache_resource
def ligar_tracing() -> bool:
    """Liga o Phoenix uma vez por processo, quando PHOENIX_TRACING=1 (src/observabilidade.py)."""
    return configurar_tracing()


ligar_tracing()

st.set_page_config(page_title="Dossiê Multiagente", layout="wide")

st.title("Sistema Multiagente de Análise de Notícias")
st.markdown("Executa a análise em paralelo com LangGraph e modelos locais no LM Studio (`qwen2.5-7b`).")

# Visualização da Arquitetura (Grafo)
with st.expander("Visualizar Arquitetura do Sistema", expanded=False):
    st.markdown("O fluxograma abaixo é gerado dinamicamente a partir do LangGraph:")
    graph_mermaid = sistema_multiagente.get_graph().draw_mermaid()
    st.markdown(f"```mermaid\n{graph_mermaid}\n```")

text_input = st.text_area("Insira a URL ou o texto da notícia para análise:", height=150, 
                          placeholder="Cole aqui a URL de um site de notícias ou o texto bruto...")

if st.button("Analisar", type="primary"):
    if text_input.strip():
        estado_inicial = initial_state(text_input)

        # Acompanhamento do pipeline em tempo real: uma linha por nó, com o tempo desde o início
        with st.status("Processando pipeline multiagente...", expanded=True) as status:
            try:
                execucao = medicao.executar(
                    sistema_multiagente,
                    estado_inicial,
                    ao_terminar_no=lambda no, segundos: st.write(f"Nó concluído: **{no}** ({segundos:.1f} s)"),
                )
                status.update(label="Análise Concluída", state="complete", expanded=False)
            except Exception as e:
                status.update(label="Erro na execução", state="error")
                st.error(f"Erro ao executar o pipeline: {str(e)}")
                st.info("Dica: verifique se o LM Studio está rodando em localhost:1234 com o qwen2.5-7b carregado.")
                st.stop()

        # medicao.executar já devolve o estado validado no schema (objetos tipados)
        validated = execucao.estado
        final_state = {campo: getattr(validated, campo) for campo in PipelineState.model_fields}

        if final_state:
            title = final_state.get('title') or 'Sem título'
            published_at = final_state.get('published_at')

            st.header(escapar_markdown(title))
            if published_at:
                st.caption(f"Publicado em {published_at}")

            for aviso in final_state.get('warnings', []):
                st.warning(aviso, icon=":material/warning:")

            segments = final_state.get('segments', [])
            if not segments:
                st.error("O Ingestor não extraiu nenhum texto. Cole o texto da matéria manualmente.", icon=":material/error:")

            # As perguntas do Agente Socrático já vêm dentro do dossiê
            dossier = final_state.get('dossier')
            if dossier:
                st.markdown(dossier)

            if segments:
                with st.expander(f"Todas as frases analisadas ({len(segments)})"):
                    st.table(tabela_frases(validated))

            with st.expander("Detalhes técnicos"):
                nos = [n for n in ("ingestor", *RAMOS, "sintetizador") if n in execucao.duracao_por_no]
                st.table({
                    "nó": nos + ["total"],
                    "segundos": [round(execucao.duracao_por_no[n], 1) for n in nos] + [round(execucao.total, 1)],
                })
                if execucao.trace_id:
                    endereco = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006")
                    st.caption(f"Trace desta análise: `{execucao.trace_id}` · [Ver o trace no Phoenix]({endereco})")
    else:
        st.warning("Por favor, insira um texto para analisar.")
