import logging
import json
from api.main import store, idx, v_store, ebm
from api.rag import rag_manager
from crawler.web_search import web_searcher

# Configurar logging para ver qué pasa
logging.basicConfig(level=logging.INFO)

def simulate_search_flow(query):
    print(f"\n=== SIMULANDO FLUJO PARA: '{query}' ===")
    
    # 1. Búsqueda Híbrida Local
    ebm_results = ebm.search(query)
    vector_results = v_store.search(query, top_k=5)
    
    ebm_map = {d: s for d, s in ebm_results}
    vector_map = {d: s for d, s in vector_results}
    all_ids = set(ebm_map.keys()) | set(vector_map.keys())
    
    combined = []
    for doc_id in all_ids:
        film = store.get_film(doc_id)
        if not film: continue
        score = (ebm_map.get(doc_id, 0) * 0.6) + (vector_map.get(doc_id, 0) * 0.4)
        combined.append({"title": film['title'], "year": film['year'], "score": score, "snippet": film.get('synopsis', '')[:100]})
    
    combined.sort(key=lambda x: x['score'], reverse=True)
    results = combined[:5]
    
    print(f"Resultados locales encontrados: {len(results)}")
    
    # 2. Trigger de Búsqueda Web
    was_web = False
    if len(results) < 3 or (results and results[0]['score'] < 0.25):
        print("Tratando de activar búsqueda web (Resultados insuficientes)...")
        web_results = web_searcher.search_and_format(query)
        if web_results:
            was_web = True
            results = web_results[:5]
            print(f"Resultados web encontrados: {len(results)}")

    # 3. RAG Generation
    print("Generando respuesta RAG...")
    answer = rag_manager.generate_response(query, results)
    print("\n--- RESPUESTA DE LA IA ---")
    print(answer)
    print("--------------------------")

if __name__ == "__main__":
    # Prueba 1: Consulta local conocida
    simulate_search_flow("Christopher Nolan and atomic bomb")
    
    # Prueba 2: Consulta que probablemente dispare búsqueda web (fuera del corpus)
    # simulate_search_flow("Who is the main actor in Dune 3?") 
