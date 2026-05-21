"""
indexer/inverted_index.py
Inverted Index & Linguistic Processing Engine (Corte 2 & 3)

Implements a normalized postings-list repository utilizing structured tokenization,
stopword extraction, and morphological stem reduction algorithms.
Extends base indexing to support suave logical evaluations within the Extended Boolean Model.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from typing import Sequence

import nltk
from nltk.corpus import stopwords
from nltk.stem import SnowballStemmer
from nltk.tokenize import word_tokenize

# ─── Bootstrap NLTK (idempotente) ────────────────────────────────────────────
for _corpus in ("punkt", "punkt_tab", "stopwords"):
    try:
        nltk.data.find(f"tokenizers/{_corpus}" if "punkt" in _corpus else f"corpora/{_corpus}")
    except LookupError:
        nltk.download(_corpus, quiet=True)

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class InvertedIndex:
    """
    MATHEMATICAL FORMALISM & LINGUISTIC PIPELINE: INVERTED INDEX
    ============================================================
    An Inverted Index is an architectural data structure that maps vocabulary terms
    to the documents containing them, representing a sparse matrix.
    
    1. Postings List Formal Representation:
       Let V = {t_1, t_2, ..., t_|V|} be the vocabulary set.
       For each term t_i ∈ V, we maintain a Posting List P_i:
       
           P_i = [ (d_{i,1}, tf_{i,d_{i,1}}), (d_{i,2}, tf_{i,d_{i,2}}), ..., (d_{i,k}, tf_{i,d_{i,k}}) ]
           
           Where:
           - d_{i,y} is the document identifier containing term t_i, ordered monotonically.
           - tf_{i,d_{i,y}} is the Term Frequency (number of occurrences of t_i inside document d_{i,y}).
           
       This dual (doc_id, tf) postings structure allows O(1) term posting lookups,
       enabling efficient p-norm distance calculations during EBM runtime.

    2. Linguistic Normalization Pipeline:
       Every text block undergoes a strict sequential transformation before index insertion:
       
       [Input Text]
            │
            ▼
       [Case folding]       ──> Convert all characters to lowercase to eliminate casing noise.
            │
            ▼
       [Tokenization]       ──> NLTK Word Tokenization splits strings on word/punctuation boundaries.
            │
            ▼
       [Alphanumeric Filter]──> Keep only tokens containing at least one letter/digit (regex: [a-z0-9]).
            │
            ▼
       [Stopwords Filter]   ──> Omit high-frequency terms. We fuse NLTK's English + Spanish sets,
                                and append domain-specific movie stopwords (e.g. "film", "director").
            │
            ▼
       [Morphological Stem] ──> Snowball Stemmer maps words to their linguistic base forms
                                (e.g. "nominations", "nominated", "nominate" -> "nomin").
            │
            ▼
       [Normalized Postings]

    Attributes:
        _raw_index (defaultdict): Internal nested hash map {term: {doc_id: tf}}.
        documents (dict): Document store mapping doc_id -> raw text for snippet generation.
        language (str): Base language for morphological analysis ('english' or 'spanish').
    """

    def __init__(self, language: str = "english") -> None:
        """
        Inicializa el índice vacío.

        Args:
            language: Idioma para stop-words y stemmer (default: 'english').
                      Valores válidos: 'english', 'spanish'.
        """
        self.language = language

        # Posting lists: término normalizado → lista de (doc_id, frecuencia)
        # Usamos defaultdict internamente para construcción; se expone como dict.
        self._raw_index: defaultdict[str, dict[int, int]] = defaultdict(dict)

        # Almacén de documentos originales: doc_id → texto
        self.documents: dict[int, str] = {}

        # Stop-words combinadas (en + es) para robustez en corpus bilingüe
        self._stop_words: frozenset[str] = self._load_stop_words()

        # Stemmer de Snowball
        self._stemmer = SnowballStemmer(language)

        logger.info(
            "InvertedIndex inicializado. Idioma: %s | Stop-words: %d",
            self.language,
            len(self._stop_words),
        )

    # ─── Stop-words ───────────────────────────────────────────────────────────

    @staticmethod
    def _load_stop_words() -> frozenset[str]:
        """Carga stop-words en inglés y español para corpus bilingüe."""
        try:
            en_stops = set(stopwords.words("english"))
            es_stops = set(stopwords.words("spanish"))
            combined = en_stops | es_stops
        except LookupError:
            nltk.download("stopwords", quiet=True)
            en_stops = set(stopwords.words("english"))
            es_stops = set(stopwords.words("spanish"))
            combined = en_stops | es_stops
        
        # Lista negra cinematográfica (Términos que generan ruido conceptual)
        cine_stopwords = {
            "historia", "película", "pelicula", "director", "cine", 
            "trama", "argumento", "personaje", "actor", "actriz", 
            "amor", "movie", "film", "story", "character", "director", "cinema"
        }
        combined.update(cine_stopwords)
        return frozenset(combined)

    # ─── Tokenización y Normalización ─────────────────────────────────────────

    def _tokenize(self, text: str) -> list[str]:
        """
        Aplica el pipeline de normalización completo a *text*.

        Pipeline:
            1. Minúsculas.
            2. Tokenización lingüística con nltk.word_tokenize.
            3. Filtro: sólo tokens con al menos un carácter alfanumérico.
            4. Eliminación de stop-words (inglés + español).
            5. Stemming con SnowballStemmer.

        Args:
            text: Texto crudo a normalizar.

        Returns:
            Lista de stems normalizados listos para indexar.
        """
        if not text or not isinstance(text, str):
            return []

        # 1. Minúsculas
        lowered = text.lower()

        # 2. Tokenizar
        tokens = word_tokenize(lowered, language=self.language)

        # 3. Filtro alfanumérico + 4. Stop-words + 5. Stemming
        stems = []
        for token in tokens:
            # Conservar sólo si contiene al menos un carácter alfanumérico
            if not re.search(r"[a-z0-9]", token):
                continue
            # Eliminar stop-words
            if token in self._stop_words:
                continue
            # Stemming
            stems.append(self._stemmer.stem(token))

        return stems

    # ─── Construcción del Índice ───────────────────────────────────────────────

    def add_document(self, doc_id: int, text: str) -> None:
        """
        Tokeniza *text* y actualiza el índice invertido con el documento *doc_id*.

        Si el documento ya fue indexado, sus postings se actualizan (no se duplican).

        Args:
            doc_id: Identificador único del documento (entero ≥ 0).
            text:   Texto completo del documento (título + sinopsis + críticas).

        Example::

            idx.add_document(0, "Oppenheimer won the Best Director Oscar in 2024.")
        """
        if not isinstance(doc_id, int) or doc_id < 0:
            raise ValueError(f"doc_id debe ser un entero no negativo. Recibido: {doc_id!r}")

        stems = self._tokenize(text)

        if not stems:
            logger.warning("Documento %d no generó tokens tras normalización.", doc_id)
            return

        # Contar frecuencias en este documento (tf_i,j)
        term_freq: Counter = Counter(stems)

        # Actualizar posting lists
        for term, freq in term_freq.items():
            self._raw_index[term][doc_id] = freq

        # Guardar texto original
        self.documents[doc_id] = text

        logger.debug(
            "Documento %d indexado: %d tokens únicos.", doc_id, len(term_freq)
        )

    def add_film(self, doc_id: int, film_data: dict) -> None:
        """
        Conveniencia: indexa un diccionario de película.

        Soporta ambos esquemas de documento:
        - v2 (TMDB): lee directamente ``film_data['rich_text']``.
        - v1 (legacy): concatena title + synopsis + reviews.

        Args:
            doc_id:    Identificador único del documento.
            film_data: Diccionario con esquema v1 o v2.
        """
        # ── Schema v2: campo rich_text ya preparado ────────────────────────
        rich_text = film_data.get("rich_text", "")
        if rich_text:
            self.add_document(doc_id, rich_text)
            return

        # ── Schema v1 legacy: construir texto desde partes ─────────────────
        metadata = film_data.get("metadata", {})
        parts = [
            film_data.get("title", ""),
            film_data.get("year", ""),
            film_data.get("synopsis", ""),
            film_data.get("director", ""),
            film_data.get("genre", ""),
            film_data.get("awards", ""),
            film_data.get("cast", ""),
        ]
        # Añadir campos de metadata si existen
        if metadata:
            parts += [
                metadata.get("director", ""),
                " ".join(metadata.get("genres", [])),
                " ".join(metadata.get("cast", [])[:5]),
                metadata.get("tagline", ""),
            ]
        # Añadir reviews
        parts += film_data.get("reviews", [])

        full_text = " ".join(p for p in parts if p)
        self.add_document(doc_id, full_text)

    # ─── Consulta del Índice ───────────────────────────────────────────────────

    def get_postings(self, term: str) -> list[tuple[int, int]]:
        """
        Retorna la posting list de un término.

        El término se normaliza con el mismo pipeline antes de buscar,
        garantizando consistencia con los tokens indexados.

        Args:
            term: Término a buscar (puede estar sin normalizar).

        Returns:
            Lista de tuplas ``(doc_id, tf)`` ordenadas por doc_id.
            Lista vacía si el término no existe en el índice.

        Example::

            postings = idx.get_postings("Awards")
            # → [(0, 2), (3, 1)]
        """
        stems = self._tokenize(term)
        if not stems:
            return []

        normalized = stems[0]
        raw = self._raw_index.get(normalized, {})
        return sorted(raw.items())  # [(doc_id, tf), ...] ordenado

    def get_all_terms(self) -> list[str]:
        """Retorna todos los términos del vocabulario indexado."""
        return sorted(self._raw_index.keys())

    # ─── Propiedad pública: index ──────────────────────────────────────────────

    @property
    def index(self) -> dict[str, list[tuple[int, int]]]:
        """
        Vista pública del índice invertido.

        Returns:
            ``dict[str, list[tuple[int, int]]]`` —
            término normalizado → lista de (doc_id, tf) ordenada por doc_id.
        """
        return {
            term: sorted(postings.items())
            for term, postings in self._raw_index.items()
        }

    @property
    def num_docs(self) -> int:
        """Número de documentos úni­cos indexados."""
        return len(self.documents)

    @property
    def vocabulary_size(self) -> int:
        """Tamaño del vocabulario (número de términos únicos)."""
        return len(self._raw_index)

    # ─── Representación ───────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"InvertedIndex("
            f"docs={self.num_docs}, "
            f"terms={self.vocabulary_size}, "
            f"lang='{self.language}')"
        )

    def __len__(self) -> int:
        """Retorna el número de términos en el vocabulario."""
        return self.vocabulary_size


# ─── Uso de ejemplo (ejecución directa) ───────────────────────────────────────
if __name__ == "__main__":
    idx = InvertedIndex(language="english")

    # Documentos de muestra (películas nominadas al Oscar)
    sample_docs = [
        (0, "Oppenheimer won the Academy Award for Best Picture and Best Director in 2024."),
        (1, "Poor Things received Oscar nominations for Best Actress and Best Costume Design."),
        (2, "The film Oppenheimer dominated the awards ceremony with seven Oscar wins."),
        (3, "Barbie was also nominated for best picture at the Academy Awards ceremony."),
    ]

    for doc_id, text in sample_docs:
        idx.add_document(doc_id, text)

    print(idx)
    print("\nPosting list para 'award':", idx.get_postings("award"))
    print("Posting list para 'Oscar':", idx.get_postings("oscar"))
    print("Posting list para 'Oppenheimer':", idx.get_postings("Oppenheimer"))
    print("\nVocabulario (primeros 15 términos):", idx.get_all_terms()[:15])
