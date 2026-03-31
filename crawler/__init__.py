"""
crawler/__init__.py
Módulo de Adquisición — Oscar Insight Search (SRI 2025-2026)

Fuentes activas:
  - TmdbClient           → metadatos estructurados (director, cast, genres, budget…)
  - LetterboxdReviewScraper → texto rico de reseñas de usuarios
"""

from .tmdb_client import TmdbClient
from .scraper     import LetterboxdReviewScraper, LetterboxdScraper   # alias de compatibilidad

__all__ = ["TmdbClient", "LetterboxdReviewScraper", "LetterboxdScraper"]
