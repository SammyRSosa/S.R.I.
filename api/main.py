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

class SearchResponse(BaseModel):
    """Estructura de respuesta de la API."""
    query: str
    total_results: int
    results: List[SearchResult]

# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, summary="Interfaz Visual", tags=["UI"])
async def read_root(request: Request):
    """
    Sirve la página web principal del buscador.
    """
    return templates.TemplateResponse("index.html", {"request": request})

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
    
    Proceso:
    1. Tokenización y normalización de la query.
    2. Cálculo de similitud p-norma (EBM).
    3. Cálculo de similitud de coseno sobre embeddings FAISS.
    4. Fusión de resultados mediante combinación lineal ponderada.
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
    
    for doc_id in all_doc_ids:
        s_ebm = ebm_map.get(doc_id, 0.0)
        s_vec = vector_map.get(doc_id, 0.0)
        
        # Combinación lineal con pesos configurables
        h_score = (s_ebm * request.ebm_weight) + (s_vec * request.vector_weight) 
        
        film = store.get_film(doc_id)
        if not film: continue
        
        # Generación de Snippet inteligente (contextual a la query)
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
            score=round(h_score, 4),
            ebm_score=round(s_ebm, 4),
            vector_score=round(s_vec, 4),
            snippet=snippet
        ))
        
    # Ordenar por score combinado y limitar a top_k
    combined.sort(key=lambda x: x.score, reverse=True)
    results = combined[:request.top_k]
    
    logger.info("Search: '%s' -> %d results.", query, len(combined))
    
    return SearchResponse(
        query=query,
        total_results=len(combined),
        results=results
    )
