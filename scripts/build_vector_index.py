"""
scripts/build_vector_index.py
Construye el índice vectorial local (FAISS) usando el modelo multilingüe.
"""

import sys
from pathlib import Path

# Agregar la raíz del proyecto al path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import logging
from database.store import DocumentStore
from database.vector_store import VectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    store = DocumentStore()
    if not store.documents:
        logger.error("No hay documentos en la base de datos local para vectorizar.")
        return
        
    logger.info(f"Cargados {len(store.documents)} documentos locales.")
    
    logger.info("Inicializando VectorStore (esto descargará el modelo multilingüe si es la primera vez)...")
    v_store = VectorStore(store.data_dir)
    
    logger.info("Construyendo índice FAISS. Esto tomará un par de minutos...")
    v_store.build_from_documents(store.documents)
    
    logger.info("¡Índice vectorial construido y guardado con éxito!")

if __name__ == "__main__":
    main()
