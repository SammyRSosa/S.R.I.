"""
api/main.py
Módulo de Recuperación Híbrido — Oscar Insight Search (Corte 2)

Implementa el motor de búsqueda basado en el Modelo Booleano Extendido (p-norm)
y Búsqueda Semántica (embeddings FAISS).
"""

from __future__ import annotations

import logging
from typing import Optional, List

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from database.store import DocumentStore
from indexer.inverted_index import InvertedIndex
from indexer.ebm import ExtendedBooleanModel
from database.vector_store import VectorStore

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Inicialización de Motores ──────────────────────────────────────────────────

# Cargamos los recursos una sola vez al inicio del servidor
store = DocumentStore()
idx = InvertedIndex()

# Reconstruir índice base (frecuencias) en memoria
if store.documents:
    for doc_id, data in store.documents.items():
        idx.add_film(doc_id, data)

# Cargar motores de ranking avanzado
ebm = ExtendedBooleanModel(store, idx, p=2.0)
v_store = VectorStore()

# ─── Aplicación ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Oscar Insight Search (Corte 2)",
    description=(
        "Sistema de Recuperación Híbrido: Modelo Booleano Extendido + Semántica Vectorial."
    ),
    version="0.2.0",
)


# ─── Schemas Pydantic ─────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=50)
    p: float = Field(default=2.0, ge=1.0, description="Exponente para la p-norma del EBM.")
    hybrid: bool = Field(default=True, description="Si es True, combina Booleano con Semántico.")

class SearchResult(BaseModel):
    doc_id: int
    title: str
    year: str
    score: float
    ebm_score: float
    vector_score: float
    snippet: str

class SearchResponse(BaseModel):
    query: str
    total_results: int
    results: List[SearchResult]

# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "status": "ok",
        "model": "Hybrid (EBM + Vector)",
        "docs": len(store.documents),
        "vocab": idx.vocabulary_size
    }

@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    Ejecuta una búsqueda híbrida:
    1. Recupera relevancia por Modelo Booleano Extendido (p-norm).
    2. Recupera relevancia por Similitud de Coseno (FAISS).
    3. Combina y ordena por Score Híbrido.
    """
    query = request.query
    ebm.p = request.p
    
    # 1. Búsqueda EBM (Booleana Suave)
    # Por defecto usamos OR para lenguaje natural, AND si queremos rigurosidad.
    ebm_results = ebm.search(query, op="OR")
    ebm_map = {doc_id: score for doc_id, score in ebm_results}
    
    # 2. Búsqueda Vectorial (Semántica)
    vector_results = v_store.search(query, top_k=50)
    vector_map = {doc_id: score for doc_id, score in vector_results}
    
    # 3. Combinación Híbrida
    all_doc_ids = set(ebm_map.keys()) | set(vector_map.keys())
    combined = []
    
    for doc_id in all_doc_ids:
        s_ebm = ebm_map.get(doc_id, 0.0)
        s_vec = vector_map.get(doc_id, 0.0)
        
        # Ponderación 50/50 por defecto
        # Evitamos que documentos sin nexo textual pero con cercanía vectorial dominen si s_ebm es 0
        h_score = (s_ebm * 0.6) + (s_vec * 0.4) 
        
        film = store.get_film(doc_id)
        if not film: continue
        
        # Generar fragmento relevante (snippet) del rich_text
        text = film.get("rich_text", "") or film.get("synopsis", "")
        # Heurística simple: buscar primera aparición de algún término de la consulta
        tokens = idx._tokenize(query)
        snippet = text[:200] + "..."
        for t in tokens:
            idx_t = text.lower().find(t)
            if idx_t != -1:
                start = max(0, idx_t - 40)
                end = min(len(text), idx_t + 160)
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
        
    # Ordenar por score combinado descendente
    combined.sort(key=lambda x: x.score, reverse=True)
    results = combined[:request.top_k]
    
    return SearchResponse(
        query=query,
        total_results=len(combined),
        results=results
    )
