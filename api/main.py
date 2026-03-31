"""
api/main.py
Módulo de Recuperación / RAG — Oscar Insight Search (SRI 2025-2026)

Esqueleto FastAPI que expondrá el motor de búsqueda basado en el
Modelo Booleano Extendido (Corte 2+).

Endpoints implementados:
    GET  /          → Health check
    POST /search    → Placeholder: búsqueda por consulta booleana (Corte 2)
    POST /index     → Placeholder: indexación de nueva película (Corte 2)
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Aplicación ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Oscar Insight Search",
    description=(
        "Sistema de Recuperación de Información sobre Cine y Premios Oscar. "
        "Modelo: Booleano Extendido (Baeza-Yates & Ribeiro-Neto, 2011). "
        "Dominio: Letterboxd + IMDb."
    ),
    version="0.1.0",
    contact={
        "name": "SRI 2025-2026 Team",
        "url": "https://github.com/sri-2025/oscar-insight",
    },
    license_info={"name": "MIT"},
)


# ─── Schemas Pydantic ─────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    """Parámetros de una consulta de búsqueda."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Consulta booleana o de texto libre. Ej: 'Oscar AND director'",
        examples=["Best Picture 2024", "Oppenheimer AND director"],
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Número máximo de resultados a retornar.",
    )
    year_filter: Optional[int] = Field(
        default=None,
        ge=1927,
        description="Filtro opcional: sólo películas de este año.",
    )


class SearchResult(BaseModel):
    """Un resultado individual de búsqueda."""

    doc_id: int = Field(..., description="ID interno del documento.")
    title: str = Field(..., description="Título de la película.")
    year: str = Field(..., description="Año de estreno.")
    score: float = Field(..., description="Puntuación de relevancia [0, 1].")
    snippet: str = Field(..., description="Fragmento de texto relevante.")


class SearchResponse(BaseModel):
    """Respuesta completa de una consulta de búsqueda."""

    query: str
    total_results: int
    results: list[SearchResult]


class IndexRequest(BaseModel):
    """Solicitud para indexar una nueva película."""

    url: str = Field(
        ...,
        description="URL de la película en Letterboxd.",
        examples=["https://letterboxd.com/film/oppenheimer-2023/"],
    )
    doc_id: Optional[int] = Field(
        default=None,
        description="ID manual (opcional). Si no se provee, se asigna automáticamente.",
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get(
    "/",
    summary="Health Check",
    tags=["Sistema"],
    response_description="Estado del sistema y versión de la API.",
)
async def root() -> dict:
    """
    Verifica que el servicio está en funcionamiento.

    Returns:
        JSON con estado, nombre del sistema y versión.
    """
    return {
        "status": "ok",
        "service": "Oscar Insight Search",
        "version": "0.1.0",
        "model": "Extended Boolean Model",
        "corte": 1,
        "message": "API operativa. Motor de búsqueda en construcción (Corte 2).",
    }


@app.post(
    "/search",
    response_model=SearchResponse,
    summary="Búsqueda de Películas",
    tags=["Recuperación"],
    status_code=status.HTTP_200_OK,
)
async def search(request: SearchRequest) -> SearchResponse:
    """
    **[PLACEHOLDER — Corte 2]** Ejecuta una consulta sobre el índice invertido
    usando el Modelo Booleano Extendido.

    En Corte 2 este endpoint:
    1. Tokenizará y normalizará la consulta (`InvertedIndex._tokenize`).
    2. Recuperará posting lists para cada término.
    3. Calculará similitud EBM con distancias euclidianas ponderadas por tf-idf.
    4. Retornará los top-k documentos ordenados por score descendente.

    Por ahora retorna un 501 informativo.
    """
    logger.info("Query recibida: '%s' | top_k=%d", request.query, request.top_k)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": "Motor de búsqueda EBM pendiente de implementación (Corte 2).",
            "query": request.query,
            "hint": "El InvertedIndex base ya está disponible en indexer/inverted_index.py",
        },
    )


@app.post(
    "/index",
    summary="Indexar Película",
    tags=["Adquisición"],
    status_code=status.HTTP_202_ACCEPTED,
)
async def index_film(request: IndexRequest) -> dict:
    """
    **[PLACEHOLDER — Corte 2]** Ordena la adquisición e indexación de una película
    desde Letterboxd.

    En Corte 2 este endpoint:
    1. Llamará a `LetterboxdScraper.scrape_film(url)`.
    2. Pasará el resultado a `InvertedIndex.add_film(doc_id, film_data)`.
    3. Persistirá el índice actualizado en la base de datos.

    Por ahora retorna un 501 informativo.
    """
    logger.info("Solicitud de indexación: %s", request.url)
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "message": "Endpoint de indexación pendiente (Corte 2).",
            "url": request.url,
            "hint": "Usa crawler/scraper.py e indexer/inverted_index.py directamente.",
        },
    )
