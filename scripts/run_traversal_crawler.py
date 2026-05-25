"""
scripts/run_traversal_crawler.py
Orquestador de Ejecución de Link-Traversal Focused Crawler.
Sistemas de Recuperación de Información · MatCom · Curso 2025-2026.

Este script inicializa todos los componentes de la arquitectura (DocumentStore,
InvertedIndex, ExtendedBooleanModel, VectorStore) y arranca el crawler en anchura (BFS)
sobre Metacritic con políticas controladas de parada y rate limiting.

Uso:
    python scripts/run_traversal_crawler.py --limit 5
    python scripts/run_traversal_crawler.py --limit 50  (Ejecución completa)
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── Forzar UTF-8 en Windows ───────────────────────────────────────────────────
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Configurar logging detallado del orquestador y crawler
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_traversal_crawler")

from database.store import DocumentStore
from database.vector_store import VectorStore
from indexer.ebm import ExtendedBooleanModel
from indexer.inverted_index import InvertedIndex
from crawler.metacritic_spider import MetacriticTraversalSpider


def main() -> None:
    parser = argparse.ArgumentParser(description="Orquestador del Link-Traversal Focused Crawler de Metacritic.")
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Número máximo de nuevas películas a descubrir e indexar antes de detener el crawler (default: 50)."
    )
    parser.add_argument(
        "--reviews-limit",
        type=int,
        default=10,
        help="Número máximo de críticas de usuario por película (default: 10)."
    )
    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("  INICIALIZANDO COMPONENTES DE BÚSQUEDA Y ALMACENAMIENTO (OSCAR SEARCH)")
    logger.info("=" * 80)

    data_dir = ROOT / "data"

    # 1. Cargar DocumentStore
    logger.info("[INIT] Cargando DocumentStore de películas...")
    store = DocumentStore(data_dir)
    initial_docs = len(store.documents)
    logger.info("[INIT] ✓ DocumentStore cargado con %d películas.", initial_docs)

    # 2. Inicializar y popular InvertedIndex desde disco
    logger.info("[INIT] Inicializando InvertedIndex...")
    idx = InvertedIndex(language="english")
    
    # Rellenar documentos originales en el índice
    for doc_id in store.documents.keys():
        idx.documents[doc_id] = store.get_rich_text(doc_id)
        
    # Cargar listas de postings guardadas de documents.json e index.json
    logger.info("[INIT] Cargando y mapeando posting lists de index.json...")
    raw_index = store.load_index()
    for term, postings in raw_index.items():
        idx._raw_index[term] = dict(postings)
    logger.info("[INIT] ✓ InvertedIndex cargado con %d términos únicos.", idx.vocabulary_size)

    # 3. Cargar pesos de ExtendedBooleanModel
    logger.info("[INIT] Inicializando ExtendedBooleanModel...")
    ebm = ExtendedBooleanModel(store, idx, p=2.0)
    logger.info("[INIT] ✓ Pesos del modelo EBM cargados correctamente.")

    # 4. Cargar VectorStore (FAISS + MiniLM)
    logger.info("[INIT] Inicializando VectorStore y cargando índice FAISS...")
    v_store = VectorStore(data_dir)
    logger.info("[INIT] ✓ Índice vectorial FAISS cargado con %d vectores.", v_store.index.ntotal)

    # 5. Lanzar MetacriticTraversalSpider
    logger.info("\n" + "=" * 80)
    logger.info(f"  ARRANCANDO SPIDER: LÍMITE DE NUEVOS FILMS = {args.limit} | CRÍTICAS/FILM = {args.reviews_limit}")
    logger.info("=" * 80)

    t0 = time.time()
    
    spider = MetacriticTraversalSpider(
        store=store,
        inverted_index=idx,
        ebm_model=ebm,
        vector_store=v_store,
        max_discoveries=args.limit,
        max_reviews_per_movie=args.reviews_limit
    )

    try:
        spider.run()
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Ejecución cancelada por el usuario de forma segura. Volcando buffer e indexando...")
        spider.flush_buffer()
    except Exception as e:
        logger.error("\n❌ Error crítico durante la ejecución del crawler: %s", e, exc_info=True)
        spider.flush_buffer()
    finally:
        elapsed = time.time() - t0
        final_docs = len(store.documents)
        new_films = final_docs - initial_docs
        
        logger.info("\n" + "=" * 80)
        logger.info("  EJECUCIÓN DEL CRAWLER COMPLETADA EXITOSAMENTE")
        logger.info("=" * 80)
        logger.info("  Estadísticas de la Sesión:")
        logger.info("    - Películas Iniciales : %d", initial_docs)
        logger.info("    - Películas Nuevas    : %d", new_films)
        logger.info("    - Películas Finales   : %d", final_docs)
        logger.info("    - Vocabulario Final   : %d términos", idx.vocabulary_size)
        logger.info("    - Vectores en FAISS   : %d vectores", v_store.index.ntotal)
        logger.info("    - Tiempo transcurrido : %.2f segundos", elapsed)
        logger.info("=" * 80)


if __name__ == "__main__":
    main()
