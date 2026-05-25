"""
database/store.py
Document Storage Engine & Direct Serialization System.

=======================================================================================================
                        MATHEMATICAL AND ARCHITECTURAL CORE OF THE DOCUMENT STORE
=======================================================================================================

This module serves as the primary persistence layer for the unstructured/semi-structured corpus and
the inverted index using high-performance, single-file JSON serialization structures.

1. Mathematical Document Mapping & Deduplication Formalism
-----------------------------------------------------------
Let $D$ be the database corpus represented as a set of documents:
    $$D = \{ d_0, d_1, ..., d_{N-1} \}$$
Each document $d_j \in D$ is characterized by a set of schema properties.
To ensure perfect uniqueness of records under automated scraping and crawling, we construct 
two distinct bijective mapping indices that operate as O(1) deduplication filters:

  A. TMDB Unique Identifier Mapping:
     Let $\mathcal{K}_{TMDB} \subset \mathbb{N}$ be the set of valid TMDB database keys. 
     We define a unique lookup function $M_{TMDB}$:
         $$M_{TMDB}: \mathcal{K}_{TMDB} \to [0, N-1]$$
         $$M_{TMDB}(\text{tmdb\_id}) = doc\_id$$

  B. Fallback Resource URL Mapping:
     Let $\mathcal{S}_{URL}$ be the infinite set of valid web URLs. 
     We define a fallback string identifier lookup function $M_{URL}$:
         $$M_{URL}: \mathcal{S}_{URL} \to [0, N-1]$$
         $$M_{URL}(\text{source\_url}) = doc\_id$$

If a candidate document $d_{cand}$ with key parameters $(\text{tmdb\_id}, \text{source\_url})$ is parsed, 
the insertion function $\text{AddFilm}(d_{cand})$ resolves the target ID as:
    $$\text{ID}_{resolved} = \begin{cases} 
      M_{TMDB}(\text{tmdb\_id}) & \text{if } \text{tmdb\_id} \in \text{Domain}(M_{TMDB}) \\
      M_{URL}(\text{source\_url}) & \text{if } \text{source\_url} \in \text{Domain}(M_{URL}) \\
      N_{next} & \text{otherwise (allocate new index)}
    \end{cases}$$

2. Document Schema Formats (Adapter Pattern)
--------------------------------------------
The DocumentStore implements a structural Adapter Pattern to reconcile differences between legacy (v1) 
and modernized TMDB-enriched (v2) schemas:

  - Document Schema v1 (Legacy Wikipedia/Letterboxd):
    $$d_j^{v1} = \langle \text{title}, \text{year}, \text{synopsis}, \text{director}, \text{genre}, \text{reviews} \rangle$$
    
  - Document Schema v2 (Structural TMDB Rich Text):
    $$d_j^{v2} = \langle \text{title}, \text{year}, \text{metadata}, \text{rich\_text}, \text{reviews\_count} \rangle$$
    where:
    $$\text{metadata} = \langle \text{director}, \text{cast}, \text{genres}, \text{budget}, \text{revenue}, \text{vote\_average}, \text{vote\_count}, \text{imdb\_id}, \text{tmdb\_id}, \text{source\_url} \rangle$$

For downstream indices (Extended Boolean Model, Vector Space Model), the indexable text representation 
$R(d_j)$ is dynamically adapted inside `get_rich_text(doc_id)`:
    $$R(d_j) = \begin{cases} 
      d_j^{v2}.\text{rich\_text} & \text{if } d_j \text{ is } v2 \\
      d_j^{v1}.\text{title} \oplus d_j^{v1}.\text{synopsis} \oplus d_j^{v1}.\text{director} \oplus d_j^{v1}.\text{genre} \oplus \bigoplus_{r \in \text{reviews}} r & \text{if } d_j \text{ is } v1 
    \end{cases}$$
where $\oplus$ represents string concatenation with a space delimiter.

3. Serialization Flow Chart
---------------------------
  [In-Memory Data Structures] ─── (save()) ───> [Path/documents.json] (Disk JSON UTF-8)
             │
             ├─── (save_index()) ───> [Path/index.json] (Serialized Posting Lists)
             │
             └─── (load()) <─── [Path/documents.json] (Disk Read on Bootstrap)
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

    def get_next_id(self) -> int:
        """
        Retorna de forma segura y encapsulada el siguiente ID secuencial que será asignado.
        Respeta el principio de ocultamiento de datos de la POO.
        """
        return self._next_id

    # ─── Añadir documento ─────────────────────────────────────────────────────

    def add_film(self, film_data: dict) -> int:
        """
        INSERTION AND DEDUPLICATION ALGORITHM
        =====================================
        Inserts a movie document into the database while maintaining uniqueness constraints.
        
        1. TMDB ID Search ($M_{TMDB}$):
           Checks if `tmdb_id` exists in the in-memory primary key lookup table:
           $$\text{tmdb\_id} \in \text{Keys}(\text{self.\_tmdb\_id\_index})$$
           If true, returns the existing $doc\_id$ to prevent duplicates.
           
        2. Source URL Fallback ($M_{URL}$):
           If TMDB search fails, checks if `source_url` exists in the secondary index:
           $$\text{source\_url} \in \text{Keys}(\text{self.\_url\_index})$$
           If true, returns the existing $doc\_id$.
           
        3. Document Allocation ($N_{next}$):
           If both lookups fail, allocates:
           $$doc\_id = \text{self.\_next\_id}$$
           $$\text{self.\_next\_id} \leftarrow \text{self.\_next\_id} + 1$$
           Then updates mapping indexes:
           $$\text{self.\_tmdb\_id\_index}[\text{tmdb\_id}] = doc\_id$$
           $$\text{self.\_url\_index}[\text{source\_url}] = doc\_id$$
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
        """
        DOCUMENT RETRIEVAL BY UNIQUE PRIMARY ID
        =======================================
        Performs an exact lookup on the in-memory documents dictionary:
        $$\text{GetFilm}(j) = d_j \in D \cup \{\text{None}\}$$
        Complexity: $O(1)$ average time complexity.
        """
        return self.documents.get(doc_id)

    def all_films(self) -> list[dict]:
        """
        CORPUS TRANSFORMATION TO LIST REPRESENTATION
        ============================================
        Converts the in-memory mapping to a sequential array, injecting the `doc_id` inside each dictionary:
        $$\text{AllFilms}(D) = \left[ \{ \text{"doc\_id"}: j \} \cup d_j \;\middle|\; j \in [0, N-1] \right]$$
        """
        return [{"doc_id": k, **v} for k, v in self.documents.items()]

    def get_rich_text(self, doc_id: int) -> str:
        """
        DYNAMIC SCHEMATIC TEXT CONCATENATION ADAPTER
        ============================================
        Resolves schematic structural variations by dynamically extracting or synthesizing 
        indexable representations $R(d_j)$ for terms tokenization.
        
        Formula:
          $$R(d_j) = \begin{cases} 
            d_j^{v2}.\text{rich\_text} & \text{if } \text{"rich\_text"} \in d_j \\
            d_j^{v1}.\text{title} \oplus d_j^{v1}.\text{synopsis} \oplus d_j^{v1}.\text{director} \oplus d_j^{v1}.\text{genre} \oplus \bigoplus_{r \in \text{reviews}} r & \text{otherwise}
          \end{cases}$$
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
        """
        INVERTED INDEX PERMANENT PERSISTENCE
        ====================================
        Serializes term postings to an UTF-8 raw JSON index file.
        Let $t$ be a term, and $P_t = [ (d_1, tf_1), (d_2, tf_2), ... ]$ be its posting list.
        Saves the posting map $T \to P_t$ onto the local storage.
        """
        path = self.data_dir / self.INDEX_FILE
        serializable = {term: list(postings) for term, postings in index.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        logger.info("Índice guardado: %s (%d términos)", path, len(index))

    def load_index(self) -> dict[str, list[tuple[int, int]]]:
        """
        INVERTED INDEX BOOTSTRAP DESERIALIZATION
        ========================================
        Loads and maps raw posting tuples $(doc\_id, tf)$ back into the index structure.
        """
        path = self.data_dir / self.INDEX_FILE
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return {term: [tuple(p) for p in postings] for term, postings in raw.items()}

    # ─── Persistencia de documentos ───────────────────────────────────────────

    def save(self) -> None:
        """
        CORPUS SERIALIZATION FLOW
        =========================
        Persists the entire document repository mapping and system metadata using structured JSON format.
        """
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
        """
        CORPUS DESERIALIZATION & INDEX CONSTRUCT PIPELINE
        =================================================
        Loads all persisted records from the filesystem and dynamically rebuilds the deduplication indices:
        $$M_{TMDB}: ID_{tmdb} \to doc\_id$$
        $$M_{URL}: URL_{source} \to doc\_id$$
        """
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
