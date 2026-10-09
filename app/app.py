import sys
from pathlib import Path
import base64
import html
import os
import textwrap

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import streamlit.components.v1 as components
from src import medicao
from src.agents.dossie import tabela_frases
from src.graph import RAMOS, sistema_multiagente
from src.observabilidade import configurar_tracing
from src.state import PipelineState, initial_state

@st.cache_resource
def ligar_tracing() -> bool:
    return configurar_tracing()

ligar_tracing()

def render_html(html_str):
    st.markdown(textwrap.dedent(html_str), unsafe_allow_html=True)

st.set_page_config(page_title="Dossiê IA & Evidências", layout="wide", initial_sidebar_state="collapsed")

def get_base64_image(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except Exception:
        return ""

logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
logo_b64 = get_base64_image(logo_path)

# Captura a página e seção atuais pela URL (Query Params)
curr_page = st.query_params.get("page", "home")
curr_section = st.query_params.get("section", "home")

# ==================== CUSTOM CSS ====================
render_html("""
<style>
header {display: none !important;}
#MainMenu {display: none !important;}
footer {display: none !important;}

.block-container {
    padding-top: 1rem !important;
    padding-bottom: 0rem !important;
}

@import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400..700;1,400..700&family=Inter:wght@300;400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #FAFAFA;
    color: #111;
}

h1, h2, h3, h4, h5, .serif-title {
    font-family: 'Lora', serif !important;
    color: #111111;
}

h1 {
    font-size: 3.5rem !important;
    font-weight: 700 !important;
    line-height: 1.1 !important;
    letter-spacing: -1px;
}

.stButton>button {
    background-color: #7C2128 !important;
    color: white !important;
    border-radius: 4px !important;
    padding: 0.6rem 1.2rem !important;
    border: none !important;
    font-weight: 500 !important;
    transition: all 0.2s ease;
}
.stButton>button:hover {
    background-color: #5A161C !important;
}

.stTextArea>div>div>textarea {
    border-radius: 8px;
    border: 1px solid #EAEAEA;
    padding: 1rem;
    font-size: 1.1rem;
}

.custom-card {
    border: 1px solid #EAEAEA;
    border-radius: 8px;
    padding: 40px;
    background-color: #FFFFFF;
    box-shadow: 0 4px 12px rgba(0,0,0,0.02);
    height: 100%;
    margin-bottom: 2rem;
}

/* NAVBAR AJUSTADA (Mais baixa e com menos espaçamento) */
.header-nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #F0F0F0;
    padding-bottom: 0.8rem;
    padding-top: 0.5rem;
    margin-bottom: 2.5rem;
    background-color: #FFF;
    padding-left: 2rem;
    padding-right: 2rem;
    border-radius: 0 0 12px 12px;
}

.tag-badge {
    font-size: 0.75rem; 
    font-weight: 600; 
    color: #555; 
    border: 1px solid #EAEAEA; 
    padding: 4px 12px; 
    border-radius: 20px;
    letter-spacing: 0.5px;
}

.stats-bar {
    display: flex;
    justify-content: space-around;
    text-align: center;
    padding: 3rem 0;
    border-top: 1px solid #EAEAEA;
    border-bottom: 1px solid #EAEAEA;
    margin: 4rem 0;
    background-color: #FFF;
}
.stats-bar h2 {
    font-size: 2.5rem !important;
    margin: 0;
    font-family: 'Inter', sans-serif !important;
}
.stats-bar p {
    font-size: 0.85rem;
    color: #666;
    margin: 0;
}

.four-sections-card {
    border: 1px solid #EAEAEA;
    border-radius: 8px;
    padding: 1.5rem;
    background-color: #FFF;
    margin-bottom: 1rem;
    display: flex;
    align-items: flex-start;
}

.four-sections-number {
    color: #7C2128;
    font-family: 'Lora', serif;
    font-size: 1.5rem;
    font-weight: 700;
    border-bottom: 2px solid #7C2128;
    margin-right: 1.5rem;
    padding-bottom: 4px;
}

.filosofia-section {
    text-align: center;
    margin-top: 5rem;
    padding-top: 3rem;
    background-color: #FFF;
}

.exemplo-box {
    background-color: #FFF;
    border: 1px solid #EAEAEA;
    border-radius: 12px;
    padding: 2rem;
    margin-top: 2rem;
}

/* RODAPÉ AJUSTADO (Mais baixo) */
.footer-container {
    border-top: 1px solid #EAEAEA;
    margin-top: 8rem;
    padding-top: 3rem;
    padding-bottom: 1rem;
    background-color: #FFF;
}

/* LINKS COMO BOTÕES HTML */
.btn-outline-html {
    display: inline-block;
    padding: 0.55rem 1.2rem;
    background-color: transparent;
    border: 1px solid #CCC;
    border-radius: 4px;
    font-weight: 500;
    color: #333;
    text-decoration: none;
    text-align: center;
    transition: all 0.2s ease;
}
.btn-outline-html:hover {
    border-color: #999;
    color: #111;
}

.btn-primary-html {
    display: inline-block;
    background-color: #7C2128;
    color: white !important;
    border-radius: 4px;
    padding: 0.6rem 1.2rem;
    border: none;
    font-weight: 500;
    text-decoration: none;
    text-align: center;
    transition: all 0.2s ease;
}
.btn-primary-html:hover {
    background-color: #5A161C;
}
</style>
""")

def get_nav_link(text, page, section):
    is_active = (curr_page == page and curr_section == section)
    style = "background-color: #7C2128; color: white; padding: 6px 12px; border-radius: 4px; text-decoration: none; font-weight: 500;" if is_active else "color: #111; padding: 6px 12px; text-decoration: none; font-weight: 500;"
    href = f"/?page={page}&section={section}#{section}" if section else f"/?page={page}"
    return f'<a href="{href}" style="{style}" target="_self">{text}</a>'

def render_header(show_nav=True):
    img_tag = f'<img src="data:image/png;base64,{logo_b64}" width="140">' if logo_b64 else '<strong style="color: #7C2128;">Dossiê</strong>'
    
    # Adicionando o botão Analisar notícia na Navbar
    btn_analisar_nav = '<a href="/?page=analisar" style="background-color: #7C2128; color: white; padding: 8px 16px; border-radius: 4px; text-decoration: none; font-weight: 500; margin-left: 15px;" target="_self">Analisar notícia</a>'
    
    nav_links = ""
    if show_nav:
        nav_links = f"""
<div style="display:flex; gap: 15px; font-size: 0.95rem; font-weight:500; align-items:center;">
{get_nav_link('Como funciona', 'home', 'como_funciona')}
{get_nav_link('Método', 'home', 'metodo')}
{get_nav_link('Exemplos', 'home', 'exemplos')}
{btn_analisar_nav}
</div>
        """
    else:
        nav_links = f"""
<div style="display:flex; gap: 15px; font-size: 0.95rem; font-weight:500; align-items:center;">
<a href="/?page=home" style="color: #111; padding: 6px 12px; text-decoration: none; font-weight: 500;" target="_self">← Voltar ao Início</a>
</div>
        """

    render_html(f"""
<div class="header-nav">
<div style="display:flex; align-items:center;">
<a href="/?page=home" target="_self">{img_tag}</a>
</div>
{nav_links}
</div>
    """)

def render_footer():
    img_tag = f'<img src="data:image/png;base64,{logo_b64}" width="100">' if logo_b64 else '<strong>Dossiê</strong>'
    render_html(f"""
<div class="footer-container">
<div style="display:flex; justify-content: space-between; max-width: 1200px; margin: 0 auto; padding: 0 2rem;">
<div style="flex: 2; padding-right: 2rem;">
{img_tag}
<p style="color:#555; font-size:0.9rem; margin-top:1rem; max-width:300px;">
Uma ferramenta de leitura crítica que organiza evidências e perguntas para você investigar antes de compartilhar.
</p>
</div>
<div style="flex: 1;">
<strong style="font-size:0.75rem; letter-spacing:1px; color:#111;">PRODUTO</strong>
<ul style="list-style:none; padding:0; color:#555; font-size:0.9rem; line-height:2.2; margin-top:1rem;">
<li><a href="/?page=home&section=como_funciona#como_funciona" target="_self" style="color:#555; text-decoration:none;">Como funciona</a></li>
<li><a href="/?page=analisar" target="_self" style="color:#555; text-decoration:none;">Analisar notícia</a></li>
<li><a href="/?page=home&section=exemplos#exemplos" target="_self" style="color:#555; text-decoration:none;">Ver exemplo</a></li>
<li><a href="/?page=home&section=metodo#metodo" target="_self" style="color:#555; text-decoration:none;">Método</a></li>
</ul>
</div>
<div style="flex: 1;">
<strong style="font-size:0.75rem; letter-spacing:1px; color:#111;">MÉTODO</strong>
<ul style="list-style:none; padding:0; color:#555; font-size:0.9rem; line-height:2.2; margin-top:1rem;">
<li>O que verificamos</li>
<li>Limites da IA</li>
<li>Fontes primárias</li>
<li>Transparência</li>
</ul>
</div>
<div style="flex: 1;">
<strong style="font-size:0.75rem; letter-spacing:1px; color:#111;">PRINCÍPIOS</strong>
<ul style="list-style:none; padding:0; color:#555; font-size:0.9rem; line-height:2.2; margin-top:1rem;">
<li>Sem veredito binário</li>
<li>Baseado em evidências</li>
<li>Pensamento crítico</li>
<li>Autonomia do leitor</li>
</ul>
</div>
</div>
<hr style="border:none; border-top:1px solid #EAEAEA; margin: 2rem auto 1.5rem auto; max-width:1200px;">
<div style="display:flex; justify-content:space-between; max-width:1200px; margin: 0 auto; padding: 0 2rem; color:#666; font-size:0.8rem;">
<span>© 2026 Dossiê · Todos os direitos reservados</span>
<span>Evidências para investigar. Perguntas para pensar.</span>
</div>
</div>
    """)

def render_home():
    render_header(show_nav=True)
    
    col_text, col_img = st.columns([1.1, 1])
    
    with col_text:
        render_html("<span class='tag-badge'>🔴 FERRAMENTA DE LEITURA CRÍTICA</span>")
        render_html("<h1 style='margin-top: 1.5rem;'>Antes de concluir,<br>investigue.</h1>")
        render_html("<p style='font-size: 1.2rem; color: #444; margin-top: 1rem; margin-bottom: 2.5rem; line-height:1.5; font-weight:300;'>O Dossiê analisa notícias suspeitas e organiza evidências, argumentos e perguntas para você pensar antes de compartilhar.</p>")
        
        btn_col1, btn_col2, btn_col3 = st.columns([1.6, 1.2, 2])
        with btn_col1:
            st.markdown('<a href="/?page=analisar" class="btn-primary-html" target="_self" style="width:100%; display:block;">Analisar uma notícia →</a>', unsafe_allow_html=True)
        with btn_col2:
            st.markdown('<a href="/?page=home&section=exemplos#exemplos" class="btn-outline-html" target="_self" style="width:100%; display:block;">Ver exemplo</a>', unsafe_allow_html=True)
            
        render_html("""
<div style='display:flex; gap: 20px; margin-top: 2.5rem; font-size: 0.85rem; color: #555; font-weight:500;'>
<span><span style="color:#7C2128;">○</span> Sem veredito binário</span>
<span><span style="color:#7C2128;">○</span> Baseado em evidências</span>
<span><span style="color:#7C2128;">○</span> Estimula pensamento crítico</span>
</div>
        """)
        
    with col_img:
        img_tag = f'<img src="data:image/png;base64,{logo_b64}" width="280">' if logo_b64 else '<h1 style="color:#7C2128; font-size: 8rem !important; margin:0; line-height:1;">D</h1>'
        render_html(f"""
<div class="custom-card" style="display:flex; flex-direction:column; justify-content:center; align-items:center; min-height: 400px; text-align:center;">
{img_tag}
<hr style="width:100%; border:none; border-top:1px solid #EAEAEA; margin-top: 3rem; margin-bottom: 1.5rem;">
<div style="display:flex; justify-content:space-between; width:100%; text-align:left;">
<div><strong style="font-size:0.65rem; color:#666;">ANÁLISE GERADA</strong><br><span style="font-size:0.95rem; font-family: Lora, serif; color:#111;">4 dimensões investigativas</span></div>
<div><strong style="font-size:0.65rem; color:#666;">MÉTODO</strong><br><span style="font-size:0.95rem; font-family: Lora, serif; color:#111;">IA & Evidências</span></div>
</div>
</div>
        """)

    render_html("""
<div class="stats-bar">
<div><h2>4</h2><p>Seções de análise</p></div>
<div style="border-left:1px solid #EAEAEA; padding-left:4rem;"><h2>100%</h2><p>Transparência metodológica</p></div>
<div style="border-left:1px solid #EAEAEA; padding-left:4rem;"><h2>0</h2><p>Vereditos automáticos</p></div>
<div style="border-left:1px solid #EAEAEA; padding-left:4rem;"><h2>∞</h2><p>Perguntas para investigar</p></div>
</div>
    """)
    
    # âncora invisível para o Como Funciona
    render_html("<div id='como_funciona'></div>")
    render_html("<div style='text-align:center; padding: 2rem 0;'><strong style='font-size:0.75rem; letter-spacing:1px; color:#111;'>COMO FUNCIONA</strong><h2 style='margin-top:0.5rem; font-size:2.5rem !important;'>Um método claro para leitura crítica</h2><p style='color:#555; font-size:1.1rem; margin-bottom: 3rem;'>O Dossiê não diz se uma notícia é verdadeira ou falsa. Ele organiza o que você precisa investigar.</p></div>")
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_html("<div class='custom-card' style='padding:24px;'><h2 style='margin-top:0; font-size:2rem !important; color:#111;'>01</h2><strong style='font-size:1.1rem; font-family:Lora, serif;'>Cole a notícia</strong><p style='font-size:0.9rem; color:#555; margin-top:1rem; line-height:1.5;'>Insira o texto completo ou a URL da notícia que você quer investigar.</p></div>")
    with c2:
        render_html("<div class='custom-card' style='padding:24px;'><h2 style='margin-top:0; font-size:2rem !important; color:#111;'>02</h2><strong style='font-size:1.1rem; font-family:Lora, serif;'>Gere o Dossiê</strong><p style='font-size:0.9rem; color:#555; margin-top:1rem; line-height:1.5;'>A IA analisa o texto e organiza evidências a verificar, recursos argumentativos e perguntas relevantes.</p></div>")
    with c3:
        render_html("<div class='custom-card' style='padding:24px;'><h2 style='margin-top:0; font-size:2rem !important; color:#111;'>03</h2><strong style='font-size:1.1rem; font-family:Lora, serif;'>Investigue com método</strong><p style='font-size:0.9rem; color:#555; margin-top:1rem; line-height:1.5;'>Leia o relatório, consulte as fontes indicadas e responda as perguntas de reflexão antes de decidir.</p></div>")
    with c4:
        render_html("<div class='custom-card' style='padding:24px;'><h2 style='margin-top:0; font-size:2rem !important; color:#111;'>04</h2><strong style='font-size:1.1rem; font-family:Lora, serif;'>Forme sua opinião</strong><p style='font-size:0.9rem; color:#555; margin-top:1rem; line-height:1.5;'>O Dossiê apoia sua leitura crítica. O julgamento final é sempre seu, não da máquina.</p></div>")

    render_html("<br><br><br>")
    
    # âncora invisível para o Método
    render_html("<div id='metodo'></div>")
    col_q1, col_q2 = st.columns([1, 1.2])
    with col_q1:
        render_html("""
<div style="padding-right: 2rem; margin-top: 2rem;">
<strong style="font-size:0.75rem; letter-spacing:1px; color:#111;">O RELATÓRIO DOSSIÊ</strong>
<h2 style="font-size: 2.5rem !important; margin: 1rem 0;">Quatro seções para investigar com profundidade</h2>
<p style="color:#555; font-size: 1.1rem; line-height: 1.6; margin-bottom: 2rem;">Cada relatório é estruturado em dimensões complementares: o que já foi checado, como o texto tenta convencer, que perguntas fazer e quais os limites da análise automática.</p>
<a href="/?page=home&section=exemplos#exemplos" class="btn-primary-html" target="_self">Ver exemplo completo</a>
</div>
        """)
    with col_q2:
        render_html("""
<div class="four-sections-card">
<div class="four-sections-number">01</div>
<div>
<strong style="font-size:1.1rem; font-family:Lora, serif;">O que as checagens dizem</strong>
<p style="font-size:0.9rem; color:#555; margin-top:0.5rem; margin-bottom:0;">Evidências públicas, agências e fontes a consultar sobre a afirmação central.</p>
</div>
</div>
<div class="four-sections-card">
<div class="four-sections-number">02</div>
<div>
<strong style="font-size:1.1rem; font-family:Lora, serif;">Como o texto argumenta</strong>
<p style="font-size:0.9rem; color:#555; margin-top:0.5rem; margin-bottom:0;">Recursos retóricos identificados: generalizações, apelos à autoridade, linguagem de certeza.</p>
</div>
</div>
<div class="four-sections-card">
<div class="four-sections-number">03</div>
<div>
<strong style="font-size:1.1rem; font-family:Lora, serif;">Perguntas para pensar antes de decidir</strong>
<p style="font-size:0.9rem; color:#555; margin-top:0.5rem; margin-bottom:0;">Questões de reflexão personalizadas para orientar sua investigação independente.</p>
</div>
</div>
<div class="four-sections-card">
<div class="four-sections-number" style="border-bottom:none; color:#EAEAEA; font-size:1.5rem; display:flex; align-items:center; justify-content:center;">ⓘ</div>
<div>
<strong style="font-size:1.1rem; font-family:Lora, serif;">Limites desta análise</strong>
<p style="font-size:0.9rem; color:#555; margin-top:0.5rem; margin-bottom:0;">Transparência sobre o que a IA pode e não pode fazer. A decisão final é sempre sua.</p>
</div>
</div>
        """)

    # âncora para os Exemplos e Filosofia
    render_html("<div id='exemplos'></div>")
    render_html("""
<div class="filosofia-section">
<strong style="font-size:0.75rem; letter-spacing:1px; color:#111;">NOSSA FILOSOFIA</strong>
<h2 style="font-size:2.8rem !important; margin: 1rem auto; max-width: 800px;">Informação sem contexto não é conhecimento.</h2>
<p style="color:#555; font-size:1.1rem; max-width:700px; margin: 0 auto 4rem auto;">O Dossiê não emite vereditos. Não diz "verdadeiro" ou "falso". Ele organiza o que você precisa investigar para formar sua própria opinião com mais rigor e menos pressa.</p>

<div style="display:flex; justify-content: space-between; text-align:left; max-width: 1000px; margin: 0 auto;">
<div style="flex:1; padding-right:2rem;">
<h3 style="font-size:1.8rem !important; margin-bottom:1rem;">Sem veredito</h3>
<p style="color:#555; font-size:0.95rem; line-height:1.6;">Análise binária simplifica demais. O Dossiê mostra o que investigar, não o que concluir.</p>
</div>
<div style="flex:1; padding-right:2rem;">
<h3 style="font-size:1.8rem !important; margin-bottom:1rem;">Com evidências</h3>
<p style="color:#555; font-size:0.95rem; line-height:1.6;">Cada ponto levantado é rastreável. Você pode conferir, questionar e aprofundar.</p>
</div>
<div style="flex:1;">
<h3 style="font-size:1.8rem !important; margin-bottom:1rem;">Para qualquer pessoa</h3>
<p style="color:#555; font-size:0.95rem; line-height:1.6;">Não é preciso ser jornalista. O método é acessível a qualquer leitor que queira pensar melhor.</p>
</div>
</div>
</div>
    """)


    render_footer()

    # Injetor de JS para forçar o scroll após o Streamlit terminar de renderizar a página
    if curr_page == 'home' and curr_section != 'home':
        components.html(f'''
            <script>
                setTimeout(() => {{
                    const el = window.parent.document.getElementById('{curr_section}');
                    if (el) {{
                        el.scrollIntoView({{behavior: 'smooth', block: 'start'}});
                    }}
                }}, 400); // Aguarda a tela desenhar para rolar
            </script>
        ''', height=0)

def render_analisar():
    render_header(show_nav=False)
        
    render_html("""
<div style='text-align:center; margin-bottom: 3rem;'>
<h1 style='font-size: 3rem !important;'>Antes de concluir, investigue.</h1>
<p style='font-size:1.2rem; color:#444; font-weight:300;'>Examine evidências, reconheça argumentos e encontre perguntas melhores.</p>
</div>
    """)
    
    render_html("""
<div style="background-color: #FFFFFF; border: 1px solid #EAEAEA; border-radius: 12px; padding: 2.5rem; margin-bottom: 3rem; box-shadow: 0 4px 12px rgba(0,0,0,0.02);">
<strong style="font-size:1.1rem; color:#111;">Notícia para análise</strong><br>
<span style="font-size:0.95rem; color:#666; margin-bottom: 1.5rem; display:inline-block;">Cole o texto completo ou a URL de uma notícia que você quer investigar.</span>
    """)
    
    text_input = st.text_area("Texto", height=150, label_visibility="collapsed", placeholder="Cole o texto ou URL da notícia suspeita...")
    
    col_vazia, col_texto, col_btn = st.columns([1.5, 1.5, 1])
    with col_texto:
        render_html("<p style='font-size:0.85rem; color:#666; margin-top:0.8rem;'>Nenhuma notícia enviada. Veja um exemplo ilustrativo abaixo.</p>")
    with col_btn:
        analisar_clicado = st.button("Gerar Dossiê →", type="primary", use_container_width=True)
        
    render_html("</div>")
    
    if analisar_clicado and text_input.strip():
        # Fluxo Real com LangGraph
        estado_inicial = initial_state(text_input)
        with st.status("Processando leitura crítica (consultando Inteligência Artificial)...", expanded=True) as status:
            try:
                execucao = medicao.executar(
                    sistema_multiagente,
                    estado_inicial,
                    ao_terminar_no=lambda no, segundos: st.write(f"Concluído: **{no}** ({segundos:.1f} s)"),
                )
                status.update(label="Análise Concluída", state="complete", expanded=False)
            except Exception as e:
                status.update(label="Erro na execução", state="error")
                st.error(f"Erro ao executar o pipeline: {str(e)}")
                st.stop()
        
        validated = execucao.estado
        final_state = {campo: getattr(validated, campo) for campo in PipelineState.model_fields}
        
        if final_state:
            title = final_state.get('title') or 'Sem título'
            published_at = final_state.get('published_at')
            data_html = (
                f'<p style="font-size:0.9rem; color:#666; margin:-1.5rem 0 2rem 0;">Publicado em {html.escape(str(published_at))}</p>'
                if published_at else ""
            )

            render_html(f"""
<div class="exemplo-box">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
<span style="font-size:0.75rem; font-weight:700; color:#7C2128; letter-spacing:1px;">🔴 RELATÓRIO DE EVIDÊNCIAS</span>
<div>
<span style="font-size:0.7rem; border:1px solid #EAEAEA; padding:4px 8px; border-radius:4px; margin-right:8px;">Análise Real</span>
</div>
</div>
<h2 style="font-size:2.2rem !important; margin-bottom:2rem;">"{html.escape(title)}"</h2>
{data_html}
<div style="background-color:#FAFAFA; border:1px solid #EAEAEA; padding:1.5rem; border-radius:8px; display:flex; gap:15px; align-items:flex-start; margin-bottom:2rem;">
<span style="color:#666; font-size:1.2rem;">ⓘ</span>
<span style="font-size:0.9rem; color:#555;">Esta análise foi gerada por inteligência artificial com base no texto fornecido. O Dossiê organiza o que falta verificar; não determina se a notícia é verdadeira ou falsa.</span>
</div>
</div>
            """)

            for aviso in final_state.get('warnings', []):
                st.warning(aviso, icon=":material/warning:")

            segments = final_state.get('segments', [])
            if not segments:
                st.error("O Ingestor não extraiu nenhum texto. Cole o texto da matéria manualmente.", icon=":material/error:")

            # O dossiê é Markdown (seções, listas, links): renderiza fora do HTML para o Markdown valer.
            # As perguntas do Agente Socrático já vêm dentro do dossiê
            dossier = final_state.get('dossier')
            if dossier:
                with st.container(border=True):
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
        # Exemplo Ilustrativo Estático
        render_html("""
<div class="exemplo-box">
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
<span style="font-size:0.75rem; font-weight:700; color:#7C2128; letter-spacing:1px;">🔴 RELATÓRIO DE EVIDÊNCIAS</span>
<div>
<span style="font-size:0.7rem; border:1px solid #EAEAEA; padding:4px 8px; border-radius:4px; margin-right:8px; color:#555;">Exemplo ilustrativo</span>
<span style="font-size:0.7rem; border:1px solid #EAEAEA; padding:4px 8px; border-radius:4px; color:#555;">Texto fictício</span>
</div>
</div>
<h2 style="font-size:2.2rem !important; margin-bottom:2rem;">"Novo estudo prova que tomar café dobra a concentração de qualquer pessoa."</h2>
<div style="background-color:#FAFAFA; border:1px solid #EAEAEA; padding:1.5rem; border-radius:8px; display:flex; gap:15px; align-items:flex-start; margin-bottom:2rem;">
<span style="color:#666; font-size:1.2rem;">ⓘ</span>
<span style="font-size:0.9rem; color:#555;">Demonstração baseada apenas na frase acima, sem consulta a fontes externas. Este dossiê organiza o que falta verificar; não determina se a notícia é verdadeira ou falsa.</span>
</div>

<div style="display:flex; align-items:flex-start; margin-bottom:3rem; border-bottom:1px solid #EAEAEA; padding-bottom:3rem;">
<div class="four-sections-number" style="margin-right:2rem; font-size:1.2rem; min-width:40px;">01</div>
<div>
<h3 style="margin-top:0; font-size:1.6rem !important; margin-bottom:1.5rem;">O que as checagens dizem</h3>

<div style="display:flex; gap:15px; margin-bottom:1.5rem;">
<span style="color:#7C2128;">📄</span>
<div>
<strong style="font-size:0.95rem; color:#111;">Estudo original não identificado</strong>
<p style="font-size:0.9rem; color:#555; margin:0;">A frase não informa autoria, publicação ou link. É preciso localizar o estudo antes de avaliar a conclusão.</p>
</div>
</div>

<div style="display:flex; gap:15px; margin-bottom:1.5rem;">
<span style="color:#7C2128;">🎯</span>
<div>
<strong style="font-size:0.95rem; color:#111;">Método e contexto não apresentados</strong>
<p style="font-size:0.9rem; color:#555; margin:0;">Não há dados sobre amostra, dose ou medida de concentração. O alcance de "dobra" permanece indefinido.</p>
</div>
</div>

<div style="display:flex; gap:15px;">
<span style="color:#7C2128;">🔍</span>
<div>
<strong style="font-size:0.95rem; color:#111;">Checagens externas não consultadas</strong>
<p style="font-size:0.9rem; color:#555; margin:0;">Nenhuma agência ou base foi consultada neste exemplo. Isso não significa que não existam checagens sobre o tema.</p>
</div>
</div>
</div>
</div>

<div style="display:flex; align-items:flex-start; margin-bottom:3rem; border-bottom:1px solid #EAEAEA; padding-bottom:3rem;">
<div class="four-sections-number" style="margin-right:2rem; font-size:1.2rem; min-width:40px;">02</div>
<div>
<h3 style="margin-top:0; font-size:1.6rem !important; margin-bottom:1.5rem;">Como o texto argumenta</h3>
<ul style="color:#111; font-size:0.95rem; line-height:1.8; margin-bottom:1.5rem;">
<li><strong>Generalização apressada.</strong> "Qualquer pessoa" estende uma possível conclusão a todos, sem apresentar os limites da amostra.</li>
<li><strong>Apelo à autoridade.</strong> "Novo estudo" sugere credibilidade, mas não oferece uma referência que permita conferir essa autoridade.</li>
<li><strong>Linguagem de certeza.</strong> "Prova" e "dobra" dão um tom definitivo. Podem omitir incertezas, condições ou explicações alternativas.</li>
</ul>
<div style="border:1px solid #EAEAEA; padding:1rem; border-radius:8px; font-size:0.85rem; color:#555;">
Esses indícios convidam à investigação; não demonstram, por si só, que a afirmação está errada.
</div>
</div>
</div>

<div style="display:flex; align-items:flex-start; margin-bottom:3rem; border-bottom:1px solid #EAEAEA; padding-bottom:3rem;">
<div class="four-sections-number" style="margin-right:2rem; font-size:1.2rem; min-width:40px;">03</div>
<div>
<h3 style="margin-top:0; font-size:1.6rem !important; margin-bottom:1.5rem;">Perguntas para pensar antes de decidir</h3>
<ol style="color:#111; font-size:0.95rem; line-height:2.2; font-weight:500;">
<li>Consigo encontrar o estudo original e conferir o que ele realmente concluiu?</li>
<li>Quem participou da pesquisa e em quais condições o resultado foi observado?</li>
<li>Que evidência me faria rever minha impressão inicial antes de compartilhar?</li>
</ol>
</div>
</div>
</div>
        """)

    render_footer()


# Lógica de Roteamento baseada na URL
if curr_page == 'home':
    render_home()
else:
    render_analisar()
