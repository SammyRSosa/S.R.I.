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
    Gestor del índice vectorial semántico utilizando FAISS y Sentence-Transformers.
    
    Este módulo permite realizar búsquedas por significado (similitud de coseno) 
    en lugar de solo por coincidencia exacta de palabras, utilizando un modelo 
    de lenguaje (bi-encoder) para generar representaciones densas de los documentos.

    Attributes:
        data_dir (Path): Directorio de persistencia.
        model (SentenceTransformer): Modelo de lenguaje cargado.
        index (faiss.Index): Índice de búsqueda aproximada (FAISS).
        vector_to_doc (dict): Mapeo interno para recuperar doc_id desde FAISS.
    """
    
    VECTOR_FILE = "faiss_index.bin"
    MAPPING_FILE = "vector_mapping.json"
    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    TEXT_LIMIT = 2000 # Límite de caracteres para evitar truncamiento excesivo
    
    def __init__(self, data_dir: str | Path = DEFAULT_DATA_DIR, model_name: str = DEFAULT_MODEL) -> None:
        """
        Inicializa el almacén vectorial.

        Args:
            data_dir: Carpeta donde se guardarán los archivos binarios.
            model_name: Nombre del modelo de HuggingFace a utilizar.
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.data_dir / self.VECTOR_FILE
        self.mapping_path = self.data_dir / self.MAPPING_FILE
        
        logger.info("Cargando modelo de embeddings: %s", model_name)
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        
        # Inicializar índice FAISS para Producto Interno (IP)
        # Nota: Al normalizar los vectores a L2, el Producto Interno es equivalente 
        # a la Similitud de Coseno.
        self.index: faiss.IndexFlatIP = faiss.IndexFlatIP(self.embedding_dim)
        
        # Diccionarios de mapeo: vector_id (FAISS) <-> doc_id (DocumentStore)
        self.vector_to_doc: dict[int, int] = {}
        self.doc_to_vector: dict[int, int] = {}
        
        self.load()
        
    def build_from_documents(self, documents: dict[int, dict]) -> None:
        """
        Codifica todos los documentos del store y construye el índice FAISS.

        Args:
            documents: Diccionario de películas proveniente del DocumentStore.
        """
        logger.info("Generando embeddings para %d documentos...", len(documents))
        
        doc_ids = []
        texts = []
        
        # Preparar corpus de texto para el modelo
        for doc_id, film_data in documents.items():
            # Usamos rich_text (título + sinopsis + críticas) para máxima riqueza semántica
            rich_text = film_data.get("rich_text", "")
            if not rich_text:
                continue
                
            doc_ids.append(int(doc_id))
            # Truncamos ligeramente para no exceder el límite de tokens del modelo
            texts.append(rich_text[:self.TEXT_LIMIT])
            
        if not texts:
            logger.warning("No se encontraron textos válidos para indexación vectorial.")
            return
            
        # 1. Generación de vectores (embeddings) - Este paso es intensivo en CPU/GPU
        embeddings = self.model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
        
        # 2. Normalización L2 para asegurar que el Producto Interno sea Similitud de Coseno
        faiss.normalize_L2(embeddings)
        
        # 3. Construcción del índice FAISS
        self.index = faiss.IndexFlatIP(self.embedding_dim)
        self.index.add(embeddings)
        
        # 4. Actualizar mapeos de IDs
        self.vector_to_doc = {i: doc_id for i, doc_id in enumerate(doc_ids)}
        self.doc_to_vector = {doc_id: i for i, doc_id in enumerate(doc_ids)}
        
        self.save()
        logger.info("Índice FAISS finalizado con %d vectores.", self.index.ntotal)

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """
        Busca los documentos más cercanos semánticamente a la consulta.

        Args:
            query: Texto de búsqueda en lenguaje natural.
            top_k: Número máximo de resultados.

        Returns:
            Lista de tuplas (doc_id, similitud_coseno) ordenada de mayor a menor.
        """
        if self.index.ntotal == 0:
            logger.warning("El índice vectorial está vacío. Ejecute build_from_documents.")
            return []
            
        # Codificar y normalizar la consulta
        emb = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(emb)
        
        # Búsqueda en FAISS
        # D: Distancias (scores), I: Índices (IDs internos de FAISS)
        scores, I = self.index.search(emb, top_k)
        
        results = []
        for score, vector_id in zip(scores[0], I[0]):
            # FAISS devuelve -1 si no encuentra suficientes resultados
            if vector_id != -1 and vector_id in self.vector_to_doc:
                doc_id = self.vector_to_doc[vector_id]
                # Normalizamos el score al rango [0, 1]
                normalized_score = max(0.0, min(1.0, float(score)))
                results.append((doc_id, normalized_score))
                
        return results
        
    def save(self) -> None:
        """Persiste el índice binario y el mapeo de IDs en disco."""
        try:
            faiss.write_index(self.index, str(self.index_path))
            with open(self.mapping_path, "w", encoding="utf-8") as f:
                json.dump(self.vector_to_doc, f)
            logger.debug("Archivos vectoriales guardados en %s", self.data_dir)
        except Exception as e:
            logger.error("Error al guardar VectorStore: %s", e)
            
    def load(self) -> None:
        """Carga el índice y mapeos existentes para evitar re-entrenamiento."""
        if self.index_path.exists() and self.mapping_path.exists():
            try:
                self.index = faiss.read_index(str(self.index_path))
                with open(self.mapping_path, "r", encoding="utf-8") as f:
                    raw_mapping = json.load(f)
                    self.vector_to_doc = {int(k): int(v) for k, v in raw_mapping.items()}
                    self.doc_to_vector = {int(v): int(k) for k, v in raw_mapping.items()}
                logger.info("Índice vectorial cargado exitosamente (%d vectores).", self.index.ntotal)
            except Exception as e:
                logger.error("Fallo al cargar índice vectorial: %s", e)
