"""
crawler/tmdb_client.py
Cliente TMDB v3 — Oscar Insight Search (SRI 2025-2026)

Obtiene metadatos estructurados de películas desde la API pública de TMDB:
  - Estrategia A: sort_by=popularity.desc (películas conocidas → más reviews en Letterboxd)
  - Estrategia B: sort_by=vote_average.desc + vote_count>=500 (películas de calidad)

Documentación TMDB API v3: https://developer.themoviedb.org/reference/intro/getting-started

Rate limit free tier: ~40 peticiones / 10 segundos.
Se aplica un delay conservador de 0.27s entre llamadas.

Uso:
    client = TmdbClient(api_key="b2119ca4292283dc53299bdf3c3998db")
    films = client.discover_movies(page=1, strategy="popularity")
    details = client.get_movie_details(872585)   # Oppenheimer
"""

from __future__ import annotations

import logging
import time
from typing import Literal, Optional

import requests

logger = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"
REQUEST_DELAY  = 0.27   # 0.27 s ≈ 37 req/10 s (bajo el límite de 40)
REQUEST_TIMEOUT = 12

# ─── Estrategias de descubrimiento ────────────────────────────────────────────
STRATEGIES: dict[str, dict] = {
    "popularity": {
        "sort_by": "popularity.desc",
        "vote_count.gte": 100,       # Mínimo de votos para tener reviews en Letterboxd
    },
    "quality": {
        "sort_by": "vote_average.desc",
        "vote_count.gte": 500,       # Alta calidad: muchos votos + nota alta
    },
}


class TmdbClient:
    """
    Cliente ligero para la API v3 de TMDB.

    Soporta autenticación mediante API key (query param) o Bearer token (header).
    Se recomienda pasar ambos: api_key para simplificar los parámetros, y
    access_token para endpoints que requieren Bearer (como algunas listas).

    Args:
        api_key: Clave de API v3 (query param ``?api_key=...``).
        access_token: Token de acceso v4/v3 (header ``Authorization: Bearer ...``).

    Example::

        client = TmdbClient(api_key="abc123")
        page_films = client.discover_movies(page=1, strategy="popularity")
        details    = client.get_movie_details(872585)
    """

    def __init__(
        self,
        api_key: str = "",
        access_token: str = "",
    ) -> None:
        if not api_key and not access_token:
            raise ValueError(
                "Se requiere al menos una API key o un access token de TMDB."
            )
        self.api_key = api_key
        self.access_token = access_token

        self.session = requests.Session()
        if access_token:
            self.session.headers["Authorization"] = f"Bearer {access_token}"

        self._last_request_time: float = 0.0

    # ─── HTTP helper ──────────────────────────────────────────────────────────

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """
        GET autenticado con rate limiting.

        Args:
            endpoint: Ruta relativa, p. ej. ``/discover/movie``.
            params:   Parámetros de query (sin api_key, se añade automáticamente).

        Returns:
            Parsed JSON como dict.

        Raises:
            requests.HTTPError: Si el servidor responde con un código de error.
        """
        url = TMDB_BASE_URL + endpoint
        query: dict = {}
        if self.api_key:
            query["api_key"] = self.api_key
        if params:
            query.update(params)

        # Rate limiting conservador
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)

        self._last_request_time = time.monotonic()
        resp = self.session.get(url, params=query, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    # ─── Discover ─────────────────────────────────────────────────────────────

    def discover_movies(
        self,
        page: int = 1,
        strategy: Literal["popularity", "quality"] = "popularity",
        language: str = "en-US",
        include_adult: bool = False,
        min_year: int = 1990,
    ) -> list[dict]:
        """
        Descubre películas usando la estrategia indicada.

        Args:
            page:           Número de página (1-500 máximo en TMDB).
            strategy:       ``'popularity'`` (A) o ``'quality'`` (B).
            language:       Idioma de respuesta (afecta overviews).
            include_adult:  Incluir contenido adulto.
            min_year:       Año mínimo de estreno.

        Returns:
            Lista de dicts con los campos:
                ``{tmdb_id, title, year, overview, vote_average, vote_count,
                   original_language, genre_ids, popularity}``
        """
        strategy_params = STRATEGIES.get(strategy, STRATEGIES["popularity"]).copy()
        params = {
            **strategy_params,
            "page": page,
            "language": language,
            "include_adult": include_adult,
            "primary_release_date.gte": f"{min_year}-01-01",
            "with_original_language": "en",   # Filtramos en inglés para maximizar reviews en Letterboxd
        }

        logger.debug("TMDB discover | strategy=%s | page=%d", strategy, page)
        data = self._get("/discover/movie", params=params)

        results = []
        for item in data.get("results", []):
            release_date = item.get("release_date", "")
            year = release_date[:4] if release_date else ""
            results.append({
                "tmdb_id":           item["id"],
                "title":             item.get("title", ""),
                "year":              year,
                "overview":          item.get("overview", ""),
                "vote_average":      item.get("vote_average", 0),
                "vote_count":        item.get("vote_count", 0),
                "original_language": item.get("original_language", ""),
                "genre_ids":         item.get("genre_ids", []),
                "popularity":        item.get("popularity", 0),
                "poster_path":       item.get("poster_path", ""),
            })
        return results

    def get_total_pages(
        self,
        strategy: Literal["popularity", "quality"] = "popularity",
        min_year: int = 1990,
    ) -> int:
        """Retorna el total de páginas disponibles para la estrategia indicada."""
        strategy_params = STRATEGIES[strategy].copy()
        params = {
            **strategy_params,
            "page": 1,
            "primary_release_date.gte": f"{min_year}-01-01",
            "with_original_language": "en",
        }
        data = self._get("/discover/movie", params=params)
        return min(data.get("total_pages", 1), 500)  # TMDB limita a 500 páginas

    # ─── Detalles de película ─────────────────────────────────────────────────

    def get_movie_details(self, tmdb_id: int) -> dict:
        """
        Obtiene los detalles completos de una película incluyendo créditos e IDs externos.

        Usa ``append_to_response=credits,external_ids`` para obtener todo en
        una sola petición HTTP.

        Args:
            tmdb_id: ID numérico de TMDB.

        Returns:
            dict con los campos enriquecidos:
                ``{tmdb_id, title, year, overview, director, cast, genres,
                   budget, revenue, runtime, imdb_id, vote_average, vote_count,
                   original_language, poster_path}``
        """
        params = {"append_to_response": "credits,external_ids", "language": "en-US"}
        data = self._get(f"/movie/{tmdb_id}", params=params)

        # ── Extraer director y cast de credits ────────────────────────────────
        credits = data.get("credits", {})
        crew    = credits.get("crew", [])
        cast    = credits.get("cast", [])

        directors = [
            m["name"] for m in crew
            if m.get("job") == "Director"
        ]
        top_cast = [m["name"] for m in cast[:10]]  # Top 10 actores

        # ── Géneros ───────────────────────────────────────────────────────────
        genres = [g["name"] for g in data.get("genres", [])]

        # ── IDs externos ─────────────────────────────────────────────────────
        ext_ids = data.get("external_ids", {})
        imdb_id = ext_ids.get("imdb_id", "") or data.get("imdb_id", "")

        release_date = data.get("release_date", "")
        year = release_date[:4] if release_date else ""

        return {
            "tmdb_id":           tmdb_id,
            "title":             data.get("title", ""),
            "original_title":    data.get("original_title", ""),
            "year":              year,
            "overview":          data.get("overview", ""),
            "director":          ", ".join(directors),
            "cast":              top_cast,
            "genres":            genres,
            "budget":            data.get("budget", 0),
            "revenue":           data.get("revenue", 0),
            "runtime":           data.get("runtime", 0),
            "imdb_id":           imdb_id,
            "vote_average":      data.get("vote_average", 0),
            "vote_count":        data.get("vote_count", 0),
            "original_language": data.get("original_language", ""),
            "poster_path":       data.get("poster_path", ""),
            "tagline":           data.get("tagline", ""),
            "status":            data.get("status", ""),
            "source_url":        f"https://www.themoviedb.org/movie/{tmdb_id}",
        }

    # ─── Géneros (lookup) ─────────────────────────────────────────────────────

    def get_genre_map(self) -> dict[int, str]:
        """Retorna el mapa id→nombre de géneros para películas."""
        data = self._get("/genre/movie/list", params={"language": "en-US"})
        return {g["id"]: g["name"] for g in data.get("genres", [])}


# ─── Ejecución directa para prueba ───────────────────────────────────────────
if __name__ == "__main__":
    import json, sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    API_KEY = sys.argv[1] if len(sys.argv) > 1 else ""
    if not API_KEY:
        print("Uso: python crawler/tmdb_client.py <API_KEY>")
        sys.exit(1)

    client = TmdbClient(api_key=API_KEY)

    print("=== Estrategia A: Popularity ===")
    films = client.discover_movies(page=1, strategy="popularity")
    for f in films[:3]:
        print(f"  {f['title']} ({f['year']}) | votes={f['vote_count']} | avg={f['vote_average']}")

    print("\n=== Detalles: Oppenheimer (id=872585) ===")
    details = client.get_movie_details(872585)
    print(json.dumps({k: v for k, v in details.items() if k not in ("overview",)}, indent=2))
    print("Overview:", details["overview"][:200])
