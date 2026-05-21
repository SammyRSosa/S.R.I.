"""
indexer/recommender.py
Content-Based Recommendation Engine (Corte 3)

Calculates hybrid similarity across movies utilizing high-performance VSM cosine 
inference over sparse EBM TF-IDF term vectors combined with structured Jaccard metadata.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


class MovieRecommender:
    """
    MATHEMATICAL FORMALISM: HYBRID CONTENT-BASED RECOMMENDATION ALGORITHM
    ====================================================================
    This module implements a state-of-the-art hybrid content recommendation engine.
    It combines non-structured textual similarities (reviews and synopsis) with
    structured attribute matches to maximize recommendation precision.

    1. Textual Vector Space Model (VSM) Cosine Similarity:
       For a seed document d_A and a candidate d_B, their textual similarity is
       modeled by the cosine of the angle between their high-dimensional TF-IDF vectors:
       
                                    d_A • d_B
           Sim_Cosine(d_A, d_B) = ─────────────
                                  ||d_A|| * ||d_B||
                                  
                                    ∑_{t ∈ (d_A ∩ d_B)} (w_{t,A} * w_{t,B})
                                = ──────────────────────────────────────────
                                  √(∑_{t ∈ d_A} w_{t,A}^2) * √(∑_{t ∈ d_B} w_{t,B}^2)

       Algorithmic Optimization (Sparse Dot Product):
       To prevent O(D) vector comparisons, we perform a sparse dot product. We iterate 
       only over the terms present in the seed movie d_A, fetch their postings, and
       accumulate scores for active intersection candidates. This reduces the complexity
       from linear O(D) to O(Terms_A * Avg_Postings_Size).

    2. Structured Metadata Jaccard Similarity:
       Structured features are parsed and normalized into set representations, then compared
       using the Jaccard similarity coefficient:
       
                                 |S_A ∩ S_B|
           Jaccard(S_A, S_B) = ───────────────
                                 |S_A ∪ S_B|

       Our model applies distinct weighting parameters for structured attributes:
       - Genres (50% weight): Set intersection Jaccard comparison.
       - Director (30% weight): Exact match (binary variable: 1.0 if match, 0.0 otherwise).
       - Cast (20% weight): Jaccard comparison of the top 5 billed actors.
       
       Mathematically:
       Sim_Meta(d_A, d_B) = 0.5 * Jaccard(G_A, G_B) + 0.3 * DirMatch(dir_A, dir_b) + 0.2 * Jaccard(C_A, C_B)

    3. Hybrid Integration:
       The final recommendation metric is a linear combination of both components:
       
           Score_Hybrid(d_A, d_B) = 0.5 * Sim_Cosine(d_A, d_B) + 0.5 * Sim_Meta(d_A, d_B)

    ALGORITHMIC FLOW DIAGRAM
    ========================
    [Input Seed doc_id] ──> [Fetch Sparse Weight Vector d_A] ──> [Pre-calculated L2 Norm ||d_A||]
                                                                        │
                                                                        ▼
    [Rank Hybrid Top-K] <── [Linear Fusion (0.5 * Cos + 0.5 * Meta)] <── [Dot Product over Postings Intersection]
                                                                        ▲
                                                                        │
                                                                 [Extract Structured Sets]
                                                                 - Genres, Director, Top 5 Cast
    """

    def __init__(self, store: Any, ebm: Any) -> None:
        """
        Inicializa el motor de recomendaciones.

        Args:
            store: Instancia cargada de DocumentStore.
            ebm: Instancia de ExtendedBooleanModel con pesos cargados.
        """
        self.store = store
        self.ebm = ebm

        # Índice directo mapeando doc_id -> {término: peso_TF_IDF}
        self.doc_vectors: dict[int, dict[str, float]] = defaultdict(dict)
        
        # Normas L2 precalculadas de cada documento para similitud coseno eficiente
        self.doc_norms: dict[int, float] = defaultdict(float)

        self._build_recommendation_index()

    def _build_recommendation_index(self) -> None:
        """
        Construye el índice directo en memoria para permitir recomendaciones en tiempo real.
        Evita tener que recorrer la matriz de términos entera por cada consulta.
        """
        logger.info("Construyendo índice directo de recomendaciones a partir de pesos EBM...")
        if not self.ebm.weights:
            logger.warning("Los pesos EBM están vacíos. No se puede construir el índice de recomendaciones.")
            return

        # 1. Poblar los vectores directos de documentos
        for term, doc_weights in self.ebm.weights.items():
            for doc_id, weight in doc_weights.items():
                self.doc_vectors[doc_id][term] = weight

        # 2. Precalcular la norma Euclidiana (L2) de cada documento
        for doc_id, vector in self.doc_vectors.items():
            sum_squares = sum(w ** 2 for w in vector.values())
            self.doc_norms[doc_id] = math.sqrt(sum_squares)

        logger.info("Índice de recomendaciones finalizado con éxito para %d películas.", len(self.doc_vectors))

    def calculate_cosine_similarity(self, doc_id_a: int) -> dict[int, float]:
        """
        Calcula la similitud coseno del texto de doc_id_a contra todos los demás documentos
        aprovechando un producto punto disperso a través de los posting lists.

        Args:
            doc_id_a: ID de la película semilla.

        Returns:
            Diccionario doc_id -> score_coseno.
        """
        norm_a = self.doc_norms.get(doc_id_a, 0.0)
        if norm_a < 1e-9:
            return {}

        vector_a = self.doc_vectors.get(doc_id_a, {})
        scores: dict[int, float] = defaultdict(float)

        # Producto punto disperso: solo multiplicamos por términos comunes
        for term, weight_a in vector_a.items():
            postings = self.ebm.weights.get(term, {})
            for doc_id_b, weight_b in postings.items():
                if doc_id_b == doc_id_a:
                    continue
                scores[doc_id_b] += weight_a * weight_b

        # Dividir por normas
        cosine_sims = {}
        for doc_id_b, dot_product in scores.items():
            norm_b = self.doc_norms.get(doc_id_b, 0.0)
            if norm_b > 1e-9:
                sim = dot_product / (norm_a * norm_b)
                # Acotar el valor por flotantes imprecisos
                cosine_sims[doc_id_b] = max(0.0, min(1.0, sim))

        return cosine_sims

    @staticmethod
    def _jaccard_similarity(set_a: Set[Any], set_b: Set[Any]) -> float:
        """Calcula el coeficiente de similitud de Jaccard entre dos conjuntos."""
        if not set_a or not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return intersection / union if union > 0 else 0.0

    def calculate_metadata_similarity(self, film_a: dict, film_b: dict) -> float:
        """
        Calcula la similitud de metadatos estructurados entre dos películas.
        Usa:
        - 50% Coeficiente Jaccard de Géneros.
        - 30% Coincidencia de Director (binario).
        - 20% Coeficiente Jaccard del elenco principal (top 5 actores).
        """
        # Extraer géneros (soporta esquemas v1 y v2)
        meta_a = film_a.get("metadata", {}) or {}
        meta_b = film_b.get("metadata", {}) or {}

        genres_a = set(film_a.get("genres", []) or meta_a.get("genres", []))
        genres_b = set(film_b.get("genres", []) or meta_b.get("genres", []))
        genre_sim = self._jaccard_similarity(genres_a, genres_b)

        # Extraer director
        dir_a = str(film_a.get("director", "") or meta_a.get("director", "")).strip().lower()
        dir_b = str(film_b.get("director", "") or meta_b.get("director", "")).strip().lower()
        
        # Validar coincidencia de director
        director_sim = 0.0
        if dir_a and dir_b and dir_a != "n/a" and dir_b != "n/a":
            director_sim = 1.0 if dir_a == dir_b else 0.0

        # Extraer reparto principal (limitado a los 5 primeros para evitar ruido de extras)
        cast_a = set((film_a.get("cast", []) or meta_a.get("cast", []))[:5])
        cast_b = set((film_b.get("cast", []) or meta_b.get("cast", []))[:5])
        cast_sim = self._jaccard_similarity(cast_a, cast_b)

        # Ponderación combinada
        return (0.5 * genre_sim) + (0.3 * director_sim) + (0.2 * cast_sim)

    def recommend(self, doc_id: int, top_k: int = 5) -> list[dict[str, Any]]:
        """
        Calcula y retorna las top_k películas más similares en base al score híbrido.

        Args:
            doc_id: ID del documento base.
            top_k: Cantidad de recomendaciones a retornar.

        Returns:
            Lista de diccionarios con metadatos de películas similares y scores.
        """
        film_a = self.store.get_film(doc_id)
        if not film_a:
            logger.warning("ID de película no encontrado en store: %s", doc_id)
            return []

        # 1. Obtener similitudes de texto (VSM)
        cosine_sims = self.calculate_cosine_similarity(doc_id)

        # 2. Calcular score final híbrido contra películas candidatos
        candidates = []
        for doc_id_b, cos_sim in cosine_sims.items():
            film_b = self.store.get_film(doc_id_b)
            if not film_b:
                continue

            # Calcular similitud de metadatos estructurados
            meta_sim = self.calculate_metadata_similarity(film_a, film_b)

            # Score combinado: 50% texto no estructurado + 50% metadatos estructurados
            final_score = (0.5 * cos_sim) + (0.5 * meta_sim)

            candidates.append((doc_id_b, final_score, cos_sim, meta_sim))

        # 3. Ordenar candidatos por score final
        candidates.sort(key=lambda x: x[1], reverse=True)

        # 4. Formatear y empaquetar recomendaciones
        recommendations = []
        for doc_id_b, final_score, cos_sim, meta_sim in candidates[:top_k]:
            film_b = self.store.get_film(doc_id_b)
            meta_b = film_b.get("metadata", {}) or {}
            
            recommendations.append({
                "doc_id": doc_id_b,
                "title": film_b.get("title", "Unknown"),
                "year": str(film_b.get("year", "N/A")),
                "director": film_b.get("director", "") or meta_b.get("director", "N/A"),
                "genres": film_b.get("genres", []) or meta_b.get("genres", []),
                "similarity": round(final_score, 4),
                "cosine_similarity": round(cos_sim, 4),
                "metadata_similarity": round(meta_sim, 4)
            })

        return recommendations
