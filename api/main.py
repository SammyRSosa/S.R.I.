import logging
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from database.store import DocumentStore
from indexer.inverted_index import InvertedIndex
from indexer.ebm import ExtendedBooleanModel
from database.vector_store import VectorStore
from api.rag import rag_manager
from crawler.web_search import web_searcher

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

# Cargar motores de ranking avanzado (EBM y FAISS)
ebm = ExtendedBooleanModel(store, idx, p=2.0)
v_store = VectorStore()

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
        "model": "Hybrid (EBM + Vector)",
        "docs_loaded": len(store.documents),
        "vocab_size": idx.vocabulary_size,
        "vector_index_size": v_store.index.ntotal if v_store.index else 0
    }

@app.post("/search", response_model=SearchResponse, summary="Búsqueda Híbrida", tags=["Recuperación"])
async def search(request: SearchRequest):
    """
    Realiza una búsqueda combinando el Modelo Booleano Extendido y Búsqueda Vectorial.
    Activa búsqueda web si los resultados locales son insuficientes.
    """
    query = request.query
    ebm.p = request.p
    
    # 1. Búsqueda EBM (Lógica Booleana Suave)
    ebm_results = ebm.search(query, op="OR")
    ebm_map = {doc_id: score for doc_id, score in ebm_results}
    
    # 2. Búsqueda Vectorial (Semántica profunda)
    vector_results = v_store.search(query, top_k=50)
    vector_map = {doc_id: score for doc_id, score in vector_results}
    
    # 3. Combinación Híbrida y Generación de Snippets
    all_doc_ids = set(ebm_map.keys()) | set(vector_map.keys())
    combined = []
    
    # Obtener el año actual para cálculo de frescura
    from datetime import datetime
    current_year = datetime.now().year

    for doc_id in all_doc_ids:
        s_ebm = ebm_map.get(doc_id, 0.0)
        s_vec = vector_map.get(doc_id, 0.0)
        
        # Combinación lineal base
        h_score = (s_ebm * request.ebm_weight) + (s_vec * request.vector_weight) 
        
        film = store.get_film(doc_id)
        if not film: continue
        
        # --- POSICIONAMIENTO AVANZADO (Corte 3) ---
        # 1. Factor Popularidad (Normalizado de 0 a 1, asumiendo max ~100)
        pop = float(film.get("popularity", 0))
        pop_factor = min(1.0, pop / 100.0) * 0.1 # Pesa un 10%
        
        # 2. Factor Frescura (Más recientes arriba)
        try:
            f_year = int(film.get("year", 0))
            fresh_factor = max(0, 1.0 - (current_year - f_year) / 50.0) * 0.05 # Pesa un 5%
        except:
            fresh_factor = 0
            
        final_score = h_score + pop_factor + fresh_factor
        
        # Generación de Snippet inteligente
        text = film.get("rich_text", "") or film.get("synopsis", "")
        tokens = idx._tokenize(query)
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
    # Disparador: Menos de 3 resultados o el mejor resultado tiene score bajo (< 0.25 en base h_score)
    top_score = combined[0].score if combined else 0
    if len(combined) < 3 or top_score < 0.25:
        web_results = web_searcher.search_and_format(query)
        if web_results:
            was_web_search = True
            # Convertir dicts a SearchResult objects
            web_objects = [SearchResult(**r) for r in web_results]
            combined.extend(web_objects)
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
