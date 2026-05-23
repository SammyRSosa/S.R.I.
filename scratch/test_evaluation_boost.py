import json
import math
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from api.main import ebm, v_store, store, extract_metadata_from_query
from api.rag import rag_manager

def calculate_metrics(relevant_ids, retrieved_ids, k=5):
    retrieved_k = retrieved_ids[:k]
    rel_set = set(relevant_ids)
    ret_set = set(retrieved_k)
    
    # Precision @ k
    true_positives = len(rel_set & ret_set)
    precision = true_positives / k if k > 0 else 0
    
    # Recall @ k
    recall = true_positives / len(rel_set) if len(rel_set) > 0 else 0
    
    # F1 Score
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    
    # MRR (Mean Reciprocal Rank)
    mrr = 0
    for i, doc_id in enumerate(retrieved_ids, 1):
        if doc_id in rel_set:
            mrr = 1 / i
            break
            
    # NDCG @ k
    dcg = 0
    for i, doc_id in enumerate(retrieved_k, 1):
        if doc_id in rel_set:
            dcg += 1 / math.log2(i + 1)
            
    idcg = 0
    for i in range(1, min(len(rel_set), k) + 1):
        idcg += 1 / math.log2(i + 1)
        
    ndcg = dcg / idcg if idcg > 0 else 0
    
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "mrr": mrr,
        "ndcg": ndcg
    }

def run_evaluation():
    gt_path = ROOT / "data" / "ground_truth.json"
    if not gt_path.exists():
        print("Error: data/ground_truth.json no encontrado.")
        return

    with open(gt_path, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    print("\n" + "="*70)
    print("  EVALUACIÓN DE CALIDAD EXACTA (CON TRADUCCIÓN Y BOOSTS DE API)")
    print("="*70)
    
    total_metrics = {
        "precision": 0, "recall": 0, "f1": 0, "mrr": 0, "ndcg": 0
    }
    
    k = 5
    n_queries = len(ground_truth)
    current_year = datetime.now().year

    for entry in ground_truth:
        query = entry["query"]
        relevant_ids = entry["relevant_ids"]
        
        # --- LOGICA EXACTA DE MAIN.PY ---
        # 1. Traduccion
        translated_query = rag_manager.translate_query_for_ebm(query)
        # 2. Extraccion metadatos
        extracted_meta = extract_metadata_from_query(query)
        target_year = extracted_meta.get('year')
        
        # 3. Busquedas
        ebm_res = ebm.search(translated_query, op="OR")
        try:
            vec_res = v_store.search(query, top_k=100) if v_store.index and v_store.index.ntotal > 0 else []
        except Exception as e:
            vec_res = []
            
        ebm_ranks = {doc_id: rank for rank, (doc_id, _) in enumerate(ebm_res, 1)}
        vec_ranks = {doc_id: rank for rank, (doc_id, _) in enumerate(vec_res, 1)}
        
        ebm_scores_map = {doc_id: score for doc_id, score in ebm_res}
        vec_scores_map = {doc_id: score for doc_id, score in vec_res}
        
        all_doc_ids = set(ebm_ranks.keys()) | set(vec_ranks.keys())
        combined = []
        
        for doc_id in all_doc_ids:
            film = store.get_film(doc_id)
            if not film:
                continue
                
            # Filter year
            if target_year is not None:
                film_year = film.get("year")
                try:
                    if int(film_year) != target_year:
                        continue
                except:
                    continue
            
            s_ebm = ebm_scores_map.get(doc_id, 0.0)
            s_vec = vec_scores_map.get(doc_id, 0.0)
            base_score = (s_ebm * 0.6) + (s_vec * 0.4)
            
            # Boosts
            pop = float(film.get("popularity", 0))
            pop_factor = min(1.0, pop / 100.0) * 0.1
            try:
                f_year = int(film.get("year", 0))
                fresh_factor = max(0, 1.0 - (current_year - f_year) / 50.0) * 0.05
            except:
                fresh_factor = 0
                
            final_score = base_score + pop_factor + fresh_factor
            combined.append((str(doc_id), final_score, film.get("title")))
            
        combined.sort(key=lambda x: x[1], reverse=True)
        retrieved_ids = [x[0] for x in combined]
        
        metrics = calculate_metrics(relevant_ids, retrieved_ids, k=k)
        
        for m in total_metrics:
            total_metrics[m] += metrics[m]
            
        print(f"\nQuery: '{query}' -> Traducida: '{translated_query}'")
        print("  Top 5 recuperados:")
        for idx_res, (d_id, sc, title) in enumerate(combined[:5], 1):
            is_rel = " [RELEVANTE]" if d_id in relevant_ids else ""
            print(f"    {idx_res}. doc_id={d_id} | {title} | score={sc:.4f}{is_rel}")
        print(f"  Métricas: P@{k}: {metrics['precision']:.3f} | R: {metrics['recall']:.3f} | NDCG: {metrics['ndcg']:.3f} | MRR: {metrics['mrr']:.3f}")

    print("\n" + "="*70)
    print("  RESULTADOS PROMEDIO FINALES (CON LOGICA COMPLETA)")
    print("="*70)
    for m, val in total_metrics.items():
        print(f"  Mean {m.upper():<10}: {val/n_queries:.4f}")
    print("="*70 + "\n")

if __name__ == "__main__":
    run_evaluation()
