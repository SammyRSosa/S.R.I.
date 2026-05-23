"""
scripts/reindex_all.py
Orquestador de Indexación desde Cero (Cold Indexing Pipeline)
Sistemas de Recuperación de Información · Curso 2025-2026

Este script cumple con la penúltima directiva del profesor para la entrega del proyecto:
"Antes de crear el video, todos los datos almacenados en cada sistema deben eliminarse. 
La carga del sistema debe de indexar su corpus inicial como un paso requerido."

Uso:
    python scripts/reindex_all.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from database.store import DocumentStore
from indexer.inverted_index import InvertedIndex
from indexer.ebm import ExtendedBooleanModel
from database.vector_store import VectorStore

# Configuración de Logging elegante
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("reindex_all")

def delete_file_if_exists(path: Path) -> None:
    if path.exists():
        try:
            path.unlink()
            logger.info("  ↳ Eliminado archivo indexado previo: %s", path.name)
        except Exception as e:
            logger.error("  ↳ Error eliminando %s: %s", path.name, e)

def main():
    logger.info("=" * 70)
    logger.info("  COGNITIVE RE-INDEXATION PIPELINE — COLD STARTUP DEMONSTRATION")
    logger.info("=" * 70)
    
    data_dir = ROOT / "data"
    
    # ── PASO 1: ELIMINACIÓN DE DATOS PREVIOS (ÍNDICES) ───────────────────────
    logger.info("Paso 1: Eliminando índices y pesos pre-calculados previos...")
    
    files_to_delete = [
        data_dir / "index.json",
        data_dir / "ebm_weights.json",
        data_dir / "faiss_index.bin",
        data_dir / "vector_mapping.json",
        data_dir / "checkpoint.json",
    ]
    
    for file_path in files_to_delete:
        delete_file_if_exists(file_path)
        
    logger.info("  ✓ Estado inicial de búsqueda local completamente limpio.")
    
    # ── PASO 2: COMPROBACIÓN DEL CORPUS INICIAL ─────────────────────────────
    logger.info("\nPaso 2: Comprobando existencia del corpus inicial (documents.json)...")
    store = DocumentStore(data_dir)
    
    if not store.documents:
        logger.error("  ❌ ERROR CRÍTICO: No se encontró 'data/documents.json' o está vacío.")
        logger.error("  Asegúrate de tener el corpus de 1,650 películas listo antes de correr este script.")
        sys.exit(1)
        
    n_docs = len(store.documents)
    logger.info("  ✓ Corpus inicial detectado: %d documentos de películas cargados.", n_docs)
    
    t0 = time.time()
    
    # ── PASO 3: INDEXACIÓN LÉXICA (INVERTED INDEX) ─────────────────────────
    logger.info("\nPaso 3: Construyendo Índice Invertido Léxico y normalizando tokens (NLP)...")
    idx = InvertedIndex(language="english")
    
    # Agregar todos los documentos del corpus al índice
    for doc_id, film in store.documents.items():
        # Schema v2 compatible
        rich_text = film.get("rich_text", "")
        if not rich_text:
            # Reconstruir en caliente si es un formato legado
            rich_text = store.get_rich_text(doc_id)
        idx.add_document(doc_id, rich_text)
        
    # Guardar index.json en disco
    store.save_index(idx.index)
    vocab_size = idx.vocabulary_size
    logger.info("  ✓ Índice Invertido guardado con éxito. Tamaño del vocabulario: %d términos únicos.", vocab_size)
    
    # ── PASO 4: CÁLCULO DE PESOS EBM (TF-IDF NORMALIZADO) ───────────────────
    logger.info("\nPaso 4: Inicializando Extended Boolean Model y pre-calculando matriz de pesos TF-IDF normalizados...")
    ebm = ExtendedBooleanModel(store, idx, p=2.0)
    ebm.build_weights()
    logger.info("  ✓ Pesos EBM construidos y guardados en 'data/ebm_weights.json'.")
    
    # ── PASO 5: INDEXACIÓN VECTORIAL SEMÁNTICA (FAISS INDEX FLAT IP) ─────────
    logger.info("\nPaso 5: Codificando embeddings semánticos mediante el modelo multilingüe...")
    logger.info("  Lanzando codificación de %d documentos densos en FAISS (esto tomará ~1-2 minutos en CPU)...", n_docs)
    
    try:
        v_store = VectorStore(data_dir)
        v_store.build_from_documents(store.documents)
        logger.info("  ✓ Índice Vectorial FAISS construido y guardado en 'data/faiss_index.bin'.")
    except Exception as e:
        logger.error("  ❌ Error construyendo el índice vectorial: %s", e)
        sys.exit(1)
        
    duration = time.time() - t0
    
    logger.info("\n" + "=" * 70)
    logger.info("  ✓ ¡INDEXACIÓN COMPLETA COMPLETADA EXITOSAMENTE!")
    logger.info("=" * 70)
    logger.info("  Estadísticas del Sistema:")
    logger.info("    - Documentos Indexados : %d películas", n_docs)
    logger.info("    - Términos Normalizados : %d vocabulario", vocab_size)
    logger.info("    - Espacio Vectorial    : 384 dimensiones (Multilingual-MiniLM)")
    logger.info("    - Tiempo de Cómputo    : %.2f segundos (%.3f s/doc)", duration, duration / n_docs)
    logger.info("  Archivos Generados:")
    logger.info("    1. [Léxico]    data/index.json")
    logger.info("    2. [EBM Pesos] data/ebm_weights.json")
    logger.info("    3. [Vectores]  data/faiss_index.bin & vector_mapping.json")
    logger.info("=" * 70)
    logger.info("  ¡El sistema está 100% listo para arrancar y ser grabado en el video! 🚀")
    logger.info("=" * 70 + "\n")

if __name__ == "__main__":
    main()
