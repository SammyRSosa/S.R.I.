import logging
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

import re
from database.store import DocumentStore
from indexer.inverted_index import InvertedIndex
from indexer.ebm import ExtendedBooleanModel
from api.rag import rag_manager
from crawler.web_search import web_searcher
from database.vector_store import VectorStore
from indexer.recommender import MovieRecommender

# ─── Query Parser ─────────────────────────────────────────────────────────────
def extract_metadata_from_query(query: str) -> dict:
    """Extrae metadatos duros de la consulta (ej. años de 4 dígitos)."""
    meta = {}
    # Buscar años entre 1900 y 2099
    match = re.search(r'\b(19|20)\d{2}\b', query)
    if match:
        meta['year'] = int(match.group(0))
    return meta

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Configuración de Rutas ──────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = Path(__file__).parent / "templates"

# ─── Inicialización de Motores ──────────────────────────────────────────────────

# Cargamos los recursos una sola vez al inicio del servidor para eficiencia
store = DocumentStore()
idx = InvertedIndex()

# Reconstruir índice base (frecuencias) en memoria si hay documentos
if store.documents:
    logger.info("Cargando %d documentos en el índice de memoria...", len(store.documents))
    for doc_id, data in store.documents.items():
        idx.add_film(doc_id, data)

# Cargar motores de ranking avanzado (EBM)
ebm = ExtendedBooleanModel(store, idx, p=2.0)

# Cargar motor de recomendaciones (VSM Híbrido)
recommender = MovieRecommender(store, ebm)

# Instanciar VectorStore (para resolver dependencias con scripts de evaluación y compatibilidad)
try:
    v_store = VectorStore(store.data_dir)
except Exception as e:
    logger.warning("Fallo al inicializar VectorStore local: %s. Usando en memoria.", e)
    v_store = VectorStore(in_memory=True)

# ─── Aplicación FastAPI ───────────────────────────────────────────────────────
app = FastAPI(
    title="Oscar Insight Search",
    description=(
        "Sistema de Recuperación Híbrido: Modelo Booleano Extendido + Semántica Vectorial. "
        "Proyecto de Sistemas de Recuperación de Información (SRI) 2025-2026."
    ),
    version="0.3.0",
)

# Configuración de templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ─── Schemas Pydantic ─────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    """Parámetros de entrada para la búsqueda híbrida."""
    query: str = Field(..., min_length=1, description="Texto de consulta en lenguaje natural.")
    top_k: int = Field(default=10, ge=1, le=50, description="Número de resultados a devolver.")
    p: float = Field(default=2.0, ge=1.0, description="Exponente para la p-norma del modelo EBM.")
    ebm_weight: float = Field(default=0.6, ge=0.0, le=1.0, description="Peso del score booleano (0-1).")
    vector_weight: float = Field(default=0.4, ge=0.0, le=1.0, description="Peso del score semántico (0-1).")
    pop_weight: float = Field(default=0.1, ge=0.0, le=1.0, description="Peso de la popularidad (0-1).")
    fresh_weight: float = Field(default=0.05, ge=0.0, le=1.0, description="Peso de la frescura (0-1).")

class SearchResult(BaseModel):
    """Representación de un resultado individual de búsqueda."""
    doc_id: int
    title: str
    year: str
    score: float
    ebm_score: float
    vector_score: float
    snippet: str
    director: str = "N/A"
    cast: List[str] = []
    genres: List[str] = []
    is_web_result: bool = False


class SearchResponse(BaseModel):
    """Estructura de respuesta de la API."""
    query: str
    total_results: int
    results: List[SearchResult]
    was_web_search: bool = False

class ChatRequest(BaseModel):
    """Parámetros para la generación de respuesta inteligente."""
    query: str
    results: List[SearchResult]

class ChatResponse(BaseModel):
    """Respuesta generada por el LLM."""
    query: str
    answer: str

class RecommendationResult(BaseModel):
    """Resultado individual de una película recomendada."""
    doc_id: int
    title: str
    year: str
    director: str
    genres: List[str]
    similarity: float
    cosine_similarity: float
    metadata_similarity: float

# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, summary="Interfaz Visual", tags=["UI"])
async def read_root(request: Request):
    """
    Sirve la página web principal del buscador.
    """
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/health", summary="Estado del Sistema", tags=["Sistema"])
async def health_check():
    """
    Verifica que los modelos e índices están cargados correctamente.
    """
    return {
        "status": "ok",
        "model": "Extended Boolean Model (EBM)",
        "docs_loaded": len(store.documents),
        "vocab_size": idx.vocabulary_size
    }

@app.post("/search", response_model=SearchResponse, summary="Búsqueda Local EBM con Web Fallback", tags=["Recuperación"])
async def search(request: SearchRequest):
    """
    Realiza una búsqueda utilizando el Modelo Booleano Extendido (EBM) de forma exclusiva para el corpus local.
    Activa búsqueda web fallback si los resultados locales son insuficientes.
    """
    query = request.query
    ebm.p = request.p
    
    # --- QUERY TRANSLATION ---
    translated_query = rag_manager.translate_query_for_ebm(query)
    
    # 1. Búsqueda EBM (Lógica Booleana Suave) - Usando Query Traducida
    ebm_results = ebm.search(translated_query, op="OR")
    
    # 2. Búsqueda Semántica Vectorial (FAISS Local) - Usando Query Original
    vec_results = v_store.search(query, top_k=100) if v_store.index and v_store.index.ntotal > 0 else []
    
    # --- FUSIÓN HÍBRIDA: RECIPROCAL RANK FUSION (RRF) ---
    # RRF formula: 1 / (k + rank) donde k es típicamente 60
    k_rrf = 60
    
    # Convertir resultados a diccionarios de rangos (rank empieza en 1)
    ebm_ranks = {doc_id: rank for rank, (doc_id, _) in enumerate(ebm_results, 1)}
    vec_ranks = {doc_id: rank for rank, (doc_id, _) in enumerate(vec_results, 1)}
    
    # Diccionarios para scores crudos (para mostrar en la UI)
    ebm_scores_map = {doc_id: score for doc_id, score in ebm_results}
    vec_scores_map = {doc_id: score for doc_id, score in vec_results}
    
    # Unir todos los IDs de documentos recuperados por ambos motores
    all_doc_ids = set(ebm_ranks.keys()) | set(vec_ranks.keys())
    
    # 3. Construcción de resultados locales y cálculo de score RRF combinado
    combined = []
    
    # Obtener el año actual para cálculo de frescura
    from datetime import datetime
    current_year = datetime.now().year

    for doc_id in all_doc_ids:
        film = store.get_film(doc_id)
        if not film: 
            continue
            
        # --- HARD METADATA FILTER ---
        extracted_meta = extract_metadata_from_query(query)
        target_year = extracted_meta.get('year')
        
        if target_year is not None:
            film_year = film.get("year")
            try:
                # Si el año no coincide, filtramos estrictamente
                if int(film_year) != target_year:
                    continue
            except (ValueError, TypeError):
                continue # Si la película no tiene un año válido y se requiere uno
        
        # Cálculo RRF
        rank_ebm = ebm_ranks.get(doc_id, 1000) # Si no está, penalizar rango
        rank_vec = vec_ranks.get(doc_id, 1000)
        
        rrf_ebm = 1.0 / (k_rrf + rank_ebm)
        rrf_vec = 1.0 / (k_rrf + rank_vec)
        
        # Obtener scores crudos para la UI
        s_ebm = ebm_scores_map.get(doc_id, 0.0)
        s_vec = vec_scores_map.get(doc_id, 0.0)
        
        # Score Base (RRF Ponderado) -> RRF produce números pequeños, escalamos artificialmente para la UI
        base_score = ((rrf_ebm * request.ebm_weight) + (rrf_vec * request.vector_weight)) * 100.0

        # --- POSICIONAMIENTO AVANZADO (Corte 3) ---
        # 1. Factor Popularidad (Normalizado de 0 a 1, asumiendo max ~100)
        pop = float(film.get("popularity", 0))
        pop_factor = min(1.0, pop / 100.0) * request.pop_weight
        
        # 2. Factor Frescura (Más recientes arriba)
        try:
            f_year = int(film.get("year", 0))
            fresh_factor = max(0, 1.0 - (current_year - f_year) / 50.0) * request.fresh_weight
        except:
            fresh_factor = 0
            
        final_score = base_score + pop_factor + fresh_factor
        
        # Generación de Snippet inteligente (Usando translated_query para encontrar tokens en el texto local en inglés)
        text = film.get("rich_text", "") or film.get("synopsis", "")
        tokens = idx._tokenize(translated_query)
        snippet = text[:200] + "..."
        for t in tokens:
            idx_t = text.lower().find(t)
            if idx_t != -1:
                start = max(0, idx_t - 60)
                end = min(len(text), idx_t + 140)
                snippet = "..." + text[start:end] + "..."
                break
        
        combined.append(SearchResult(
            doc_id=doc_id,
            title=film.get("title", "Unknown"),
            year=str(film.get("year", "N/A")),
            score=round(final_score, 4),
            ebm_score=round(s_ebm, 4),
            vector_score=round(s_vec, 4),
            snippet=snippet,
            director=film.get("director", "N/A"),
            cast=film.get("cast", []),
            genres=film.get("genres", []),
            is_web_result=False
        ))
        
    # Ordenar por score combinado
    combined.sort(key=lambda x: x.score, reverse=True)
    
    # --- MÓDULO DE BÚSQUEDA WEB AUTOMÁTICO (Corte 2) ---
    was_web_search = False
    # Disparador: Menos de 3 resultados o el mejor resultado tiene score bajo (< 0.25)
    top_score = combined[0].score if combined else 0
    if len(combined) < 3 or top_score < 0.25:
        web_results = web_searcher.search_and_format(query)
        if web_results:
            was_web_search = True
            # Convertir dicts a SearchResult objects
            web_objects = [SearchResult(**r) for r in web_results]
            combined.extend(web_objects)
            # Re-ordenar la combinación por score
            combined.sort(key=lambda x: x.score, reverse=True)

    results = combined[:request.top_k]
    logger.info("Search: '%s' -> %d results (Web: %s).", query, len(combined), was_web_search)
    
    return SearchResponse(
        query=query,
        total_results=len(combined),
        results=results,
        was_web_search=was_web_search
    )

@app.post("/chat", response_model=ChatResponse, summary="Generación RAG", tags=["Recuperación"])
async def chat(request: ChatRequest):
    """
    Toma los resultados de búsqueda y genera una respuesta inteligente (RAG).
    """
    answer = rag_manager.generate_response(
        query=request.query,
        retrieved_docs=[r.model_dump() for r in request.results]
    )
    return ChatResponse(query=request.query, answer=answer)

@app.get("/recommend", response_model=List[RecommendationResult], summary="Recomendar películas similares", tags=["Recomendación"])
async def get_recommendations(doc_id: int, top_k: int = 5):
    """
    Retorna las películas más similares a la indicada por `doc_id`.
    Utiliza un modelo híbrido basado en contenido (VSM sobre TF-IDF + similitud estructurada Jaccard).
    """
    # Validar si el documento semilla existe
    film = store.get_film(doc_id)
    if not film:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Película con doc_id {doc_id} no encontrada en la base de datos local."
        )
    
    try:
        recommendations = recommender.recommend(doc_id, top_k=top_k)
        return recommendations
    except Exception as e:
        logger.error("Error al generar recomendaciones para doc_id %d: %s", doc_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno al procesar las recomendaciones: {str(e)}"
        )
