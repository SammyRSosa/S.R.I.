"""
crawler/__init__.py
Módulo de Adquisición — Oscar Insight Search (SRI 2025-2026)

Exporta las clases de scraping para uso externo.
"""

from .scraper import LetterboxdScraper
from .omdb_scraper import OmdbScraper
from .wikipedia_scraper import WikipediaScraper

__all__ = ["LetterboxdScraper", "OmdbScraper", "WikipediaScraper"]
