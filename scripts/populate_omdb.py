"""
scripts/populate_omdb.py
Población via OMDB API — Oscar Insight Search (SRI 2025-2026)

Llena la base de datos con películas nominadas al Oscar usando la OMDB API
(datos oficiales de IMDb). No depende de Letterboxd ni de scraping web.

Prerrequisito — Obtener API Key GRATUITA:
    1. Ve a: https://www.omdbapi.com/apikey.aspx
    2. Selecciona "FREE" (1000 peticiones/día)
    3. Ingresa tu correo → recibirás la clave por email
    4. Actívala clickando el enlace del email

Uso:
    python scripts/populate_omdb.py --api-key TU_CLAVE_AQUI
    python scripts/populate_omdb.py --api-key TU_CLAVE_AQUI --years 2024
    python scripts/populate_omdb.py --api-key TU_CLAVE_AQUI --all-years

    # Con variable de entorno (más seguro):
    $env:OMDB_API_KEY = "tu_clave"
    python scripts/populate_omdb.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from crawler.omdb_scraper import OmdbScraper
from database import DocumentStore
from indexer import InvertedIndex

# ─── Corpus: Nominadas al Oscar Best Picture (y otras categorías principales) ──
# Formato: (titulo_en_ingles, año_estreno, año_ceremonia)
OSCAR_CORPUS: list[tuple[str, int, int]] = [
    # ── 96ª ceremonia (2024) ────────────────────────────────────────────────
    ("Oppenheimer",                        2023, 2024),
    ("Poor Things",                        2023, 2024),
    ("Anatomy of a Fall",                  2023, 2024),
    ("The Zone of Interest",               2023, 2024),
    ("Barbie",                             2023, 2024),
    ("Maestro",                            2023, 2024),
    ("Killers of the Flower Moon",         2023, 2024),
    ("Past Lives",                         2023, 2024),
    ("American Fiction",                   2023, 2024),
    ("The Holdovers",                      2023, 2024),
    # ── 95ª ceremonia (2023) ────────────────────────────────────────────────
    ("Everything Everywhere All at Once",  2022, 2023),
    ("Tar",                                2022, 2023),
    ("The Fabelmans",                      2022, 2023),
    ("All Quiet on the Western Front",     2022, 2023),
    ("The Whale",                          2022, 2023),
    ("Women Talking",                      2022, 2023),
    ("The Banshees of Inisherin",          2022, 2023),
    # ── 94ª ceremonia (2022) ────────────────────────────────────────────────
    ("CODA",                               2021, 2022),
    ("The Power of the Dog",               2021, 2022),
    ("Dune",                               2021, 2022),
    ("Belfast",                            2021, 2022),
    ("Licorice Pizza",                     2021, 2022),
    ("Drive My Car",                       2021, 2022),
    ("King Richard",                       2021, 2022),
    # ── 93ª ceremonia (2021) ────────────────────────────────────────────────
    ("Nomadland",                          2020, 2021),
    ("The Father",                         2020, 2021),
    ("Judas and the Black Messiah",        2020, 2021),
    ("Mank",                               2020, 2021),
    ("Minari",                             2020, 2021),
    ("Promising Young Woman",              2020, 2021),
    ("Sound of Metal",                     2020, 2021),
    ("The Trial of the Chicago 7",         2020, 2021),
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pobla la DB de Oscar Insight Search usando OMDB API (datos IMDb).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/populate_omdb.py --api-key abc12345
  python scripts/populate_omdb.py --api-key abc12345 --years 2024
  python scripts/populate_omdb.py --api-key abc12345 --all-years

Obtener API key gratis: https://www.omdbapi.com/apikey.aspx
        """,
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OMDB_API_KEY", ""),
        help="API key de OMDB (o usa la variable de entorno OMDB_API_KEY).",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        metavar="YEAR",
        help="Filtrar por año de ceremonia Oscar (ej: --years 2023 2024).",
    )
    parser.add_argument(
        "--all-years",
        action="store_true",
        help="Procesar todo el corpus (2021–2024).",
    )
    parser.add_argument(
        "--data-dir",
        default=str(ROOT / "data"),
        help="Directorio donde guardar los archivos JSON.",
    )
    args = parser.parse_args()

    # Validar API key
    if not args.api_key:
        print("\n❌ ERROR: No se proporcionó API key de OMDB.")
        print("   Obtén una gratis en: https://www.omdbapi.com/apikey.aspx")
        print("   Luego ejecuta:")
        print("     python scripts/populate_omdb.py --api-key TU_CLAVE")
        print("   O establece la variable de entorno:")
        print("     $env:OMDB_API_KEY = 'tu_clave'")
        sys.exit(1)

    # Filtrar corpus
    corpus = OSCAR_CORPUS
    if args.years and not args.all_years:
        corpus = [(t, y, c) for t, y, c in OSCAR_CORPUS if c in args.years]
    elif not args.all_years:
        # Por defecto: últimas 2 ceremonias
        corpus = [(t, y, c) for t, y, c in OSCAR_CORPUS if c in (2024, 2023)]

    print(f"\n🎬 Oscar Insight Search — Población via OMDB API (IMDb)")
    print(f"   Total a procesar: {len(corpus)} películas")
    print()

    # Inicializar componentes
    scraper = OmdbScraper(api_key=args.api_key)
    store   = DocumentStore(data_dir=args.data_dir)
    idx     = InvertedIndex(language="english")

    # Reindexar documentos existentes
    if store.documents:
        print(f"ℹ️  Documentos existentes: {len(store.documents)}. Reindexando...")
        for doc_id, film_data in store.documents.items():
            idx.add_film(doc_id, film_data)

    # Procesar corpus
    ok = skipped = errors = 0
    for i, (title, year, ceremony) in enumerate(corpus, start=1):
        print(f"[{i:>2}/{len(corpus)}] {title} ({year}) — Oscar {ceremony}")
        try:
            film_data = scraper.scrape_film(title, year=year)
            film_data["oscar_ceremony"] = ceremony   # campo extra útil
            doc_id = store.add_film(film_data)
            idx.add_film(doc_id, film_data)

            print(f"  ✅ doc_id={doc_id} | {film_data['title']} | "
                  f"imdbID={film_data.get('imdb_id','?')}")
            ok += 1

        except ValueError as e:
            print(f"  ⚠️  No encontrada en OMDB: {e}")
            skipped += 1
        except Exception as e:
            print(f"  ❌ Error: {e}")
            errors += 1

    # Guardar
    print("\n💾 Guardando en disco...")
    store.save()
    store.save_index(idx.index)

    # Resumen
    print("\n" + "═" * 60)
    print("  RESUMEN — Oscar Insight Search (OMDB)")
    print("═" * 60)
    print(f"  ✅ Procesadas correctamente : {ok}")
    print(f"  ⚠️  No encontradas en OMDB  : {skipped}")
    print(f"  ❌ Errores                  : {errors}")
    print(f"  📁 Total en base de datos   : {store.num_docs}")
    print(f"  📚 Términos en el índice    : {idx.vocabulary_size}")
    print(f"  📂 Carpeta de datos         : {args.data_dir}")
    print("═" * 60)

    if idx.vocabulary_size > 0:
        top = sorted(idx.index.items(), key=lambda x: sum(f for _, f in x[1]), reverse=True)[:10]
        print("\n  Top 10 términos:")
        for term, postings in top:
            print(f"    '{term}' → {len(postings)} doc(s), tf={sum(f for _, f in postings)}")

    print()


if __name__ == "__main__":
    main()
