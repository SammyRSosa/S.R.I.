"""
database/vector_store.py
Módulo de Almacenamiento Vectorial — Oscar Insight Search (Corte 2)

Provee indexación y búsqueda semántica (vectores) utilizando FAISS
y Sentence-Transformers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"

class VectorStore:
    """
    Gestor del índice vectorial usando FAISS y miniLM.
    """
    
    VECTOR_FILE = "faiss_index.bin"
    MAPPING_FILE = "vector_mapping.json"
    MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
    
    def __init__(self, data_dir: str | Path = DEFAULT_DATA_DIR) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.data_dir / self.VECTOR_FILE
        self.mapping_path = self.data_dir / self.MAPPING_FILE
        
        self.model = SentenceTransformer(self.MODEL_NAME)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        
        # FAISS index (Inner Product for Cosine Similarity since vectors will be normalized)
        self.index: faiss.IndexFlatIP = faiss.IndexFlatIP(self.embedding_dim)
        
        # Mapping: vector_id (int FAISS) -> doc_id (int Store)
        self.vector_to_doc: dict[int, int] = {}
        # Mapping: doc_id (int Store) -> vector_id (int FAISS)
        self.doc_to_vector: dict[int, int] = {}
        
        self.load()
        
    def build_from_documents(self, documents: dict[int, dict]) -> None:
        """
        Construye el índice vectorial desde el DocumentStore, codificando el rich_text.
        """
        logger.info("Construyendo índice vectorial FAISS para %d documentos...", len(documents))
        
        doc_ids = []
        texts = []
        
        for doc_id, film_data in documents.items():
            rich_text = film_data.get("rich_text", "")
            if not rich_text:
                continue
            doc_ids.append(int(doc_id))
            # Limitamos el texto para no saturar el transformador
            texts.append(rich_text[:2000])
            
        if not texts:
            logger.warning("No hay textos para vectorizar.")
            return
            
        # Encode genera vectores de float32
        embeddings = self.model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
        # Normalizar para que el producto interno sea equivalente a similitud coseno
        faiss.normalize_L2(embeddings)
        
        # Construir índice desde cero
        self.index = faiss.IndexFlatIP(self.embedding_dim)
        self.index.add(embeddings)
        
        # Guardar mapeos
        self.vector_to_doc = {i: doc_id for i, doc_id in enumerate(doc_ids)}
        self.doc_to_vector = {doc_id: i for i, doc_id in enumerate(doc_ids)}
        
        self.save()
        logger.info("Índice vectorial FAISS construido con éxito.")

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """
        Realiza búsqueda semántica y devuelve [(doc_id, score_coseno), ...].
        """
        if self.index.ntotal == 0:
            return []
            
        emb = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(emb)
        
        # distance (I) y scores (D)
        scores, I = self.index.search(emb, top_k)
        
        results = []
        for score, vector_id in zip(scores[0], I[0]):
            if vector_id != -1 and vector_id in self.vector_to_doc:
                doc_id = self.vector_to_doc[vector_id]
                # FAISS inner product de L2 normalizadas -> Similitud Coseno [-1, 1]
                # Acotamos el valor entre 0 y 1 para promediar fácilmente
                normalized_score = max(0.0, float(score))
                results.append((doc_id, normalized_score))
                
        return results
        
    def save(self) -> None:
        """Persiste índice FAISS y mappings."""
        faiss.write_index(self.index, str(self.index_path))
        with open(self.mapping_path, "w", encoding="utf-8") as f:
            json.dump(self.vector_to_doc, f)
            
    def load(self) -> None:
        """Carga FAISS y mappings si existen."""
        if self.index_path.exists() and self.mapping_path.exists():
            self.index = faiss.read_index(str(self.index_path))
            with open(self.mapping_path, "r", encoding="utf-8") as f:
                raw_mapping = json.load(f)
                self.vector_to_doc = {int(k): int(v) for k, v in raw_mapping.items()}
                self.doc_to_vector = {int(v): int(k) for k, v in raw_mapping.items()}
            logger.info("FAISS cargado: %d vectores disponibles.", self.index.ntotal)
