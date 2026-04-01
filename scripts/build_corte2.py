"""
scripts/build_corte2.py
Oscar Insight Search (Corte 2)

Construye los pesos TF-IDF para el Modelo Booleano Extendido (EBM) y
genera los embeddings FAISS (all-MiniLM-L6-v2) sobre la base documental enriquecida de Metacritic.
"""

import sys
from pathlib import Path
import logging

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from database.store import DocumentStore
from indexer.inverted_index import InvertedIndex
from database.vector_store import VectorStore
from indexer.ebm import ExtendedBooleanModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def main():
    store = DocumentStore()
    
    if not store.documents:
        logger.error("La base de datos está vacía. Ejecuta populator y enrich_reviews primero.")
        sys.exit(1)
        
    logger.info("Cargando %d documentos en el índice TF...", len(store.documents))
    
    idx = InvertedIndex()
    for doc_id, data in store.documents.items():
        idx.add_film(doc_id, data)
        
    logger.info("Índice base generado. Términos: %d.", idx.vocabulary_size)
    
    # ── 1. Construir pesos EBM (TF-IDF normalizado) ──
    logger.info("Inicializando modelo EBM...")
    ebm = ExtendedBooleanModel(store, idx, p=2.0)
    ebm.build_weights()
    
    # ── 2. Construir modelo FAISS (Vectores) ──
    logger.info("Inicializando modelo Vectorial Sentence-Transformers + FAISS...")
    v_store = VectorStore()
    v_store.build_from_documents(store.documents)
    
    logger.info("✅ Construcción finalizada. EBM y FAISS persistidos en disco.")

if __name__ == "__main__":
    main()
