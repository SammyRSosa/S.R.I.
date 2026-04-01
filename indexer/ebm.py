"""
indexer/ebm.py
Extended Boolean Model (Corte 2)

Calcula pesos TF-IDF normalizados y evalúa consultas mediante distancias $p$-norm.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from .inverted_index import InvertedIndex
from database.store import DocumentStore

logger = logging.getLogger(__name__)

class ExtendedBooleanModel:
    """
    Implementa el Modelo Booleano Extendido (Baeza-Yates & Ribeiro-Neto).
    Ponderación: tf-idf normalizado [0, 1].
    Similitud: p-norm.
    """
    
    WEIGHTS_FILE = "ebm_weights.json"
    
    def __init__(self, store: DocumentStore, index: InvertedIndex, p: float = 2.0):
        self.store = store
        self.index = index
        self.p = p
        
        # Mapeos de pre-cálculo de pesos: term -> {doc_id: w_ij}
        self.weights: dict[str, dict[int, float]] = {}
        
        # Carga los pesos si existen
        self.weights_path = store.data_dir / self.WEIGHTS_FILE
        self.load_weights()
        
    def build_weights(self) -> None:
        """
        Recorre el índice y calcula w_ij según tf-idf normalizado.
        w_{i,j} = (tf_{i,j} / max_tf_{j}) * idf_i
        
        Donde:
          idf_i = log(N / n_i) / log(N)  (normalizado al rango [0,1])
        """
        logger.info("Construyendo pesos EBM TF-IDF para %d documentos...", self.index.num_docs)
        N = max(1, self.index.num_docs)
        
        # Calcular el max_tf por documento
        max_tf_per_doc: dict[int, int] = {}
        for term, postings in self.index._raw_index.items():
            for doc_id, tf in postings.items():
                max_tf_per_doc[doc_id] = max(max_tf_per_doc.get(doc_id, 0), tf)
                
        # Calcular TF-IDF
        self.weights.clear()
        
        for term, postings in self.index._raw_index.items():
            n_i = len(postings)
            # Normalize IDF to [0,1] dividing by log(N)
            # To handle N=1 or n_i=N cases safely
            if N > 1 and n_i < N:
                idf_i = math.log(N / n_i) / math.log(N)
            else:
                idf_i = 1.0 if N == 1 else 0.01  # Pequeño peso si aparece en todos lados
                
            self.weights[term] = {}
            for doc_id, tf in postings.items():
                max_tf = max_tf_per_doc[doc_id]
                norm_tf = tf / max_tf if max_tf > 0 else 0
                
                w_ij = norm_tf * idf_i
                self.weights[term][doc_id] = round(w_ij, 5)
                
        self.save_weights()
        logger.info("Pesos EBM construidos localmente con éxito.")

    def save_weights(self) -> None:
        with open(self.weights_path, "w", encoding="utf-8") as f:
            json.dump(self.weights, f)
            
    def load_weights(self) -> None:
        if self.weights_path.exists():
            with open(self.weights_path, "r", encoding="utf-8") as f:
                # {term: {doc_id_str: weight}}
                raw = json.load(f)
                self.weights = {
                    term: {int(d_id): w for d_id, w in docs.items()}
                    for term, docs in raw.items()
                }
            logger.info("Pesos EBM cargados correctamente.")

    def search(self, query: str, op: str = "OR") -> list[tuple[int, float]]:
        """
        Calcula la similitud p-norm para una consulta plana.
        op = "AND" o "OR". 
        (Por simplicidad, asume que todos los términos son unidos por el mismo operador).
        """
        tokens = self.index._tokenize(query)
        if not tokens:
            return []
            
        # Obtenemos todos los documentos que contengan al menos un término
        candidate_docs = set()
        for t in tokens:
            if t in self.weights:
                candidate_docs.update(self.weights[t].keys())
                
        m = len(tokens)
        results = []
        
        for doc_id in candidate_docs:
            # Obtener pesos para este documento
            # Si el término no existe, w_ij = 0
            doc_weights = [
                self.weights.get(t, {}).get(doc_id, 0.0) 
                for t in tokens
            ]
            
            if op.upper() == "OR":
                # OR p-norm: ( sum(w^p) / m ) ^ (1/p)
                sum_wp = sum(w**self.p for w in doc_weights)
                sim = (sum_wp / m) ** (1.0 / self.p)
            else:
                # AND p-norm: 1 - ( sum((1-w)^p) / m ) ^ (1/p)
                sum_1_minus_wp = sum((1.0 - w)**self.p for w in doc_weights)
                sim = 1.0 - (sum_1_minus_wp / m) ** (1.0 / self.p)
                
            if sim > 0:
                results.append((doc_id, sim))
                
        # Normalizar scores
        results.sort(key=lambda x: x[1], reverse=True)
        return results

