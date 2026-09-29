import sys
from pathlib import Path

# `streamlit run app/app.py` só coloca app/ no sys.path; adiciona a raiz para importar `src`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from src.graph import sistema_multiagente
from src.state import PipelineState

st.set_page_config(page_title="Dossiê Multiagente", layout="wide")

st.title("Sistema Multiagente de Análise de Notícias")
st.markdown("Executa análise paralela com LangGraph e modelos locais via Ollama (`llama3.2`).")

# Visualização da Arquitetura (Grafo)
with st.expander("Visualizar Arquitetura do Sistema", expanded=False):
    st.markdown("O fluxograma abaixo é gerado dinamicamente a partir do LangGraph:")
    graph_mermaid = sistema_multiagente.get_graph().draw_mermaid()
    st.markdown(f"```mermaid\n{graph_mermaid}\n```")

text_input = st.text_area("Insira a URL ou o texto da notícia para análise:", height=150, 
                          placeholder="Cole aqui a URL de um site de notícias ou o texto bruto...")

if st.button("Analisar", type="primary"):
    if text_input.strip():
        final_state = {"raw_input": text_input}
        
        # Acompanhamento do pipeline em tempo real
        with st.status("Processando pipeline multiagente...", expanded=True) as status:
            try:
                # O método stream() permite ver o grafo funcionando passo a passo
                for event in sistema_multiagente.stream({"raw_input": text_input}):
                    for node_name, node_update in event.items():
                        st.write(f"Nó processado: **{node_name}**")
                        
                        # Atualiza nosso estado local para exibir depois
                        for key, value in node_update.items():
                            if key == "evidence":
                                final_state.setdefault("evidence", []).extend(value)
                            else:
                                final_state[key] = value
                
                status.update(label="Análise Concluída", state="complete", expanded=False)
            except Exception as e:
                status.update(label="Erro na execução", state="error")
                st.error(f"Erro ao executar o pipeline: {str(e)}")
                st.info("Dica: Verifique se o Ollama está rodando e se o modelo 'llama3.2' está instalado.")
                st.stop()

        # Os eventos do stream trazem dicts crus; valida no schema para exibir objetos tipados
        validated = PipelineState.model_validate(final_state)
        final_state = {campo: getattr(validated, campo) for campo in PipelineState.model_fields}

        if final_state:
            title = final_state.get('title') or 'Sem título'
            published_at = final_state.get('published_at')
            date_str = f" - Publicado em: {published_at}" if published_at else ""

            st.header(f"{title}")
            st.markdown(f"**Fonte/Ingestão**: {date_str}")

            for aviso in final_state.get('warnings', []):
                st.warning(aviso, icon=":material/warning:")

            segments = final_state.get('segments', [])
            if segments:
                with st.expander(f"Frases segmentadas pelo Ingestor ({len(segments)})"):
                    st.table({"id": [s.id for s in segments], "frase": [s.text for s in segments]})
            else:
                st.error("O Ingestor não extraiu nenhum texto. Cole o texto da matéria manualmente.", icon=":material/error:")

            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Dossiê Sintetizado")
                dossier = final_state.get('dossier')
                if dossier:
                    st.write(dossier)
                
                st.subheader("Perguntas Socráticas")
                perguntas = final_state.get('socratic_questions', [])
                for q in perguntas:
                    st.markdown(f"- {q}")
            
            with col2:
                st.subheader("Evidências Analisadas")
                evidencias = final_state.get('evidence', [])
                for ev in evidencias:
                    # 'ev' is a Pydantic object
                    cor = "green" if ev.stance == "apoia" else "red" if ev.stance == "contradiz" else "orange"
                    st.markdown(f"- **<span style='color:{cor}'>{ev.stance.upper()}</span>**: *\"{ev.excerpt}\"*", unsafe_allow_html=True)
                    
                st.subheader("Marcadores de Texto (Viés/Falácia)")
                text_report = final_state.get('text_report')
                if text_report and text_report.markers:
                    for m in text_report.markers:
                        st.markdown(f"**{m.type}**: *{m.excerpt}*  \n_{m.explanation}_")
                else:
                    st.write("Nenhum marcador específico extraído.")
    else:
        st.warning("Por favor, insira um texto para analisar.")
