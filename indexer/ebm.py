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
    Implementación del Modelo Booleano Extendido (EBM) según el formalismo de 
    p-norma propuesto por Salton, Fox y Wu (1983).

    Este modelo supera la rigidez del modelo booleano clásico permitiendo que 
    los términos de la consulta tengan pesos (TF-IDF) y que la similitud sea 
    una función continua en el intervalo [0, 1].

    Matemáticamente:
    - Para una consulta OR: Sim(d, q) = [(w1^p + w2^p + ... + wm^p) / m]^(1/p)
    - Para una consulta AND: Sim(d, q) = 1 - [((1-w1)^p + (1-w2)^p + ... + (1-wm)^p) / m]^(1/p)

    Attributes:
        store (DocumentStore): Referencia al almacén de documentos.
        index (InvertedIndex): Referencia al índice invertido para tokenización.
        p (float): Parámetro de suavizado (p=1 es modelo vectorial, p=inf es booleano puro).
        weights (dict): Diccionario de pesos calculados {término: {doc_id: peso}}.
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

