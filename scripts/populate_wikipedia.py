"""
scripts/populate_wikipedia.py
Población vía Wikipedia API — Oscar Insight Search (SRI 2025-2026)

Llena la base de datos con películas nominadas al Oscar usando la Wikipedia API.
No requiere clave de API y es completamente gratuita y ética.

Uso:
    # Desde la raíz del proyecto (entorno virtual activado)
    python scripts/populate_wikipedia.py

    # Solo películas de 2024 y 2023:
    python scripts/populate_wikipedia.py --years 2024 2023

    # Todo el corpus histórico 2019-2024:
    python scripts/populate_wikipedia.py --all

    # Limpiar la DB antes de poblar:
    python scripts/populate_wikipedia.py --reset

    # Modo verbose (debug):
    python scripts/populate_wikipedia.py --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

# ── Forzar UTF-8 en stdout/stderr en Windows (cp1252 no soporta caracteres ─────
# como ═ o 🎬 que usamos en los mensajes de progreso)
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from crawler.wikipedia_scraper import WikipediaScraper
from database import DocumentStore
from indexer import InvertedIndex

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("populate_wikipedia")

# ─── Corpus de Nominadas al Oscar (1991-2024) ──────────────────────────────────
#
# Formato: (wikipedia_article_title, release_year, oscar_ceremony_year)
# El título del artículo de Wikipedia se usa para obtener datos exactos
# (muchas películas tienen desambiguaciones como "X (film)" o "X (2023 film)").
#
OSCAR_CORPUS: list[tuple[str, int, int]] = [
    # ══ 97ª ceremonia (Oscar 2025) ══════════════════════════════════════════
    ("Anora (film)",                           2024, 2025),
    ("The Brutalist",                          2024, 2025),
    ("A Complete Unknown",                     2024, 2025),
    ("Conclave (film)",                        2024, 2025),
    ("Dune: Part Two",                         2024, 2025),
    ("Emilia Pérez",                           2024, 2025),
    ("I'm Still Here (2024 film)",             2024, 2025),
    ("Nickel Boys",                            2024, 2025),
    ("The Substance",                          2024, 2025),
    ("Wicked (2024 film)",                     2024, 2025),
    ("Maria (2024 film)",                      2024, 2025),
    ("September 5 (film)",                     2024, 2025),
    ("Sing Sing (film)",                       2024, 2025),
    ("The Room Next Door (film)",              2024, 2025),

    # ══ 96ª ceremonia (Oscar 2024) ══════════════════════════════════════════
    ("Oppenheimer (film)",                     2023, 2024),
    ("Poor Things (film)",                     2023, 2024),
    ("Anatomy of a Fall",                      2023, 2024),
    ("The Zone of Interest (film)",            2023, 2024),
    ("Barbie (film)",                          2023, 2024),
    ("Maestro (2023 film)",                    2023, 2024),
    ("Killers of the Flower Moon (film)",      2023, 2024),
    ("Past Lives (film)",                      2023, 2024),
    ("American Fiction (film)",                2023, 2024),
    ("The Holdovers",                          2023, 2024),
    ("Saltburn (film)",                        2023, 2024),
    ("Society of the Snow",                    2023, 2024),
    ("The Promised Land (2023 film)",          2023, 2024),
    ("Robot Dreams (film)",                    2023, 2024),
    ("20 Days in Mariupol",                    2023, 2024),

    # ══ 95ª ceremonia (Oscar 2023) ══════════════════════════════════════════
    ("Everything Everywhere All at Once",      2022, 2023),
    ("Tár",                                    2022, 2023),
    ("The Fabelmans",                          2022, 2023),
    ("All Quiet on the Western Front (2022 film)", 2022, 2023),
    ("The Whale (2022 film)",                  2022, 2023),
    ("Women Talking (film)",                   2022, 2023),
    ("The Banshees of Inisherin",              2022, 2023),
    ("Triangle of Sadness",                    2022, 2023),
    ("Avatar: The Way of Water",               2022, 2023),
    ("The Fabelmans",                          2022, 2023),
    ("Navalny (film)",                         2022, 2023),
    ("Pinocchio (2022 film)",                  2022, 2023),
    ("The Quiet Girl",                         2022, 2023),
    ("Argentina, 1985",                        2022, 2023),

    # ══ 94ª ceremonia (Oscar 2022) ══════════════════════════════════════════
    ("CODA (2021 film)",                       2021, 2022),
    ("The Power of the Dog (film)",            2021, 2022),
    ("Dune (2021 film)",                       2021, 2022),
    ("Belfast (film)",                         2021, 2022),
    ("Licorice Pizza",                         2021, 2022),
    ("Drive My Car (film)",                    2021, 2022),
    ("King Richard (film)",                    2021, 2022),
    ("Nightmare Alley (2021 film)",            2021, 2022),
    ("Spencer (film)",                         2021, 2022),
    ("The Lost Daughter (film)",               2021, 2022),
    ("Flee (film)",                            2021, 2022),
    ("The Hand of God (film)",                 2021, 2022),

    # ══ 93ª ceremonia (Oscar 2021) ══════════════════════════════════════════
    ("Nomadland (film)",                       2020, 2021),
    ("The Father (2020 film)",                 2020, 2021),
    ("Judas and the Black Messiah",            2020, 2021),
    ("Mank (film)",                            2020, 2021),
    ("Minari (film)",                          2020, 2021),
    ("Promising Young Woman",                  2020, 2021),
    ("Sound of Metal",                         2020, 2021),
    ("The Trial of the Chicago 7",             2020, 2021),
    ("Ma Rainey's Black Bottom (film)",        2020, 2021),
    ("Collective (film)",                      2019, 2021),

    # ══ 92ª ceremonia (Oscar 2020) ══════════════════════════════════════════
    ("Parasite (2019 film)",                   2019, 2020),
    ("1917 (film)",                            2019, 2020),
    ("Joker (2019 film)",                      2019, 2020),
    ("The Irishman",                           2019, 2020),
    ("Once Upon a Time in Hollywood",          2019, 2020),
    ("Marriage Story (film)",                  2019, 2020),
    ("Little Women (2019 film)",               2019, 2020),
    ("Ford v Ferrari",                         2019, 2020),
    ("Jojo Rabbit",                            2019, 2020),
    ("Pain and Glory",                         2019, 2020),
    ("Corpus Christi (2019 film)",             2019, 2020),

    # ══ 91ª ceremonia (Oscar 2019) ══════════════════════════════════════════
    ("Green Book (film)",                      2018, 2019),
    ("Roma (2018 film)",                       2018, 2019),
    ("A Star Is Born (2018 film)",             2018, 2019),
    ("The Favourite",                          2018, 2019),
    ("BlacKkKlansman",                         2018, 2019),
    ("Black Panther (film)",                   2018, 2019),
    ("Bohemian Rhapsody (film)",               2018, 2019),
    ("Vice (2018 film)",                       2018, 2019),
    ("Cold War (2018 film)",                   2018, 2019),
    ("Shoplifters",                            2018, 2019),

    # ══ 90ª ceremonia (Oscar 2018) ══════════════════════════════════════════
    ("The Shape of Water (film)",              2017, 2018),
    ("Three Billboards Outside Ebbing, Missouri", 2017, 2018),
    ("Get Out (film)",                         2017, 2018),
    ("Lady Bird (film)",                       2017, 2018),
    ("Dunkirk (2017 film)",                    2017, 2018),
    ("Phantom Thread",                         2017, 2018),
    ("Call Me by Your Name (film)",            2017, 2018),
    ("The Post (film)",                        2017, 2018),
    ("Darkest Hour (film)",                    2017, 2018),
    ("A Fantastic Woman",                      2017, 2018),
]

# Eliminamos duplicados manteniendo el orden de inserción
seen_titles: set[str] = set()
OSCAR_CORPUS_UNIQUE: list[tuple[str, int, int]] = []
for entry in OSCAR_CORPUS:
    if entry[0] not in seen_titles:
        seen_titles.add(entry[0])
        OSCAR_CORPUS_UNIQUE.append(entry)
OSCAR_CORPUS = OSCAR_CORPUS_UNIQUE


# ─── Funciones auxiliares ─────────────────────────────────────────────────────

def print_banner() -> None:
    print("\n" + "═" * 65)
    print("  🎬  Oscar Insight Search — Población vía Wikipedia API")
    print("═" * 65)


def print_summary(store: DocumentStore, idx: InvertedIndex, stats: dict) -> None:
    print("\n" + "═" * 65)
    print("  📊  RESUMEN FINAL")
    print("═" * 65)
    print(f"  ✅ Procesadas correctamente : {stats['ok']}")
    print(f"  ⚠️  No encontradas           : {stats['not_found']}")
    print(f"  🔄  Ya existían en la DB    : {stats['skipped']}")
    print(f"  ❌ Errores                  : {stats['errors']}")
    print(f"  📁 Total documentos en DB   : {len(store.documents)}")
    print(f"  📚 Términos en el índice    : {idx.vocabulary_size}")
    store_stats = store.stats()
    print(f"  📂 Carpeta de datos         : {store_stats['data_dir']}")
    print("═" * 65)

    if idx.vocabulary_size > 0:
        top = sorted(
            idx.index.items(),
            key=lambda x: sum(f for _, f in x[1]),
            reverse=True,
        )[:15]
        print("\n  🔝 Top 15 términos en el índice:")
        for term, postings in top:
            tf_total = sum(f for _, f in postings)
            print(f"    '{term}' → {len(postings)} doc(s), tf={tf_total}")
    print()


def reset_database(data_dir: str) -> None:
    """Borra los archivos JSON de la base de datos para empezar desde cero."""
    import os
    data_path = Path(data_dir)
    for fname in ["documents.json", "index.json"]:
        fpath = data_path / fname
        if fpath.exists():
            os.remove(fpath)
            print(f"  🗑️  Eliminado: {fpath}")
    print("  Base de datos reseteada.\n")


# ─── CLI & Main ───────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pobla la DB de Oscar Insight Search usando Wikipedia API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/populate_wikipedia.py                      # Últimas 2 ceremonias
  python scripts/populate_wikipedia.py --years 2024 2025   # Ceremonia específica
  python scripts/populate_wikipedia.py --all               # Todo el corpus (2018-2025)
  python scripts/populate_wikipedia.py --reset --all       # Resetear y poblar todo
  python scripts/populate_wikipedia.py --verbose           # Logging detallado
        """,
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        metavar="YEAR",
        help="Año(s) de ceremonia Oscar a procesar (ej: --years 2024 2025).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Procesar todo el corpus histórico.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Borrar la base de datos antes de poblar.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(ROOT / "data"),
        help="Directorio donde guardar los archivos JSON.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay en segundos entre peticiones (default: 1.0).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Límite máximo de películas a procesar (útil para pruebas).",
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

    print_banner()

    # ── Resetear DB si se solicita ──────────────────────────────────────────
    if args.reset:
        print("  ⚠️  --reset: eliminando base de datos existente...")
        reset_database(args.data_dir)

    # ── Seleccionar corpus ──────────────────────────────────────────────────
    if args.all:
        corpus = OSCAR_CORPUS
    elif args.years:
        corpus = [(t, y, c) for t, y, c in OSCAR_CORPUS if c in args.years]
    else:
        # Por defecto: últimas 2 ceremonias
        default_years = {2025, 2024}
        corpus = [(t, y, c) for t, y, c in OSCAR_CORPUS if c in default_years]

    if args.limit:
        corpus = corpus[: args.limit]

    print(f"  🎞️  Películas a procesar    : {len(corpus)}")
    print(f"  ⏱️  Delay entre peticiones  : {args.delay}s")
    print()

    # ── Inicializar componentes ─────────────────────────────────────────────
    import crawler.wikipedia_scraper as wp_mod
    wp_mod.REQUEST_DELAY = args.delay  # permitir ajustar el delay desde CLI

    scraper = WikipediaScraper()
    store   = DocumentStore(data_dir=args.data_dir)
    idx     = InvertedIndex(language="english")

    # Reindexar documentos existentes para no perder el índice
    if store.documents:
        print(f"  ℹ️  Documentos ya existentes: {len(store.documents)}. Reindexando...")
        for doc_id, film_data in store.documents.items():
            idx.add_film(doc_id, film_data)
        print()

    # ── Procesar corpus ─────────────────────────────────────────────────────
    stats = {"ok": 0, "not_found": 0, "skipped": 0, "errors": 0}
    total = len(corpus)

    for i, (wiki_title, rel_year, ceremony) in enumerate(corpus, start=1):
        prefix = f"[{i:>3}/{total}]"
        display = wiki_title.replace(" (film)", "").replace(f" ({rel_year} film)", "")
        print(f"{prefix} {display} ({rel_year}) — Oscar {ceremony}", end="", flush=True)

        try:
            film_data = scraper.scrape_film(wiki_title, year=rel_year)
            film_data["oscar_ceremony"] = ceremony

            # Verificar si ya existe en el store
            source_url = film_data.get("source_url", "")
            existing = next(
                (doc_id for doc_id, d in store.documents.items()
                 if d.get("source_url") == source_url),
                None,
            )
            if existing is not None:
                print(f" → 🔄 ya existe (doc_id={existing})")
                stats["skipped"] += 1
                continue

            doc_id = store.add_film(film_data)
            idx.add_film(doc_id, film_data)

            director = film_data.get("director", "?")[:25]
            genre    = film_data.get("genre", "?")[:25]
            print(f" → ✅ doc_id={doc_id} | dir: {director} | género: {genre}")
            stats["ok"] += 1

        except ValueError as exc:
            print(f" → ⚠️  No encontrada: {exc}")
            stats["not_found"] += 1

        except Exception as exc:
            print(f" → ❌ Error: {exc}")
            logger.exception("Error procesando '%s'", wiki_title)
            stats["errors"] += 1

    # ── Guardar ─────────────────────────────────────────────────────────────
    print("\n  💾 Guardando en disco...")
    store.save()
    store.save_index(idx.index)
    print("  ✅ Guardado correctamente.")

    # ── Resumen ─────────────────────────────────────────────────────────────
    print_summary(store, idx, stats)


if __name__ == "__main__":
    main()
