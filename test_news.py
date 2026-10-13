import time
from src.state import initial_state
from src.graph import sistema_multiagente

textos = [
    # Texto 1: 2020 (Covid/Cloroquina)
    """Urgente! Médicos escondem a verdade sobre o tratamento precoce da COVID-19!
O renomado cientista Dr. Fulano afirmou categoricamente que o uso da Cloroquina cura a doença em 100% dos casos.
É um milagre que está sendo abafado pela mídia tradicional e pelos grandes laboratórios.
Qualquer pessoa que não apoie o tratamento está condenando milhares à morte.
Não existe outra opção: ou você toma a medicação, ou você não tem salvação.
As vacinas que estão sendo desenvolvidas são extremamente perigosas e contêm chips de rastreamento financiados por bilionários.
Os hospitais estão vazios, os caixões estão sendo enterrados com pedras dentro apenas para assustar a população.
A pandemia é uma fraude monumental inventada para quebrar a economia do país.
Compartilhe isso imediatamente antes que o governo censure essa mensagem!
Todo mundo já sabe que as autoridades de saúde estão mentindo descaradamente para a população.
É terrível a forma como o povo está sendo manipulado. Não seja mais um gado!""",

    # Texto 2: 2022 (Eleições/Urnas)
    """Fraude comprovada nas urnas eletrônicas nestas eleições! 
Auditoria militar independente revelou que milhões de votos foram transferidos secretamente durante a madrugada.
Um hacker internacional confirmou que o sistema do TSE é o mais vulnerável do planeta, permitindo invasões com facilidade.
Ou cancelamos as eleições imediatamente, ou o país cairá no comunismo irreversível.
Os institutos de pesquisa manipularam os números desde o primeiro dia para desestimular os eleitores de bem.
Urnas quebradas foram encontradas no lixo no interior do Nordeste, já com os votos computados para o candidato rival.
O presidente do tribunal eleitoral é um ditador que age acima da lei.
As Forças Armadas precisam intervir hoje mesmo! URGENTE! Se esperarmos até amanhã, será tarde demais.
Todo brasileiro honesto sabe que as eleições foram roubadas de forma grotesca.
Mande para todos os seus contatos agora, a grande mídia não vai mostrar isso na TV!""",

    # Texto 3: 2023 (8 de Janeiro)
    """A verdade oculta sobre as manifestações em Brasília!
Infiltrados destruíram tudo propositalmente para culpar os manifestantes pacíficos.
Um general de alta patente garantiu que as portas foram abertas por ordem de dentro do próprio governo.
É óbvio que foi uma armadilha meticulosamente preparada.
A mídia golpista chama os patriotas de terroristas, mas ignora os verdadeiros criminosos no poder.
Os campos de concentração onde prenderam os inocentes são piores do que na Segunda Guerra Mundial.
Pessoas estão morrendo de fome e sede lá dentro neste exato momento, sem direito a advogados.
O país está vivendo uma ditadura brutal e silenciosa. Ou lutamos agora pela nossa liberdade, ou seremos escravizados para sempre.
O mundo inteiro está chocado com a parcialidade da nossa Suprema Corte.
Divulgue essa mensagem urgente antes que apaguem as redes sociais para sempre!"""
]

print("Iniciando bateria de testes locais com textos crus (2020-2023)...\n")

for i, texto in enumerate(textos, 1):
    print(f"--- Teste {i}/{len(textos)} ---")
    start = time.time()
    
    try:
        estado = initial_state(texto)
        resultado = sistema_multiagente.invoke(estado)
        tempo = time.time() - start
        
        qtd_frases = len(resultado.get('segments', []))
        marcadores = resultado.get('text_report').markers if resultado.get('text_report') else []
        qtd_marcadores = len(marcadores)
        
        avisos = resultado.get('warnings', [])
        
        print(f"✅ Sucesso em {tempo:.1f}s!")
        print(f"📊 Frases processadas: {qtd_frases}")
        print(f"🚩 Marcadores de Viés/Falácia encontrados: {qtd_marcadores}")
        if avisos:
            print("⚠️ Avisos:")
            for aviso in avisos:
                print(f"  - {aviso}")
        print("\n")
        
    except Exception as e:
        print(f"❌ Erro ao analisar texto: {e}\n")

print("Bateria de testes concluída!")
