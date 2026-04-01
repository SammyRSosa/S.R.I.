"""
scripts/query.py
Script de Consulta Interactiva — Oscar Insight Search (SRI 2025-2026)

Permite consultar el índice invertido desde la línea de comandos
sin necesidad de levantar la API.

Uso:
    python scripts/query.py "oscar"
    python scripts/query.py "director" --show-docs
    python scripts/query.py "Oppenheimer" --show-docs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from database import DocumentStore
from indexer import InvertedIndex


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consulta el índice invertido de Oscar Insight Search.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/query.py "oscar"
  python scripts/query.py "director" --show-docs
  python scripts/query.py "Oppenheimer award" --show-docs
        """,
    )
    parser.add_argument("query", nargs="+", help="Término(s) a buscar.")
    parser.add_argument(
        "--show-docs",
        action="store_true",
        help="Mostrar el título y sinopsis de los documentos encontrados.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(ROOT / "data"),
        help="Directorio con los archivos JSON.",
    )
    args = parser.parse_args()

    # Cargar store e índice
    store = DocumentStore(data_dir=args.data_dir)
    idx = InvertedIndex()

    # Reconstruir índice desde documentos almacenados
    if not store.documents:
        print("⚠️  Base de datos vacía. Ejecuta primero: python scripts/populate.py --mock")
        sys.exit(1)

    print(f"ℹ️  Cargando {len(store.documents)} documentos en el índice...")
    for doc_id, film_data in store.documents.items():
        idx.add_film(doc_id, film_data)

    print(f"✅ Índice listo: {idx.vocabulary_size} términos únicos.\n")

    # Buscar cada término de la consulta
    for term in args.query:
        postings = idx.get_postings(term)
        print(f"🔍 Término: '{term}'")
        if not postings:
            print("   → Sin resultados.\n")
            continue

        # Ordenar por frecuencia (tf) de mayor a menor y limitar al top 10
        postings.sort(key=lambda x: x[1], reverse=True)
        top_n = min(10, len(postings))
        
        print(f"   → {len(postings)} documento(s) en total, mostrando los {top_n} más relevantes:")
        for doc_id, tf in postings[:top_n]:
            film = store.get_film(doc_id)
            title = film.get("title", "?") if film else "?"
            year  = film.get("year",  "?") if film else "?"
            print(f"      doc_id={doc_id} | tf={tf} | {title} ({year})")

            if args.show_docs and film:
                synopsis = film.get("synopsis", "")[:120]
                print(f"      Sinopsis: {synopsis}...")
        print()


if __name__ == "__main__":
    main()
