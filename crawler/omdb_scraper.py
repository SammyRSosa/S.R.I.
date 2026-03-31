"""
crawler/omdb_scraper.py
Adquisición via OMDB API — Oscar Insight Search (SRI 2025-2026)

Alternativa al scraper de Letterboxd para cuando el sitio aplica
protección Cloudflare. OMDB API expone datos oficiales de IMDb
con una clave gratuita (1000 peticiones/día).

Registro gratuito: https://www.omdbapi.com/apikey.aspx

Uso:
    scraper = OmdbScraper(api_key="tu_clave")
    data = scraper.scrape_film("Oppenheimer", year=2023)
"""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)

OMDB_BASE_URL = "http://www.omdbapi.com/"
REQUEST_DELAY = 0.5   # 0.5 s entre peticiones (límite: 1000/día en free tier)


class OmdbScraper:
    """
    Scraper de películas vía OMDB API (datos de IMDb).

    Args:
        api_key: Clave de la API obtenida en https://www.omdbapi.com/apikey.aspx

    Example::

        scraper = OmdbScraper(api_key="abc12345")
        data = scraper.scrape_film("Oppenheimer", year=2023)
        # {"title": "Oppenheimer", "year": "2023", "synopsis": "...", ...}
    """

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("Se requiere una API key de OMDB. Regístrate gratis en https://www.omdbapi.com/apikey.aspx")
        self.api_key = api_key
        self.session = requests.Session()

    def _get(self, params: dict) -> dict:
        """Realiza una petición a la OMDB API y retorna el JSON."""
        params["apikey"] = self.api_key
        time.sleep(REQUEST_DELAY)
        response = self.session.get(OMDB_BASE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("Response") == "False":
            raise ValueError(f"OMDB error: {data.get('Error', 'Unknown error')}")
        return data

    def scrape_film(self, title: str, year: int | None = None) -> dict:
        """
        Obtiene metadatos de una película desde OMDB/IMDb.

        Args:
            title: Título de la película en inglés.
            year:  Año de estreno (opcional, mejora la búsqueda).

        Returns:
            Diccionario compatible con InvertedIndex.add_film()::

                {
                    "title":    str,
                    "year":     str,
                    "synopsis": str,
                    "reviews":  list[str],    # Siempre vacío (OMDB no provee reseñas)
                    "source_url": str,        # URL de IMDb construida desde imdbID
                    "imdb_id":  str,
                    "genre":    str,
                    "director": str,
                    "awards":   str,
                }
        """
        params: dict = {"t": title, "plot": "full", "type": "movie"}
        if year:
            params["y"] = year

        logger.info("Consultando OMDB: '%s' (%s)", title, year or "?")
        data = self._get(params)

        imdb_id = data.get("imdbID", "")
        film_data = {
            "title":      data.get("Title", title),
            "year":       data.get("Year", str(year or "")),
            "synopsis":   data.get("Plot", "Sinopsis no disponible."),
            "reviews":    [],           # OMDB no provee reseñas de usuarios
            "source_url": f"https://www.imdb.com/title/{imdb_id}/" if imdb_id else "",
            "imdb_id":    imdb_id,
            "genre":      data.get("Genre", ""),
            "director":   data.get("Director", ""),
            "awards":     data.get("Awards", ""),
        }

        logger.info("OK: %s (%s) — %s", film_data["title"], film_data["year"], imdb_id)
        return film_data
