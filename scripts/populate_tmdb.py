"""
scripts/populate_tmdb.py
Orquestador Principal — Oscar Insight Search (SRI 2025-2026)

Pobla la base de datos con 2000+ películas usando:
  1. TMDB API → metadatos estructurados (director, cast, genres, budget, revenue)
  2. Letterboxd → texto rico de 15-20 reseñas de usuarios por película

Estrategia de adquisición (A + B combinadas):
  - Estrategia A: popularity.desc (primeras N páginas)   → películas muy conocidas
  - Estrategia B: vote_average.desc + vote_count≥500 (siguientes M páginas) → calidad

Filtros de calidad:
  - vote_count >= 50  (películas con suficiente feedback)
  - overview no vacío (necesitamos sinopsis para el índice)
  - reviews_count >= min_reviews (texto suficiente para lenguaje natural)

Checkpointing: guarda el estado cada SAVE_EVERY documentos. Si el proceso
se interrumpe, reanuda desde donde se quedó con --resume.

Uso:
    python scripts/populate_tmdb.py --api-key KEY
    python scripts/populate_tmdb.py --api-key KEY --pages 100 --resume
    python scripts/populate_tmdb.py --api-key KEY --pages 5 --no-reviews   # prueba rápida
    python scripts/populate_tmdb.py --api-key KEY --reset --pages 100      # desde cero

Variables de entorno:
    TMDB_API_KEY      → API key de TMDB v3
    TMDB_ACCESS_TOKEN → Bearer token de TMDB v3/v4
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── Forzar UTF-8 en Windows ───────────────────────────────────────────────────
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from crawler.tmdb_client import TmdbClient
from crawler.scraper     import LetterboxdReviewScraper
from database.checkpoint import Checkpoint
from database            import DocumentStore
from indexer             import InvertedIndex

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("populate_tmdb")

# ─── Configuración de guardado ────────────────────────────────────────────────
CHECKPOINT_EVERY = 25    # Guardar checkpoint cada N documentos indexados
SAVE_DB_EVERY    = 50    # Guardar DB a disco cada N documentos indexados


# ─── Builder de rich_text ─────────────────────────────────────────────────────

def build_rich_text(details: dict, reviews: list[str]) -> str:
    """
    Construye el campo rich_text concatenando todos los campos textuales.

    Orden pensado para dar más peso a los elementos más descriptivos:
      titulo | tagline | generos | director | cast | sinopsis completa | reseñas

    Este es el texto que se tokeniza e indexa — debe ser rico en lenguaje natural.
    """
    parts: list[str] = []

    # Título (repetido para dar peso)
    title = details.get("title", "")
    if title:
        parts.append(title)
        parts.append(title)   # doble peso al título

    # Tagline (a veces muy descriptivo)
    tagline = details.get("tagline", "")
    if tagline:
        parts.append(tagline)

    # Géneros
    genres = details.get("genres", [])
    if genres:
        parts.append(" ".join(genres))

    # Director
    director = details.get("director", "")
    if director:
        parts.append(director)

    # Cast (top 10)
    cast = details.get("cast", [])
    if cast:
        parts.append(" ".join(cast[:10]))

    # Sinopsis (texto más largo y descriptivo)
    overview = details.get("overview", "")
    if overview:
        parts.append(overview)

    # Reseñas (texto más rico en lenguaje natural)
    for review in reviews:
        if review and len(review) >= 30:
            parts.append(review)

    return " ".join(parts)


def build_document(details: dict, reviews: list[str]) -> dict:
    """
    Construye el objeto JSON final a almacenar en el DocumentStore.

    Schema v2:
        {title, year, metadata: {...}, rich_text: str, reviews_count: int}
    """
    metadata = {
        "director":          details.get("director", ""),
        "cast":              details.get("cast", []),
        "genres":            details.get("genres", []),
        "budget":            details.get("budget", 0),
        "revenue":           details.get("revenue", 0),
        "vote_average":      details.get("vote_average", 0),
        "vote_count":        details.get("vote_count", 0),
        "original_language": details.get("original_language", ""),
        "imdb_id":           details.get("imdb_id", ""),
        "tmdb_id":           details.get("tmdb_id"),
        "source_url":        details.get("source_url", ""),
        "tagline":           details.get("tagline", ""),
        "runtime":           details.get("runtime", 0),
        "original_title":    details.get("original_title", ""),
    }

    return {
        "title":         details.get("title", ""),
        "year":          details.get("year", ""),
        "metadata":      metadata,
        "rich_text":     build_rich_text(details, reviews),
        "reviews_count": len(reviews),
    }


# ─── Proceso principal ────────────────────────────────────────────────────────

def process_page(
    films_basic: list[dict],
    tmdb: TmdbClient,
    review_scraper: LetterboxdReviewScraper | None,
    store: DocumentStore,
    idx: InvertedIndex,
    checkpoint: Checkpoint,
    args: argparse.Namespace,
    stats: dict,
) -> None:
    """
    Procesa una lista de films básicos de una página de TMDB.
    Obtiene detalles, reviews, filtra y añade al store e índice.
    """
    for film_basic in films_basic:
        tmdb_id   = film_basic["tmdb_id"]
        title     = film_basic["title"]
        year      = film_basic["year"]
        overview  = film_basic["overview"]

        # ── Deduplicación ─────────────────────────────────────────────────
        if checkpoint.is_processed(tmdb_id):
            stats["skipped"] += 1
            continue

        # ── Filtro básico antes de pedir detalles ─────────────────────────
        if film_basic["vote_count"] < args.min_votes:
            stats["filtered_votes"] += 1
            checkpoint.mark_failed(tmdb_id)   # No reintentar
            continue

        if not overview or len(overview) < 50:
            stats["filtered_no_overview"] += 1
            checkpoint.mark_failed(tmdb_id)
            continue

        # ── Obtener detalles completos de TMDB ────────────────────────────
        try:
            details = tmdb.get_movie_details(tmdb_id)
        except Exception as exc:
            logger.warning("[TMDB] Error detalles tmdb_id=%d '%s': %s", tmdb_id, title, exc)
            stats["errors_tmdb"] += 1
            checkpoint.mark_failed(tmdb_id)
            continue

        # Filtro de idioma (solo inglés para máxima cobertura en Letterboxd)
        if details.get("original_language", "en") != "en":
            stats["filtered_lang"] += 1
            checkpoint.mark_failed(tmdb_id)
            continue

        # ── Obtener reviews de Letterboxd ─────────────────────────────────
        reviews: list[str] = []
        imdb_id = details.get("imdb_id", "")

        if not args.no_reviews and review_scraper is not None:
            try:
                reviews = review_scraper.get_reviews(
                    title=title,
                    year=int(year) if year else None,
                    imdb_id=imdb_id or None,
                    max_reviews=args.max_reviews,
                )
            except Exception as exc:
                logger.debug("[Letterboxd] Error en '%s': %s", title, exc)
                # No es fatal — continuamos con 0 reviews

        # ── Filtro final: texto suficiente ────────────────────────────────
        if len(reviews) < args.min_reviews and not args.no_reviews:
            # Si tiene overview larga (≥300 chars), la aceptamos sin reviews
            if len(details.get("overview", "")) < 300:
                stats["filtered_no_reviews"] += 1
                checkpoint.mark_failed(tmdb_id)
                continue

        # ── Construir y almacenar ─────────────────────────────────────────
        film_doc = build_document(details, reviews)
        doc_id   = store.add_film(film_doc)
        idx.add_film(doc_id, film_doc)

        checkpoint.mark_done(tmdb_id)
        checkpoint.total_indexed += 1
        stats["indexed"] += 1

        # ── Progreso ──────────────────────────────────────────────────────
        genres_str   = ", ".join(details.get("genres", [])[:3])
        director_str = details.get("director", "?")[:20]
        print(
            f"  [{stats['indexed']:>4}] {title} ({year})"
            f" | dir: {director_str}"
            f" | genres: {genres_str}"
            f" | reviews: {len(reviews)}"
        )

        # ── Guardado incremental ──────────────────────────────────────────
        if checkpoint.total_indexed % CHECKPOINT_EVERY == 0:
            checkpoint.save()

        if checkpoint.total_indexed % SAVE_DB_EVERY == 0:
            store.save()
            store.save_index(idx.index)
            print(f"\n  === Guardado incremental: {checkpoint.total_indexed} docs | {idx.vocabulary_size} términos ===\n")


# ─── Main ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pobla la DB de Oscar Insight Search con TMDB + Letterboxd.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/populate_tmdb.py --api-key KEY                         # Popularidad, 100 pag
  python scripts/populate_tmdb.py --api-key KEY --pages 5 --no-reviews  # Prueba rapida
  python scripts/populate_tmdb.py --api-key KEY --pages 100 --resume    # Reanudar
  python scripts/populate_tmdb.py --api-key KEY --reset --pages 100     # Empezar de cero

Obtener API KEY gratis: https://www.themoviedb.org/settings/api
        """,
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("TMDB_API_KEY", ""),
        help="API key de TMDB v3 (o usa TMDB_API_KEY env var).",
    )
    parser.add_argument(
        "--access-token",
        default=os.environ.get("TMDB_ACCESS_TOKEN", ""),
        help="Bearer access token de TMDB (alternativo a api-key).",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=100,
        help="Páginas de TMDB a procesar por estrategia (default: 100 → ~2000 films).",
    )
    parser.add_argument(
        "--pages-popularity",
        type=int,
        default=None,
        help="Páginas solo para estrategia A (popularity). Default: --pages * 0.6.",
    )
    parser.add_argument(
        "--pages-quality",
        type=int,
        default=None,
        help="Páginas solo para estrategia B (quality). Default: --pages * 0.4.",
    )
    parser.add_argument(
        "--max-reviews",
        type=int,
        default=15,
        help="Máximo de reviews a obtener por película (default: 15).",
    )
    parser.add_argument(
        "--min-reviews",
        type=int,
        default=3,
        help="Mínimo de reviews para aceptar la película (default: 3). 0=sin filtro.",
    )
    parser.add_argument(
        "--min-votes",
        type=int,
        default=50,
        help="Mínimo de votos en TMDB para procesar la película (default: 50).",
    )
    parser.add_argument(
        "--no-reviews",
        action="store_true",
        help="No scrappear Letterboxd (solo metadata de TMDB). Más rápido, menos texto.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reanudar desde el checkpoint guardado.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Borrar DB y checkpoint antes de empezar.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(ROOT / "data"),
        help="Directorio donde guardar los archivos JSON.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Logging detallado (DEBUG).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ── Validar credenciales ───────────────────────────────────────────────
    if not args.api_key and not args.access_token:
        print("\nERROR: Se requiere API key de TMDB.")
        print("  Obtén una gratis en: https://www.themoviedb.org/settings/api")
        print("  Luego usa: --api-key TU_CLAVE")
        sys.exit(1)

    # ── Calcular páginas por estrategia ────────────────────────────────────
    pages_pop = args.pages_popularity or int(args.pages * 0.60)   # 60% popularidad
    pages_qua = args.pages_quality    or (args.pages - pages_pop)  # 40% calidad

    # ── Banner ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 68)
    print("  Oscar Insight Search -- Poblacion TMDB + Letterboxd")
    print("=" * 68)
    print(f"  Estrategia A (popularity):  {pages_pop} paginas x 20 = ~{pages_pop*20} films")
    print(f"  Estrategia B (quality):     {pages_qua} paginas x 20 = ~{pages_qua*20} films")
    print(f"  Max reviews/pelicula:       {args.max_reviews}")
    print(f"  Min reviews requeridas:     {0 if args.no_reviews else args.min_reviews}")
    print(f"  Reviews Letterboxd:         {'NO (--no-reviews)' if args.no_reviews else 'SI'}")
    print(f"  Modo:                       {'RESUME' if args.resume else 'NUEVO'}")
    print("=" * 68 + "\n")

    # ── Inicializar componentes ────────────────────────────────────────────
    checkpoint = Checkpoint(Path(args.data_dir) / "checkpoint.json")
    store      = DocumentStore(data_dir=args.data_dir)
    idx        = InvertedIndex(language="english")

    if args.reset:
        print("  [RESET] Borrando base de datos y checkpoint...")
        checkpoint.reset()
        import os as _os
        for fname in ["documents.json", "index.json"]:
            fp = Path(args.data_dir) / fname
            if fp.exists():
                _os.remove(fp)
                print(f"  Eliminado: {fp}")
        # Reinicializar tras reset
        store = DocumentStore(data_dir=args.data_dir)
        idx   = InvertedIndex(language="english")
        print()

    # Reindexar documentos existentes al arrancar (para no perder el índice)
    if store.documents:
        print(f"  Documentos existentes: {len(store.documents)}. Reindexando en memoria...")
        for doc_id, film_data in store.documents.items():
            idx.add_film(doc_id, film_data)
        print(f"  Indice reconstruido: {idx.vocabulary_size} terminos\n")

    if args.resume and checkpoint.stats()["processed"] > 0:
        print(f"  RESUME: {checkpoint.stats()['processed']} IDs ya procesados (se saltaran).")
        print(f"          Estrategia A: pagina {checkpoint.last_page_popularity}")
        print(f"          Estrategia B: pagina {checkpoint.last_page_quality}\n")

    # ── Instanciar clientes ────────────────────────────────────────────────
    tmdb = TmdbClient(
        api_key=args.api_key,
        access_token=args.access_token,
    )

    review_scraper: LetterboxdReviewScraper | None = None
    if not args.no_reviews:
        review_scraper = LetterboxdReviewScraper()

    stats = {
        "indexed":              0,
        "skipped":              0,
        "filtered_votes":       0,
        "filtered_no_overview": 0,
        "filtered_no_reviews":  0,
        "filtered_lang":        0,
        "errors_tmdb":          0,
    }

    # ── ESTRATEGIA A: Popularity ───────────────────────────────────────────
    start_page_pop = checkpoint.last_page_popularity + 1 if args.resume else 1

    print(f">>> ESTRATEGIA A: popularity.desc — paginas {start_page_pop}..{pages_pop}")
    for page in range(start_page_pop, pages_pop + 1):
        print(f"\n[A] Pagina {page}/{pages_pop} | idx={store.num_docs} | vocab={idx.vocabulary_size}")
        try:
            films = tmdb.discover_movies(page=page, strategy="popularity")
        except Exception as exc:
            logger.error("Error TMDB pagina A=%d: %s", page, exc)
            time.sleep(5)
            continue

        process_page(films, tmdb, review_scraper, store, idx, checkpoint, args, stats)
        checkpoint.last_page_popularity = page

        # Guardar checkpoint al final de cada página
        checkpoint.save()

    # ── ESTRATEGIA B: Quality (vote_average.desc) ──────────────────────────
    start_page_qua = checkpoint.last_page_quality + 1 if args.resume else 1

    print(f"\n>>> ESTRATEGIA B: vote_average.desc — paginas {start_page_qua}..{pages_qua}")
    for page in range(start_page_qua, pages_qua + 1):
        print(f"\n[B] Pagina {page}/{pages_qua} | idx={store.num_docs} | vocab={idx.vocabulary_size}")
        try:
            films = tmdb.discover_movies(page=page, strategy="quality")
        except Exception as exc:
            logger.error("Error TMDB pagina B=%d: %s", page, exc)
            time.sleep(5)
            continue

        process_page(films, tmdb, review_scraper, store, idx, checkpoint, args, stats)
        checkpoint.last_page_quality = page
        checkpoint.save()

    # ── Guardado final ─────────────────────────────────────────────────────
    print("\n  Guardando base de datos final...")
    store.save()
    store.save_index(idx.index)
    checkpoint.save()
    print("  Guardado completado.")

    # ── Resumen final ──────────────────────────────────────────────────────
    print("\n" + "=" * 68)
    print("  RESUMEN FINAL")
    print("=" * 68)
    print(f"  Indexadas correctamente : {stats['indexed']}")
    print(f"  Saltadas (duplicadas)   : {stats['skipped']}")
    print(f"  Filtradas (votos)       : {stats['filtered_votes']}")
    print(f"  Filtradas (sin sinopsis): {stats['filtered_no_overview']}")
    print(f"  Filtradas (sin reviews) : {stats['filtered_no_reviews']}")
    print(f"  Filtradas (idioma)      : {stats['filtered_lang']}")
    print(f"  Errores TMDB            : {stats['errors_tmdb']}")
    print(f"  --------------------------------")
    print(f"  TOTAL documentos en DB  : {store.num_docs}")
    print(f"  Terminos en el indice   : {idx.vocabulary_size}")
    print(f"  Objetivo (10.000 terms) : {'ALCANZADO' if idx.vocabulary_size >= 10000 else f'FALTA {10000 - idx.vocabulary_size}'}")
    print("=" * 68)

    if idx.vocabulary_size > 0:
        top = sorted(
            idx.index.items(),
            key=lambda x: sum(f for _, f in x[1]),
            reverse=True,
        )[:20]
        print("\n  Top 20 terminos en el indice:")
        for term, postings in top:
            print(f"    '{term}' -> {len(postings)} doc(s), tf={sum(f for _, f in postings)}")
    print()


if __name__ == "__main__":
    main()
