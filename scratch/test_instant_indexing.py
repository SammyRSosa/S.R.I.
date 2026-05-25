import time
import logging
from api.main import store, idx, v_store, ebm
from crawler.web_search import web_searcher

# Configurar logs para ver el proceso en tiempo real
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_instant_indexing")

def run_hybrid_search(query: str):
    start_time = time.time()
    
    # 1. Búsqueda local (EBM + Vectores)
    ebm_results = ebm.search(query)
    vector_results = v_store.search(query, top_k=5)
    
    ebm_map = {d: s for d, s in ebm_results}
    vector_map = {d: s for d, s in vector_results}
    all_ids = set(ebm_map.keys()) | set(vector_map.keys())
    
    combined = []
    for doc_id in all_ids:
        film = store.get_film(doc_id)
        if not film:
            continue
        score = (ebm_map.get(doc_id, 0) * 0.6) + (vector_map.get(doc_id, 0) * 0.4)
        combined.append({
            "doc_id": doc_id,
            "title": film.get("title", "Unknown"),
            "year": film.get("year", "N/A"),
            "score": score,
            "ebm_score": ebm_map.get(doc_id, 0),
            "vector_score": vector_map.get(doc_id, 0),
            "snippet": film.get("rich_text", "")[:150],
            "is_web_result": False
        })
        
    combined.sort(key=lambda x: x["score"], reverse=True)
    
    # Decisión de Fallback
    top_score = combined[0]["score"] if combined else 0.0
    was_web = False
    
    if len(combined) < 3 or top_score < 0.15:
        logger.info("[SEARCH] Score local bajo (%.3f) o pocos resultados (%d). Activando Web Search Fallback...", top_score, len(combined))
        # PASANDO los objetos activos del motor para indexación incremental instantánea
        web_results = web_searcher.search_and_format(
            query,
            store=store,
            idx=idx,
            ebm=ebm,
            v_store=v_store
        )
        if web_results:
            was_web = True
            combined = web_results
            combined.sort(key=lambda x: x["score"], reverse=True)
            
    elapsed = time.time() - start_time
    return combined[:5], was_web, elapsed

if __name__ == "__main__":
    query = "Bishkek capital of Kyrgyzstan travel tourism"
    
    print("\n" + "="*80)
    print("EJECUTANDO PRUEBA 1: PRIMER INTENTO (DEBE DISPARAR FALLBACK Y CRAWLEADO)")
    print("="*80)
    results1, was_web1, time1 = run_hybrid_search(query)
    
    print(f"\nResultados obtenidos en {time1:.3f} segundos.")
    print(f"¿Fue fallback de la web?: {was_web1}")
    for i, r in enumerate(results1):
        print(f"[{i+1}] {r['title']} (Score: {r['score']:.4f}) | Web: {r['is_web_result']}")
        print(f"    Snippet: {r['snippet']}\n")
        
    print("\n" + "="*80)
    print("EJECUTANDO PRUEBA 2: SEGUNDO INTENTO (DEBE RESPONDER INSTANTÁNEAMENTE Y EN LOCAL)")
    print("="*80)
    results2, was_web2, time2 = run_hybrid_search(query)
    
    print(f"\nResultados obtenidos en {time2:.3f} segundos.")
    print(f"¿Fue fallback de la web?: {was_web2}")
    for i, r in enumerate(results2):
        print(f"[{i+1}] {r['title']} (Score: {r['score']:.4f}) | Web: {r['is_web_result']}")
        print(f"    Snippet: {r['snippet']}\n")
        
    print("="*80)
    print("RESUMEN DE EFICIENCIA:")
    print(f"Tiempo en el 1er intento (Web Fallback + Crawler): {time1:.3f}s")
    print(f"Tiempo en el 2do intento (Búsqueda Local Indexada): {time2:.3f}s")
    reduction = ((time1 - time2) / time1) * 100
    print(f"Reducción en tiempo de respuesta: {reduction:.2f}% de velocidad extra!")
    print("="*80)
