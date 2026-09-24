import chromadb
import os

def seed_database():
    print("Atualizando o banco de dados ChromaDB com temas políticos...")
    client = chromadb.PersistentClient(path="./chroma_data")
    
    # Reseta a coleção anterior para não misturar os temas
    try:
        client.delete_collection("fact_checks")
    except Exception:
        pass

    collection = client.create_collection(name="fact_checks")
    
    # Documentos sobre fatos políticos da Constituição e sistema eleitoral
    documents = [
        "O voto no Brasil é obrigatório para cidadãos alfabetizados maiores de 18 anos e menores de 70 anos.",
        "As urnas eletrônicas brasileiras são auditáveis, não possuem conexão com a internet, e são consideradas seguras.",
        "O Supremo Tribunal Federal (STF) é a mais alta instância do poder judiciário brasileiro, composto por 11 ministros.",
        "O mandato do Presidente da República do Brasil tem a duração de quatro anos, sendo permitida a reeleição para um único período subsequente.",
        "O Congresso Nacional do Brasil é bicameral, composto pela Câmara dos Deputados e pelo Senado Federal."
    ]
    
    metadatas = [
        {"source_name": "Tribunal Superior Eleitoral (TSE)", "source_url": "https://tse.jus.br"},
        {"source_name": "Tribunal Superior Eleitoral (TSE)", "source_url": "https://tse.jus.br/urnas"},
        {"source_name": "Supremo Tribunal Federal (STF)", "source_url": "https://stf.jus.br"},
        {"source_name": "Constituição Federal", "source_url": "https://planalto.gov.br"},
        {"source_name": "Congresso Nacional", "source_url": "https://congressonacional.leg.br"}
    ]
    
    ids = [f"politica_{i}" for i in range(len(documents))]
    
    print(f"Inserindo {len(documents)} fatos políticos na coleção 'fact_checks'...")
    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )
    
    print("✅ Banco de dados político populado com sucesso em './chroma_data'!")

if __name__ == "__main__":
    seed_database()
