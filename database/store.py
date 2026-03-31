"""
database/store.py
Almacenamiento Documental — Oscar Insight Search (SRI 2025-2026)

Gestiona la persistencia del corpus (películas) y del índice invertido
usando archivos JSON simples — sin dependencias externas.

Nuevo esquema de documento (v2):
    {
        "title":    str,
        "year":     str,
        "metadata": {
            "director":           str,
            "cast":               list[str],
            "genres":             list[str],
            "budget":             int,
            "revenue":            int,
            "vote_average":       float,
            "vote_count":         int,
            "original_language":  str,
            "imdb_id":            str,
            "tmdb_id":            int,
            "source_url":         str,
            "letterboxd_url":     str,
            "tagline":            str,
        },
        "rich_text":      str,   # title + genres + director + cast + overview + reviews
        "reviews_count":  int,
    }

Compatibilidad con esquema v1 (Wikipedia/Letterboxd):
    Si el documento tiene "synopsis" en lugar de "rich_text", se adapta
    automáticamente en el getter.

Archivos generados:
    data/documents.json   → persistencia de documentos
    data/index.json       → índice invertido serializado
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"


class DocumentStore:
    """
    Almacén persistente de documentos e índice invertido en formato JSON.

    Soporta dos esquemas de documento:
      - v1: {title, year, synopsis, reviews, source_url, ...}  (Wikipedia/Letterboxd legacy)
      - v2: {title, year, metadata, rich_text, reviews_count}  (TMDB + Letterboxd nuevo)

    La deduplicación usa `metadata.tmdb_id` si está disponible, o `source_url` como fallback.

    Attributes:
        data_dir (Path):    Carpeta donde se guardan los archivos JSON.
        documents (dict):   {doc_id (int): film_data (dict)}
        _next_id (int):     Autoincremental para nuevos documentos.

    Example::

        store = DocumentStore()
        doc_id = store.add_film(film_data)
        store.save()
    """

    DOCUMENTS_FILE = "documents.json"
    INDEX_FILE     = "index.json"

    def __init__(self, data_dir: str | Path = DEFAULT_DATA_DIR) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.documents: dict[int, dict] = {}
        self._next_id: int = 0

        # Índice de deduplicación: tmdb_id → doc_id
        self._tmdb_id_index: dict[int, int] = {}
        # Índice de deduplicación: source_url → doc_id (fallback)
        self._url_index: dict[str, int] = {}

        self.load()

    # ─── Añadir documento ─────────────────────────────────────────────────────

    def add_film(self, film_data: dict) -> int:
        """
        Añade una película al store. Retorna el doc_id (nuevo o existente).

        Deduplicación:
          1. Por `metadata.tmdb_id` (v2 schema)
          2. Por `source_url` (v1 schema y fallback)

        Args:
            film_data: Diccionario con el esquema v1 o v2.

        Returns:
            doc_id asignado (int).
        """
        # ── Deduplicación por tmdb_id ──────────────────────────────────────
        tmdb_id: Optional[int] = None
        metadata = film_data.get("metadata", {})
        if metadata:
            tmdb_id = metadata.get("tmdb_id")
        else:
            # v1 schema puede tener tmdb_id en el root
            tmdb_id = film_data.get("tmdb_id")

        if tmdb_id and tmdb_id in self._tmdb_id_index:
            existing_id = self._tmdb_id_index[tmdb_id]
            logger.debug("Película ya indexada por tmdb_id=%d (doc_id=%d).", tmdb_id, existing_id)
            return existing_id

        # ── Deduplicación por source_url ──────────────────────────────────
        source_url = film_data.get("source_url", "")
        if not source_url and metadata:
            source_url = metadata.get("source_url", "")

        if source_url and source_url in self._url_index:
            existing_id = self._url_index[source_url]
            logger.debug("Película ya indexada por URL (doc_id=%d): %s", existing_id, source_url)
            return existing_id

        # ── Insertar nuevo documento ──────────────────────────────────────
        doc_id = self._next_id
        self.documents[doc_id] = film_data
        self._next_id += 1

        # Actualizar índices de deduplicación
        if tmdb_id:
            self._tmdb_id_index[tmdb_id] = doc_id
        if source_url:
            self._url_index[source_url] = doc_id

        logger.debug(
            "Película agregada: doc_id=%d | %s (%s)",
            doc_id,
            film_data.get("title", "?"),
            film_data.get("year", "?"),
        )
        return doc_id

    # ─── Consulta ─────────────────────────────────────────────────────────────

    def get_film(self, doc_id: int) -> Optional[dict]:
        """Retorna el documento con el doc_id dado, o None si no existe."""
        return self.documents.get(doc_id)

    def all_films(self) -> list[dict]:
        """Retorna todos los documentos como lista con 'doc_id' incluido."""
        return [{"doc_id": k, **v} for k, v in self.documents.items()]

    def get_rich_text(self, doc_id: int) -> str:
        """
        Retorna el texto indexable del documento.

        Compatible con ambos esquemas:
          - v2: devuelve `rich_text`
          - v1: construye desde title + synopsis + reviews
        """
        film = self.documents.get(doc_id, {})
        if not film:
            return ""

        # Schema v2
        if "rich_text" in film:
            return film["rich_text"]

        # Schema v1 — construir rich_text
        parts = [
            film.get("title", ""),
            film.get("synopsis", ""),
            film.get("director", ""),
            film.get("genre", ""),
        ] + film.get("reviews", [])
        return " ".join(p for p in parts if p)

    # ─── Índice invertido ─────────────────────────────────────────────────────

    def save_index(self, index: dict[str, list[tuple[int, int]]]) -> None:
        """Persiste el índice invertido en data/index.json."""
        path = self.data_dir / self.INDEX_FILE
        serializable = {term: list(postings) for term, postings in index.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        logger.info("Índice guardado: %s (%d términos)", path, len(index))

    def load_index(self) -> dict[str, list[tuple[int, int]]]:
        """Carga el índice invertido desde data/index.json."""
        path = self.data_dir / self.INDEX_FILE
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return {term: [tuple(p) for p in postings] for term, postings in raw.items()}

    # ─── Persistencia de documentos ───────────────────────────────────────────

    def save(self) -> None:
        """Persiste los documentos en data/documents.json."""
        path = self.data_dir / self.DOCUMENTS_FILE
        payload = {
            "_meta": {
                "next_id": self._next_id,
                "total":   len(self.documents),
                "schema":  "v2",
            },
            "documents": {str(k): v for k, v in self.documents.items()},
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("Store guardado: %s (%d docs)", path, len(self.documents))

    def load(self) -> None:
        """Carga documentos desde data/documents.json (si existe)."""
        path = self.data_dir / self.DOCUMENTS_FILE
        if not path.exists():
            return
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)

        meta = payload.get("_meta", {})
        self._next_id = meta.get("next_id", 0)
        raw_docs = payload.get("documents", {})
        self.documents = {int(k): v for k, v in raw_docs.items()}

        # Reconstruir índices de deduplicación
        for doc_id, film in self.documents.items():
            metadata = film.get("metadata", {})
            tmdb_id  = (metadata.get("tmdb_id") if metadata else None) or film.get("tmdb_id")
            if tmdb_id:
                self._tmdb_id_index[int(tmdb_id)] = doc_id
            src = (metadata.get("source_url") if metadata else None) or film.get("source_url", "")
            if src:
                self._url_index[src] = doc_id

        logger.info("Store cargado: %d documentos.", len(self.documents))

    # ─── Utilidades ───────────────────────────────────────────────────────────

    @property
    def num_docs(self) -> int:
        """Número de documentos almacenados."""
        return len(self.documents)

    def stats(self) -> dict:
        """Retorna estadísticas del store."""
        return {
            "total_documents": len(self.documents),
            "next_id":         self._next_id,
            "data_dir":        str(self.data_dir),
            "documents_file":  str(self.data_dir / self.DOCUMENTS_FILE),
            "index_file":      str(self.data_dir / self.INDEX_FILE),
        }

    def __repr__(self) -> str:
        return f"DocumentStore(docs={len(self.documents)}, dir='{self.data_dir}')"
