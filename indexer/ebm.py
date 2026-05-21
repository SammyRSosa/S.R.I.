"""
indexer/ebm.py
Extended Boolean Model (EBM) Engine (Corte 2 & 3)

Mathematical and Algorithmic Core of the Hybrid Information Retrieval System.
Provides normalized TF-IDF weight generation and soft logical evaluation using 
multidimensional p-norm distance algorithms.
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
    MATHEMATICAL FORMALISM: EXTENDED BOOLEAN MODEL (EBM) USING P-NORM ALGORITHMS
    ===========================================================================
    Proposed by Salton, Fox, and Wu (1983) in "Extended Boolean Information Retrieval",
    this model bridges the gap between structured boolean logic and the vector space model (VSM).
    It treats terms not as binary variables (0 or 1), but as coordinates in a normalized 
    multidimensional space [0, 1]^m, where weights are determined by TF-IDF metrics.

    1. Mathematical Definitions:
       Let d be a document, q be a query with m terms (t_1, t_2, ..., t_m), and w_{i,j} 
       be the normalized weight of term t_i in document d_j.
       
       A. Query with 'OR' operator: q = (t_1 OR t_2 OR ... OR t_m)
          In classical Boolean logic, the document is relevant if AT LEAST one term is present.
          Geometrically, this represents distance from the worst point (0, 0, ..., 0).
          Using the p-norm, the similarity score is:
          
              Sim_OR(d_j, q) = || (w_{1,j}, w_{2,j}, ..., w_{m,j}) ||_p
                             = [ (w_{1,j}^p + w_{2,j}^p + ... + w_{m,j}^p) / m ] ^ (1/p)

       B. Query with 'AND' operator: q = (t_1 AND t_2 AND ... AND t_m)
          In classical Boolean logic, all terms must be present. Geometrically, this represents
          proximity to the ideal point (1, 1, ..., 1).
          The similarity score is:
          
              Sim_AND(d_j, q) = 1 - || (1-w_{1,j}, 1-w_{2,j}, ..., 1-w_{m,j}) ||_p
                              = 1 - [ ((1-w_{1,j})^p + (1-w_{2,j})^p + ... + (1-w_{m,j})^p) / m ] ^ (1/p)

    2. Tuning Parameter 'p' (Smoothing Factor):
       - p = 1: The model collapses into a simple linear average (Vector Space Model behavior).
       - p = infinity: The model collapses into classical binary Boolean logic (Strict AND / OR).
       - 1 < p < infinity: Soft logical interpolation. Our system defaults to p = 2.0 (Euclidean distance).

    3. Weighting Scheme (Normalized TF-IDF):
       To prevent document length bias and ensure all weights lie strictly within [0, 1]:
       
           w_{i,j} = TF_norm_{i,j} * IDF_norm_i
           
           Where:
           - TF_norm_{i,j} = tf_{i,j} / max_tf_j
             (tf_{i,j} is the frequency of term i in doc j, max_tf_j is the maximum frequency of any term in doc j)
           - IDF_norm_i = log_e(N / n_i) / log_e(N)
             (N is the total number of documents in the corpus, n_i is the document frequency of term i)

    ALGORITHMIC PIPELINE & FLOW CHART
    =================================
    [Query Entry] ──> [Normalizer & Tokenizer (NLTK)] ──> [Stems Extracted]
                                                                  │
                                                                  ▼
    [EBM Sim_OR / Sim_AND] <── [Fetch Weights w_ij] <── [Candidate Search]
              │
              ▼
    [Sort by Similarity Descending] ──> [Top-K Hybrid Reranking]

    Attributes:
        store (DocumentStore): Reference to document repository.
        index (InvertedIndex): Reference to inverted index for term statistics and tokenization.
        p (float): Exponent factor for p-norm calculation (controls strictness/smoothing).
        weights (dict): In-memory nested mapping of {term: {doc_id: weight_value}}.
    """
    
    WEIGHTS_FILE = "ebm_weights.json"
    
    def __init__(self, store: DocumentStore, index: InvertedIndex, p: float = 2.0):
        """
        Inicializa el motor EBM.

        Args:
            store: Instancia de DocumentStore cargada.
            index: Instancia de InvertedIndex para acceder a las frecuencias.
            p: Exponente para el cálculo de la p-norma (default 2.0 para distancia euclidiana).
        """
        self.store = store
        self.index = index
        self.p = p
        
        # Mapeos de pre-cálculo de pesos: term -> {doc_id: w_ij}
        self.weights: dict[str, dict[int, float]] = {}
        
        # Carga los pesos si existen en disco para evitar recalcular
        self.weights_path = store.data_dir / self.WEIGHTS_FILE
        self.load_weights()
        
    def build_weights(self) -> None:
        """
        Calcula la matriz de pesos w_{i,j} para todos los términos del vocabulario.
        Utiliza el esquema de ponderación TF-IDF normalizado al rango [0, 1].
        
        Fórmula de peso:
            w_{i,j} = (tf_{i,j} / max_tf_{j}) * idf_i
        Donde idf_i es log(N/n_i) / log(N) para asegurar normalización.
        """
        logger.info("Construyendo pesos EBM TF-IDF para %d documentos...", self.index.num_docs)
        N = max(1, self.index.num_docs)
        
        # Paso 1: Determinar la frecuencia máxima de cualquier término en cada documento
        # Esto es necesario para la normalización del TF
        max_tf_per_doc: dict[int, int] = {}
        for term, postings in self.index._raw_index.items():
            for doc_id, tf in postings.items():
                max_tf_per_doc[doc_id] = max(max_tf_per_doc.get(doc_id, 0), tf)
                
        # Paso 2: Calcular el peso w_ij para cada par (término, documento)
        self.weights.clear()
        
        for term, postings in self.index._raw_index.items():
            n_i = len(postings) # Document frequency del término i
            
            # Cálculo de IDF normalizado al rango [0, 1]
            if N > 1 and n_i < N:
                idf_i = math.log(N / n_i) / math.log(N)
            else:
                # Caso borde: el término aparece en todos los documentos o N=1
                idf_i = 0.0001
                
            self.weights[term] = {}
            for doc_id, tf in postings.items():
                max_tf = max_tf_per_doc.get(doc_id, 1)
                norm_tf = tf / max_tf
                
                # Peso final del término i en el documento j
                w_ij = norm_tf * idf_i
                self.weights[term][doc_id] = round(w_ij, 5)
                
        self.save_weights()
        logger.info("Pesos EBM construidos y persistidos con éxito.")

    def save_weights(self) -> None:
        """Persiste los pesos calculados en un archivo JSON."""
        with open(self.weights_path, "w", encoding="utf-8") as f:
            json.dump(self.weights, f)
            
    def load_weights(self) -> None:
        """Carga los pesos desde disco si el archivo existe."""
        if self.weights_path.exists():
            try:
                with open(self.weights_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    self.weights = {
                        term: {int(d_id): w for d_id, w in docs.items()}
                        for term, docs in raw.items()
                    }
                logger.info("Pesos EBM cargados desde %s", self.WEIGHTS_FILE)
            except Exception as e:
                logger.error("Error al cargar pesos EBM: %s", e)

    def search(self, query: str, op: str = "OR") -> list[tuple[int, float]]:
        """
        Evalúa una consulta utilizando la lógica de p-norma.

        Args:
            query: Texto de la consulta.
            op: Operador booleano a aplicar entre todos los términos ("AND" o "OR").

        Returns:
            Lista de tuplas (doc_id, similitud) ordenada por relevancia descendente.
        """
        # 1. Normalizar y tokenizar la consulta usando el mismo pipeline del indexador
        tokens = self.index._tokenize(query)
        if not tokens:
            return []
            
        # 2. Identificar documentos candidatos (aquellos que contienen al menos un término)
        candidate_docs = set()
        for t in tokens:
            if t in self.weights:
                candidate_docs.update(self.weights[t].keys())
                
        m = len(tokens) # Número de términos en la consulta
        results = []
        
        # 3. Calcular la similitud para cada documento candidato
        for doc_id in candidate_docs:
            # Obtener el vector de pesos (w_i) del documento para los términos de la consulta
            doc_weights = [
                self.weights.get(t, {}).get(doc_id, 0.0) 
                for t in tokens
            ]
            
            if op.upper() == "OR":
                # Fórmula OR: Proximidad al origen (0,0...0)
                # Sim = [ (w1^p + ... + wm^p) / m ] ^ (1/p)
                sum_wp = sum(w**self.p for w in doc_weights)
                sim = (sum_wp / m) ** (1.0 / self.p)
            else:
                # Fórmula AND: Proximidad al punto ideal (1,1...1)
                # Sim = 1 - [ ((1-w1)^p + ... + (1-wm)^p) / m ] ^ (1/p)
                sum_1_minus_wp = sum((1.0 - w)**self.p for w in doc_weights)
                sim = 1.0 - (sum_1_minus_wp / m) ** (1.0 / self.p)
                
            if sim > 1e-6: # Umbral de relevancia mínima
                results.append((doc_id, sim))
                
        # 4. Ordenar resultados por score de similitud descendente
        results.sort(key=lambda x: x[1], reverse=True)
        return results

