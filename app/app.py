import streamlit as st
from src.graph import sistema_multiagente

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

        if final_state:
            title = final_state.get('title', 'Sem Título')
            date = final_state.get('date')
            date_str = f" - Publicado em: {date}" if date else ""
            
            st.header(f"{title}")
            st.markdown(f"**Fonte/Ingestão**: {date_str}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Dossiê Sintetizado")
                dossier = final_state.get('dossier')
                if dossier:
                    st.info(f"**Resumo dos Fatos:**\n\n{dossier.content_summary}")
                    st.warning(f"**Enquadramento Geral:**\n\n{dossier.framing_summary}")
                
                st.subheader("Perguntas Socráticas")
                perguntas = final_state.get('socratic_questions', [])
                for q in perguntas:
                    st.markdown(f"- {q}")
            
            with col2:
                st.subheader("Evidências Analisadas")
                evidencias = final_state.get('evidence', [])
                for ev in evidencias:
                    cor = "green" if ev.stance == "apoia" else "red" if ev.stance == "contradiz" else "orange"
                    st.markdown(f"- **<span style='color:{cor}'>{ev.stance.upper()}</span>**: *\"{ev.excerpt}\"*", unsafe_allow_html=True)
                    
                st.subheader("Marcadores de Enquadramento")
                framing = final_state.get('framing')
                if framing and framing.markers:
                    for m in framing.markers:
                        st.markdown(f"**{m.type}**: *{m.exact_excerpt}*  \n_{m.short_explanation}_")
                    
                    st.write("**Tom Emocional Detectado:**")
                    st.json(framing.emotional_tone)
                else:
                    st.write("Nenhum marcador específico extraído.")
    else:
        st.warning("Por favor, insira um texto para analisar.")
