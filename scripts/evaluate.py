import json
import math
import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from api.main import ebm, v_store, store

def calculate_metrics(relevant_ids, retrieved_ids, k=5):
    """
    Calcula P@k, Recall@k, F1@k, MRR y NDCG@k.
    """
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

    print("\n" + "="*60)
    print("  EVALUACIÓN DE CALIDAD - OSCAR INSIGHT SEARCH")
    print("="*60)
    
    total_metrics = {
        "precision": 0, "recall": 0, "f1": 0, "mrr": 0, "ndcg": 0
    }
    
    k = 5
    n_queries = len(ground_truth)

    for entry in ground_truth:
        query = entry["query"]
        relevant_ids = entry["relevant_ids"]
        
        # Simular búsqueda híbrida (0.6 EBM + 0.4 Vector)
        ebm_res = ebm.search(query)
        vec_res = v_store.search(query, top_k=10)
        
        ebm_map = {d: s for d, s in ebm_res}
        vec_map = {d: s for d, s in vec_res}
        
        all_ids = set(ebm_map.keys()) | set(vec_map.keys())
        combined = []
        for d_id in all_ids:
            score = (ebm_map.get(d_id, 0) * 0.6) + (vec_map.get(d_id, 0) * 0.4)
            combined.append((str(d_id), score))
            
        combined.sort(key=lambda x: x[1], reverse=True)
        retrieved_ids = [x[0] for x in combined]
        
        metrics = calculate_metrics(relevant_ids, retrieved_ids, k=k)
        
        for m in total_metrics:
            total_metrics[m] += metrics[m]
            
        print(f"\nQuery: '{query}'")
        print(f"  P@{k}: {metrics['precision']:.3f} | R: {metrics['recall']:.3f} | NDCG: {metrics['ndcg']:.3f}")

    print("\n" + "="*60)
    print("  RESULTADOS PROMEDIO")
    print("="*60)
    for m, val in total_metrics.items():
        print(f"  Mean {m.upper():<10}: {val/n_queries:.4f}")
    print("="*60 + "\n")

if __name__ == "__main__":
    run_evaluation()
