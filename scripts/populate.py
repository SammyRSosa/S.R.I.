"""
scripts/populate.py
Script de Población de la Base de Datos — Oscar Insight Search (SRI 2025-2026)

Uso:
    # Desde la raíz del proyecto
    python scripts/populate.py

    # Para añadir solo algunos años:
    python scripts/populate.py --years 2023 2024

    # Sin hacer scraping real (usa datos ficticios para pruebas rápidas):
    python scripts/populate.py --mock

Descripción:
    1. Itera sobre una lista de URLs de Letterboxd de películas nominadas al Oscar.
    2. Extrae metadatos vía LetterboxdScraper.
    3. Almacena cada película en DocumentStore (data/documents.json).
    4. Construye el InvertedIndex y lo persiste (data/index.json).
    5. Imprime un resumen al terminar.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Asegurar que el root del proyecto esté en sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from crawler import LetterboxdScraper
from database import DocumentStore
from indexer import InvertedIndex

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("populate")

# ─── Corpus de películas nominadas al Oscar ────────────────────────────────────
# Estas URLs corresponden a películas reales nominadas. Extiende esta lista
# según el corpus que necesites para el proyecto.
OSCAR_FILMS: list[dict] = [
    # ── Premios Oscar 2024 (96ª ceremonia) ────────────────────────────────────
    {"url": "https://letterboxd.com/film/oppenheimer-2023/",      "year": 2024},
    {"url": "https://letterboxd.com/film/poor-things-2023/",      "year": 2024},
    {"url": "https://letterboxd.com/film/anatomy-of-a-fall/",     "year": 2024},
    {"url": "https://letterboxd.com/film/the-zone-of-interest/",  "year": 2024},
    {"url": "https://letterboxd.com/film/barbie-2023/",            "year": 2024},
    {"url": "https://letterboxd.com/film/maestro-2023/",           "year": 2024},
    {"url": "https://letterboxd.com/film/killers-of-the-flower-moon/", "year": 2024},
    {"url": "https://letterboxd.com/film/past-lives/",             "year": 2024},
    {"url": "https://letterboxd.com/film/american-fiction/",       "year": 2024},
    {"url": "https://letterboxd.com/film/the-holdovers/",          "year": 2024},
    # ── Premios Oscar 2023 (95ª ceremonia) ────────────────────────────────────
    {"url": "https://letterboxd.com/film/everything-everywhere-all-at-once/", "year": 2023},
    {"url": "https://letterboxd.com/film/tár/",                    "year": 2023},
    {"url": "https://letterboxd.com/film/the-fabelmans/",          "year": 2023},
    {"url": "https://letterboxd.com/film/all-quiet-on-the-western-front-2022/", "year": 2023},
    {"url": "https://letterboxd.com/film/the-whale-2022/",         "year": 2023},
    # ── Premios Oscar 2022 (94ª ceremonia) ────────────────────────────────────
    {"url": "https://letterboxd.com/film/coda-2021/",              "year": 2022},
    {"url": "https://letterboxd.com/film/the-power-of-the-dog/",   "year": 2022},
    {"url": "https://letterboxd.com/film/dune-2021/",              "year": 2022},
    {"url": "https://letterboxd.com/film/belfast/",                "year": 2022},
    {"url": "https://letterboxd.com/film/licorice-pizza/",         "year": 2022},
]

# ─── Datos ficticios para pruebas sin conexión (--mock) ───────────────────────
MOCK_FILMS: list[dict] = [
    {
        "title": "Oppenheimer",
        "year": "2023",
        "synopsis": (
            "The story of J. Robert Oppenheimer's role in the development of "
            "the atomic bomb during World War II."
        ),
        "reviews": [
            "A masterpiece of epic cinema. Nolan at his absolute best.",
            "Cillian Murphy delivers an Oscar-worthy performance.",
            "The IMAX sequences are breathtaking. A must-see on the big screen.",
            "Dense, complex, and utterly fascinating.",
            "One of the best films of the decade.",
        ],
        "source_url": "https://letterboxd.com/film/oppenheimer-2023/",
    },
    {
        "title": "Poor Things",
        "year": "2023",
        "synopsis": (
            "The incredible tale about the fantastical evolution of Bella Baxter, "
            "a young woman brought back to life by the brilliant and unorthodox "
            "scientist Dr. Godwin Baxter."
        ),
        "reviews": [
            "Emma Stone is absolutely incredible. What a performance.",
            "Visually stunning and wildly original. Yorgos Lanthimos at his peak.",
            "A feminist fable told with dark humor and gorgeous imagery.",
            "Bizarre, funny, and deeply moving.",
            "Best film I've seen in years.",
        ],
        "source_url": "https://letterboxd.com/film/poor-things-2023/",
    },
    {
        "title": "Everything Everywhere All at Once",
        "year": "2022",
        "synopsis": (
            "A middle-aged Chinese immigrant is swept up into an insane adventure "
            "where she alone can save existence by exploring other universes."
        ),
        "reviews": [
            "A chaotic, beautiful, tear-jerking multiverse adventure.",
            "Michelle Yeoh gives the performance of her career.",
            "Unlike anything I've ever seen. Completely original.",
            "Funny, heartfelt, and mind-bending.",
            "Best Picture winner that actually deserved it.",
        ],
        "source_url": "https://letterboxd.com/film/everything-everywhere-all-at-once/",
    },
    {
        "title": "The Zone of Interest",
        "year": "2023",
        "synopsis": (
            "The commandant of Auschwitz, Rudolf Höss, and his wife strive to "
            "build a dream life for their family next to the concentration camp."
        ),
        "reviews": [
            "Disturbing and haunting in the most understated way.",
            "Glazer's direction is cold and clinical, which makes it more terrifying.",
            "A Holocaust film unlike any other.",
            "The sound design alone is Oscar-worthy.",
            "Deeply unsettling and important.",
        ],
        "source_url": "https://letterboxd.com/film/the-zone-of-interest/",
    },
    {
        "title": "Anatomy of a Fall",
        "year": "2023",
        "synopsis": (
            "A woman is suspected of her husband's murder and her 11 year-old son, "
            "visually impaired, must face questions about his parents."
        ),
        "reviews": [
            "Sandra Hüller is mesmerizing. Best screenplay of the year.",
            "A legal thriller that's also a deep character study.",
            "Palme d'Or-winning masterpiece.",
            "Gripping from start to finish.",
            "The courtroom scenes are electrifying.",
        ],
        "source_url": "https://letterboxd.com/film/anatomy-of-a-fall/",
    },
]


# ─── Funciones principales ─────────────────────────────────────────────────────

def populate_mock(store: DocumentStore, idx: InvertedIndex) -> None:
    """Llena la base de datos con datos ficticios (sin conexión a internet)."""
    logger.info("Modo MOCK activado — usando %d películas de prueba.", len(MOCK_FILMS))
    for film_data in MOCK_FILMS:
        doc_id = store.add_film(film_data)
        idx.add_film(doc_id, film_data)
        print(f"  ✅ [{doc_id:>2}] {film_data['title']} ({film_data['year']})")


def populate_real(
    store: DocumentStore,
    idx: InvertedIndex,
    year_filter: list[int] | None = None,
) -> None:
    """Llena la base de datos haciendo scraping real de Letterboxd."""
    scraper = LetterboxdScraper()

    films_to_scrape = OSCAR_FILMS
    if year_filter:
        films_to_scrape = [f for f in OSCAR_FILMS if f["year"] in year_filter]

    logger.info("Iniciando scraping de %d películas...", len(films_to_scrape))

    for i, entry in enumerate(films_to_scrape, start=1):
        url = entry["url"]
        try:
            print(f"\n[{i:>2}/{len(films_to_scrape)}] Procesando: {url}")
            film_data = scraper.scrape_film(url)
            doc_id = store.add_film(film_data)
            idx.add_film(doc_id, film_data)
            print(
                f"  ✅ doc_id={doc_id} | {film_data['title']} ({film_data['year']}) | "
                f"reviews={len(film_data['reviews'])}"
            )
        except PermissionError as e:
            print(f"  🚫 robots.txt bloqueó: {url}")
            logger.warning(str(e))
        except Exception as e:
            print(f"  ❌ Error en {url}: {e}")
            logger.error("Error al procesar %s: %s", url, e)

        # Delay adicional entre películas para ser respetuoso con el servidor
        if i < len(films_to_scrape):
            time.sleep(1.0)


def print_summary(store: DocumentStore, idx: InvertedIndex) -> None:
    """Imprime un resumen del estado de la base de datos."""
    print("\n" + "═" * 60)
    print("  RESUMEN — Oscar Insight Search Database")
    print("═" * 60)
    stats = store.stats()
    print(f"  📁 Documentos almacenados : {stats['total_documents']}")
    print(f"  📚 Términos en el índice  : {idx.vocabulary_size}")
    print(f"  📂 Carpeta de datos       : {stats['data_dir']}")
    print(f"  🗄️  Archivo de documentos  : {stats['documents_file']}")
    print(f"  🔍 Archivo de índice      : {stats['index_file']}")
    print("═" * 60)

    if idx.vocabulary_size > 0:
        # Mostrar muestra de términos más frecuentes
        sorted_terms = sorted(
            idx.index.items(),
            key=lambda x: sum(freq for _, freq in x[1]),
            reverse=True,
        )[:10]
        print("\n  Top 10 términos en el índice:")
        for term, postings in sorted_terms:
            total_tf = sum(freq for _, freq in postings)
            print(f"    '{term}' → aparece en {len(postings)} doc(s), tf_total={total_tf}")

    print("\n  Ejemplo de consulta con el índice cargado:")
    print("    from indexer import InvertedIndex")
    print("    from database import DocumentStore")
    print("    store = DocumentStore()          # carga automáticamente")
    print("    postings = ...                   # ver scripts/query.py")
    print()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pobla la base de datos de Oscar Insight Search.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/populate.py --mock           # Rápido, sin internet
  python scripts/populate.py                 # Scraping real (todos los años)
  python scripts/populate.py --years 2024    # Solo películas de 2024
  python scripts/populate.py --years 2023 2024 --verbose
        """,
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Usar datos ficticios (sin conexión a internet).",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        metavar="YEAR",
        help="Filtrar por año de ceremonia Oscar (ej: --years 2023 2024).",
    )
    parser.add_argument(
        "--data-dir",
        default=str(ROOT / "data"),
        help="Directorio donde guardar los archivos JSON.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Activar logging detallado (DEBUG).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    print("\n🎬 Oscar Insight Search — Población de Base de Datos")
    print(f"   Modo: {'MOCK (sin internet)' if args.mock else 'REAL (Letterboxd)'}")
    if args.years:
        print(f"   Años: {args.years}")
    print()

    # Inicializar componentes
    store = DocumentStore(data_dir=args.data_dir)
    idx = InvertedIndex(language="english")

    # Si ya hay documentos en el store, re-indexarlos para no perder el índice
    if store.documents:
        print(f"ℹ️  Store existente: {len(store.documents)} documentos. Reindexando...")
        for doc_id, film_data in store.documents.items():
            idx.add_film(doc_id, film_data)

    # Poblar según el modo
    if args.mock:
        populate_mock(store, idx)
    else:
        populate_real(store, idx, year_filter=args.years)

    # Persistir
    print("\n💾 Guardando en disco...")
    store.save()
    store.save_index(idx.index)

    # Resumen
    print_summary(store, idx)


if __name__ == "__main__":
    main()
