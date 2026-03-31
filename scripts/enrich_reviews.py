"""
scripts/enrich_reviews.py
Enriquecimiento de Reviews — Oscar Insight Search (SRI 2025-2026)

Toma las 1622 películas ya indexadas (con metadata de TMDB pero sin reviews)
y añade el texto de hasta 10 reseñas de Letterboxd al campo rich_text de cada una.

Esto es crítico para el Modelo Booleano Extendido: sin texto de reseñas,
el índice solo tiene géneros y sinopsis. Con reseñas tendrá vocabulario rico
para soportar consultas en lenguaje natural como:
  "dark claustrophobic cinematography"
  "heartbreaking performance grief"
  "slow burn psychological thriller"

Flujo:
  1. Carga documents.json en memoria.
  2. Re-indexa todos los docs en InvertedIndex.
  3. Para cada doc con imdb_id y reviews_count == 0:
       a. Obtiene reviews de Letterboxd (scraper de sesión única).
       b. Concatena al rich_text.
       c. Actualiza reviews_count.
       d. Re-indexa el doc para incorporar nuevos términos.
  4. Guarda checkpoint cada SAVE_EVERY docs enriquecidos.
  5. Guarda DB a disco y actualiza index.json al final.

Checkpoint: data/enrich_checkpoint.json
  {"done": [1, 5, 9, ...], "failed": [2, 7, ...], "total": 150}
  → Si se interrumpe, reanuda desde donde quedó con --resume.

Uso:
  python scripts/enrich_reviews.py
  python scripts/enrich_reviews.py --limit 100          # Solo 100 películas
  python scripts/enrich_reviews.py --resume             # Continuar desde checkpoint
  python scripts/enrich_reviews.py --max-reviews 15     # Más reviews por película
  python scripts/enrich_reviews.py --verbose            # Logs DEBUG
"""

from __future__ import annotations

import argparse
import io
import json
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

from crawler.scraper import LetterboxdReviewScraper
from database        import DocumentStore
from indexer         import InvertedIndex

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("enrich_reviews")

SAVE_EVERY = 25     # Guardar a disco cada N docs enriquecidos


# ─── Checkpoint de enriquecimiento ────────────────────────────────────────────

def load_enrich_ck(path: Path) -> dict:
    """Carga el checkpoint de enriquecimiento (o retorna uno vacío)."""
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            done   = set(raw.get("done", []))
            failed = set(raw.get("failed", []))
            total  = raw.get("total", 0)
            logger.info("Checkpoint de enriquecimiento: %d done, %d failed, %d total",
                        len(done), len(failed), total)
            return {"done": done, "failed": failed, "total": total}
        except Exception as exc:
            logger.warning("No se pudo cargar checkpoint: %s", exc)
    return {"done": set(), "failed": set(), "total": 0}


def save_enrich_ck(path: Path, ck: dict) -> None:
    """Persiste el checkpoint de enriquecimiento."""
    payload = {
        "done":   sorted(ck["done"]),
        "failed": sorted(ck["failed"]),
        "total":  ck["total"],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def build_enriched_text(current_rich: str, reviews: list[str]) -> str:
    """Añade las reviews al rich_text existente."""
    review_text = " ".join(r for r in reviews if r)
    return (current_rich + " " + review_text).strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enriquece los documentos TMDB con reseñas de Letterboxd.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/enrich_reviews.py                   # Enriquecer todo
  python scripts/enrich_reviews.py --limit 50        # Solo 50 películas (prueba)
  python scripts/enrich_reviews.py --resume          # Continuar desde checkpoint
  python scripts/enrich_reviews.py --max-reviews 15  # 15 reviews por película
        """,
    )
    parser.add_argument(
        "--data-dir",
        default=str(ROOT / "data"),
        help="Directorio de datos.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Límite de películas a procesar (0 = todas).",
    )
    parser.add_argument(
        "--max-reviews",
        type=int,
        default=10,
        help="Máximo de reviews a obtener por película (default: 10).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Continuar desde el checkpoint de enriquecimiento.",
    )
    parser.add_argument(
        "--reset-ck",
        action="store_true",
        help="Borrar el checkpoint de enriquecimiento y empezar de cero.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Habilitar logs DEBUG.",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    data_dir = Path(args.data_dir)
    ck_path  = data_dir / "enrich_checkpoint.json"

    # ── Reset checkpoint si se pide ───────────────────────────────────────────
    if args.reset_ck and ck_path.exists():
        ck_path.unlink()
        print("  Checkpoint de enriquecimiento borrado.")

    # ── Cargar estado ─────────────────────────────────────────────────────────
    ck = load_enrich_ck(ck_path) if args.resume else {"done": set(), "failed": set(), "total": 0}

    # ── Cargar store e índice ─────────────────────────────────────────────────
    store = DocumentStore(data_dir=data_dir)
    idx   = InvertedIndex(language="english")

    if not store.documents:
        print("ERROR: No hay documentos en la base de datos. Ejecuta populate_tmdb.py primero.")
        sys.exit(1)

    print(f"\n  Reindexando {len(store.documents)} documentos en memoria...")
    for doc_id, film in store.documents.items():
        idx.add_film(doc_id, film)
    print(f"  Indice en memoria: {idx.vocabulary_size} terminos\n")

    # ── Filtrar candidatos a enriquecer ────────────────────────────────────────
    candidates = []
    for doc_id, film in store.documents.items():
        meta = film.get("metadata", {})
        imdb_id      = meta.get("imdb_id", "")
        reviews_count = film.get("reviews_count", 0)
        if imdb_id and reviews_count == 0 and doc_id not in ck["done"]:
            candidates.append((doc_id, film))

    total_candidates = len(candidates)
    if args.limit > 0:
        candidates = candidates[:args.limit]

    # ── Banner ─────────────────────────────────────────────────────────────────
    print("=" * 65)
    print("  Oscar Insight Search -- Enriquecimiento con Reviews Letterboxd")
    print("=" * 65)
    print(f"  Documentos en DB        : {len(store.documents)}")
    print(f"  Candidatos a enriquecer : {total_candidates}")
    print(f"  A procesar en este run  : {len(candidates)}")
    print(f"  Max reviews/pelicula    : {args.max_reviews}")
    print(f"  Ya completados (ck)     : {len(ck['done'])}")
    print("=" * 65 + "\n")

    if not candidates:
        print("  No hay peliculas pendientes de enriquecimiento.")
        sys.exit(0)

    # ── Inicializar scraper (una sola sesion, precalentada) ────────────────────
    print("  Iniciando sesion Letterboxd (precalentando Cloudflare cookies)...")
    scraper = LetterboxdReviewScraper(warmup=True)
    print("  Sesion lista.\n")

    # ── Stats ─────────────────────────────────────────────────────────────────
    stats = {"enriched": 0, "skipped": 0, "errors": 0}

    # ── Loop principal ─────────────────────────────────────────────────────────
    for i, (doc_id, film) in enumerate(candidates, 1):
        meta     = film.get("metadata", {})
        imdb_id  = meta.get("imdb_id", "")
        title    = film.get("title", "")
        year_str = film.get("year", "")
        year     = int(year_str) if year_str and year_str.isdigit() else None

        prefix = f"[{i:>4}/{len(candidates)}]"
        print(f"{prefix} {title} ({year or '?'}) | imdb={imdb_id}")

        try:
            reviews = scraper.get_reviews(
                title=title,
                year=year,
                imdb_id=imdb_id,
                max_reviews=args.max_reviews,
            )
        except Exception as exc:
            logger.error("Excepcion en '%s': %s", title, exc)
            reviews = []
            stats["errors"] += 1

        if reviews:
            # Actualizar documento
            current_rich = film.get("rich_text", "")
            film["rich_text"]     = build_enriched_text(current_rich, reviews)
            film["reviews_count"] = len(reviews)
            store.documents[doc_id] = film

            # Re-indexar solo el texto nuevo (mas eficiente que re-indexar todo)
            reviews_text = " ".join(reviews)
            idx.add_document(doc_id, reviews_text)

            ck["done"].add(doc_id)
            ck["total"] += 1
            stats["enriched"] += 1
            print(f"         -> OK: {len(reviews)} reviews | vocab: {idx.vocabulary_size} terminos")
        else:
            ck["failed"].add(doc_id)
            stats["skipped"] += 1
            print(f"         -> Sin reviews")

        # Guardado incremental
        if stats["enriched"] > 0 and stats["enriched"] % SAVE_EVERY == 0:
            print(f"\n  [Guardando... {stats['enriched']} enriquecidos | {idx.vocabulary_size} terminos]\n")
            save_enrich_ck(ck_path, ck)
            store.save()
            store.save_index(idx.index)

    # ── Guardado final ────────────────────────────────────────────────────────
    print("\n  Guardando estado final...")
    save_enrich_ck(ck_path, ck)
    store.save()
    store.save_index(idx.index)

    # ── Resumen ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  RESUMEN DE ENRIQUECIMIENTO")
    print("=" * 65)
    print(f"  Enriquecidas con reviews : {stats['enriched']}")
    print(f"  Sin reviews (Letterboxd) : {stats['skipped']}")
    print(f"  Errores                  : {stats['errors']}")
    print(f"  Total historico (ck)     : {ck['total']}")
    print(f"  Terminos en el indice    : {idx.vocabulary_size}")
    print(f"  Objetivo (10.000 terms)  : {'ALCANZADO' if idx.vocabulary_size >= 10000 else f'FALTA {10000-idx.vocabulary_size}'}")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
