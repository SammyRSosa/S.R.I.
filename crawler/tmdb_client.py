"""
crawler/tmdb_client.py
Cliente TMDB v3 — Oscar Insight Search (SRI 2025-2026)

=======================================================================================================
            MATHEMATICAL & TECHNICAL THEORY OF THROTTLE CONTROL AND BATCH ACQUISITION
=======================================================================================================

This module implements a transactional acquisition client for TMDB v3.

1. API Rate Limiting Throttle Control Heuristics
------------------------------------------------
The TMDB public tier operates on rate quotas defined by:
    $$\text{Quota} \le 40 \text{ requests} / 10 \text{ seconds}$$
To ensure execution does not exceed the capacity limit, we implement a strict temporal lock delta:
    $$\Delta t = 0.27 \text{ seconds}$$
Let $t_i$ be the epoch timestamp of the start of request $i$. The client enforces a thread-blocking delay:
    $$d_i = \max \left( 0, \Delta t - (t_i - t_{i-1}) \right)$$
The sequential frequency of request execution is bounded by:
    $$f_{\text{request}} = \frac{1}{\Delta t} \approx 3.703 \text{ requests/sec} < 4.000 \text{ requests/sec}$$
This mathematically guarantees compliance without the overhead of thread-safe token bucket algorithms.

2. Discovery Strategy Partitioning
----------------------------------
We structure document discovery into two separate strategies to represent different subsets of the film distribution space:
- Strategy A (Popularity-Driven Seed Space):
  Discovers movies sorted by popularity with a lower bound constraint on vote density to guarantee downstream scraper coverage:
    $$\mathcal{D}_{pop} = \{ m \in \text{TMDB} \mid \text{sort\_by}(m) = \text{"popularity.desc"} \land \text{votes}(m) \ge 100 \}$$
- Strategy B (Quality-Driven Seed Space):
  Discovers critical acclaim films with high statistical significance bounds:
    $$\mathcal{D}_{qual} = \{ m \in \text{TMDB} \mid \text{sort\_by}(m) = \text{"vote\_average.desc"} \land \text{votes}(m) \ge 500 \}$$

3. RTT Optimizations via Context Aggregation
--------------------------------------------
Rather than triggering multiple independent HTTP transactions forcredits and metadata:
    $$\text{RTT}_{\text{naive}} = \text{RTT}_{\text{details}} + \text{RTT}_{\text{credits}} + \text{RTT}_{\text{ids}}$$
We optimize network utilization using appending headers `append_to_response=credits,external_ids` which collapses requests into a single network cycle:
    $$\text{RTT}_{\text{optimal}} = \text{RTT}_{\text{aggregated}}$$
This achieves a speedup factor of $S \approx 3.0$ for each database entity populated.
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
    Cliente ligero para la API v3 de TMDB con control secuencial de frecuencia de red (Throttling).

    Soporta autenticación mediante API key (query param) o Bearer token (header).
    Se recomienda pasar ambos: api_key para simplificar los parámetros, y
    access_token para endpoints que requieren Bearer (como algunas listas).
    """

    def __init__(
        self,
        api_key: str = "",
        access_token: str = "",
    ) -> None:
        """
        Inicializa el cliente TMDB configurando el canal HTTP persistente (requests.Session).
        
        Initialization Model:
        $$\mathcal{H}_{auth} = \begin{cases} 
           \text{"Authorization: Bearer " } \mathbin{\|} \text{access\_token} & \text{if access\_token exists} \\
           \emptyset & \text{otherwise}
        \end{cases}$$
        """
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
        GET autenticado con rate limiting estricto secuencial.

        Args:
            endpoint: Ruta relativa de la API (ej. ``/discover/movie``).
            params:   Parámetros de consulta ad-hoc.

        Returns:
            Estructura deserializada JSON como diccionario.
            
        Mathematical Throttling Proof:
        Let $t_i$ be the time metric at the current iteration, and $t_{i-1}$ be the timestamp of the last request.
        $$\delta_i = t_i - t_{i-1}$$
        If $\delta_i < 0.27$, the thread pauses for $t_{sleep} = 0.27 - \delta_i$.
        This bounds the aggregate frequency:
        $$\lim_{N \to \infty} \frac{N}{\sum_{i=1}^N (0.27 + \epsilon_i)} \le 3.703 \text{ requests/second}$$
        where $\epsilon_i \ge 0$ is network latency jitter.
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
            page:           Número de página de la API TMDB ($P \in [1, 500]$).
            strategy:       Estrategia léxica: ``'popularity'`` (A) o ``'quality'`` (B).
            language:       Configuración de localización.
            include_adult:  Filtro de clasificación.
            min_year:       Año límite inferior para la ventana temporal.

        Returns:
            Lista de diccionarios que representan los metadatos de las películas.
            
        Seed Strategy Formulation:
        Let $\theta_{strategy}$ be the set of query parameters:
        $$\theta_{popularity} = \{ \text{sort\_by} = \text{"popularity.desc"}, \text{vote\_count.gte} = 100 \}$$
        $$\theta_{quality} = \{ \text{sort\_by} = \text{"vote\_average.desc"}, \text{vote\_count.gte} = 500 \}$$
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
        """
        Retorna el total de páginas disponibles para la estrategia indicada.
        
        Boundary Limit:
        $$\text{Pages}_{total} = \min \left( \text{TMDB\_response.total\_pages}, 500 \right)$$
        """
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

        Args:
            tmdb_id: ID numérico de TMDB.

        Returns:
            Diccionario de metadatos enriquecidos de la película.
            
        Aggregation Speedup Proof:
        Triggering separate sub-resource lookups requires:
        $$T_{naive} = \text{RTT}_{\text{details}} + \text{RTT}_{\text{credits}} + \text{RTT}_{\text{external\_ids}}$$
        Using appending parameter query strings collapses network calls into a single transaction:
        $$T_{aggregated} = \text{RTT}_{\text{aggregated}}$$
        $$\text{Speedup} = \frac{T_{naive}}{T_{aggregated}} \approx 3.0 \quad \text{(under zero cache bounds)}$$
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
        """
        Retorna el mapa id→nombre de géneros para películas.
        
        Lookup Mapping:
        $$\mathcal{G}_{map}: \mathcal{K}_{genre} \to \mathcal{S}_{name}$$
        """
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
