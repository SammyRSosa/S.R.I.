"""
indexer/recommender.py
Módulo de Recomendación basado en Contenido — Oscar Insight Search (Corte 3)

Calcula similitudes híbridas utilizando:
1. Representación Vectorial e Inferencia Coseno sobre los pesos TF-IDF precalculados (EBM).
2. Similitud estructurada Jaccard sobre géneros y reparto + coincidencia exacta de director.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


class MovieRecommender:
    """
    Motor de Recomendación basado en Contenido.
    
    Implementa un enfoque híbrido que combina:
    - Similitud Coseno de Espacio Vectorial (VSM) sobre las representaciones TF-IDF de reviews y sinopsis.
    - Similitud estructurada sobre atributos clave (géneros, director y elenco).
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
