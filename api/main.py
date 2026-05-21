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
    r"""
    Extrae metadatos duros de la consulta (ej. años de 4 dígitos) para filtrado determinista.
    
    Mathematical Definition:
    Let $Q$ be the raw input query string. We define an extraction mapping $f_{\text{extract}}: Q \to \mathcal{M}$:
    $$\mathcal{M} = \{ \text{"year"}: y \quad \forall y \in [1900, 2099] \subset \mathbb{N} \}$$
    where $y$ is a 4-digit substring matching the regular expression boundary:
    $$\text{Pattern} = \text{"\b(19|20)\d{2}\b"}$$
    If a match is found:
    $$\text{Filter}_{\text{year}}(d) \iff \text{year}(d) = y$$
    This is used for strict boolean context trimming before the rank fusion pass.
    """
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
    r"""
    Realiza una búsqueda híbrida utilizando el Modelo Booleano Extendido (EBM) y Búsqueda Semántica Vectorial.
    Activa la búsqueda web automatizada (Focused Crawling Fallback) si la relevancia o volumen local es insuficiente.

    =======================================================================================================
                            MATHEMATICAL DESIGN OF THE HYBRID SEARCH ENGINE
    =======================================================================================================

    1. Hybrid Linear Combination (Score Fusion)
    -------------------------------------------
    For each document $d$ in the union of Boolean and Vector candidate spaces:
        $$S_{\text{base}}(d) = w_{\text{EBM}} \cdot S_{\text{EBM}}(d) + w_{\text{vector}} \cdot S_{\text{vector}}(d)$$
    where $S_{\text{EBM}}(d)$ is the Salton $p$-norm score, and $S_{\text{vector}}(d)$ is the FAISS cosine 
    similarity score, with $w_{\text{EBM}} + w_{\text{vector}} = 1.0$ (typically $0.6$ and $0.4$).

    2. Advanced Ranking Positioning (Boosting & Feature Engineering)
    -----------------------------------------------------------------
    The base score is dynamically boosted by structural features extracted from the database:
        $$S_{\text{final}}(d) = S_{\text{base}}(d) + w_{\text{pop}} \cdot \Phi_{\text{pop}}(d) + w_{\text{fresh}} \cdot \Phi_{\text{fresh}}(d)$$
    where:
    - $\Phi_{\text{pop}}(d)$ is the popularity scaling function capped at a saturation upper-bound:
        $$\Phi_{\text{pop}}(d) = \min \left( 1.0, \frac{\text{popularity}(d)}{100.0} \right)$$
    - $\Phi_{\text{fresh}}(d)$ is the freshness decaying function modeling proximity to the current year $Y_{now}$:
        $$\Phi_{\text{fresh}}(d) = \max \left( 0.0, 1.0 - \frac{Y_{now} - Y(d)}{50.0} \right)$$

    3. Dynamic Fallback Switch Policy (Automatic Web Crawling)
    ---------------------------------------------------------
    Let $\mathcal{R}_{\text{local}}$ be the sorted local candidate list. The fallback crawl triggers 
    if the cardinal volume is critically low or the top score is below a minimum reliability threshold:
        $$\text{TriggerWeb}(Q) = [|\mathcal{R}_{\text{local}}| < 3] \lor \left[ \max_{d \in \mathcal{R}_{\text{local}}} S_{\text{final}}(d) < 0.15 \right]$$
    """
    query = request.query
    ebm.p = request.p
    
    # --- QUERY TRANSLATION ---
    translated_query = rag_manager.translate_query_for_ebm(query)
    
    # --- METADATA EXTRACTION (una vez, fuera del loop) ---
    extracted_meta = extract_metadata_from_query(query)
    target_year = extracted_meta.get('year')
    
    # 1. Búsqueda EBM (Lógica Booleana Suave) - Usando Query Traducida
    ebm_results = ebm.search(translated_query, op="OR")
    
    # 2. Búsqueda Semántica Vectorial (FAISS Local) - Usando Query Original
    try:
        vec_results = v_store.search(query, top_k=100) if v_store.index and v_store.index.ntotal > 0 else []
    except Exception as e:
        logger.error("Error en búsqueda vectorial: %s", e)
        vec_results = []
    
    logger.info("EBM devolvio %d resultados | VEC devolvio %d resultados", len(ebm_results), len(vec_results))
    
    # --- FUSIÓN HÍBRIDA: RECIPROCAL RANK FUSION (RRF) ---
    k_rrf = 60
    
    ebm_ranks = {doc_id: rank for rank, (doc_id, _) in enumerate(ebm_results, 1)}
    vec_ranks = {doc_id: rank for rank, (doc_id, _) in enumerate(vec_results, 1)}
    
    ebm_scores_map = {doc_id: score for doc_id, score in ebm_results}
    vec_scores_map = {doc_id: score for doc_id, score in vec_results}
    
    all_doc_ids = set(ebm_ranks.keys()) | set(vec_ranks.keys())
    
    combined = []
    from datetime import datetime
    current_year = datetime.now().year

    for doc_id in all_doc_ids:
        film = store.get_film(doc_id)
        if not film: 
            continue
            
        # --- HARD METADATA FILTER ---
        if target_year is not None:
            film_year = film.get("year")
            try:
                if int(film_year) != target_year:
                    continue
            except (ValueError, TypeError):
                continue
        
        # Obtener scores crudos para la UI y para el ranking
        s_ebm = ebm_scores_map.get(doc_id, 0.0)
        s_vec = vec_scores_map.get(doc_id, 0.0)
        
        # Score Base: Combinación lineal ponderada de scores crudos (ambos en rango 0-1)
        base_score = (s_ebm * request.ebm_weight) + (s_vec * request.vector_weight)

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
    
    # --- MÓDULO DE BÚSQUEDA WEB AUTOMÁTICO (Corte 3) ---
    # Usa el score COMBINADO (no solo EBM) para decidir si activar el fallback.
    # Esto evita búsquedas web innecesarias cuando ya hay buenos resultados locales.
    was_web_search = False
    top_combined = combined[0].score if combined else 0
    if len(combined) < 3 or top_combined < 0.15:
        logger.info("Activando Web Fallback: %d resultados locales, top_combined=%.3f", len(combined), top_combined)
        web_results = web_searcher.search_and_format(query)
        if web_results:
            was_web_search = True
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
    r"""
    Toma los resultados de búsqueda y genera una respuesta inteligente (RAG).

    =======================================================================================================
                        MATHEMATICAL DESIGN OF THE RAG CONTEXT SYSTEM
    =======================================================================================================
    Let $Q$ be the raw natural language input query, and $D = \{d_1, d_2, \dots, d_N\}$ be the set of 
    retrieved candidate documents, where each document is structured as a tuple:
        $$d_i = \langle \text{title}, \text{year}, \text{director}, \text{cast}, \text{genres}, \text{score}, \text{snippet} \rangle$$
    
    1. Information-Theoretic Context Serialization
    ----------------------------------------------
    We define a structural mapping $\mathcal{S}: D \to \mathcal{X}$ which formats and serializes the 
    retrieved records into a cohesive context text block $\mathcal{X} \in \Sigma^*$:
        $$\mathcal{S}(D) = \bigoplus_{i=1}^N \Big[ \text{"--- Película "} \cdot i \cdot \text{" ---\\n"} 
        \cdot \text{"Título: "} \cdot \text{title}(d_i) \cdot \text{"\nAño: "} \cdot \text{year}(d_i)
        \cdot \text{"\nDirector: "} \cdot \text{director}(d_i) \cdot \text{"\nReparto: "} \cdot \text{cast}(d_i)
        \cdot \text{"\nGéneros: "} \cdot \text{genres}(d_i) \cdot \text{"\nScore: "} \cdot \text{score}(d_i)
        \cdot \text{"\nResumen: "} \cdot \text{snippet}(d_i) \cdot \text{"\n"} \Big]$$
    where $\oplus$ is the string concatenation operator.

    2. Prompt Integration & Generative Auto-Regression
    --------------------------------------------------
    The system synthesizes the system instructions and serialized context to form the unified prompt template $P(Q, \mathcal{X})$:
        $$P(Q, \mathcal{X}) = \text{Template}_{\text{System}}(\mathcal{X}) \circ \text{Template}_{\text{User}}(Q)$$
    The generated response $R \in \Sigma^*$ is modeled as the maximum posterior probability sequence of tokens under the parameterized LLM:
        $$R = \arg\max_{Y} \prod_{t=1}^{T} P(y_t \mid y_1, y_2, \dots, y_{t-1}, P(Q, \mathcal{X}); \theta_{\text{LLM}})$$

    3. Closed-World Soundness & Anti-Hallucination Bound
    -----------------------------------------------------
    To enforce rigorous academic veracity, we impose a closed-world knowledge constraint:
        $$\text{Response}(Q, D) = \begin{cases} 
            f_{\text{LLM}}(P(Q, \mathcal{S}(D))) & \text{if } |D| > 0 \text{ and } \max_{d \in D} \text{score}(d) \ge \tau_{\text{reliability}} \\
            \text{"No se encontraron resultados relevantes en la base de datos..."} & \text{otherwise}
        \end{cases}$$
    """
    answer = rag_manager.generate_response(
        query=request.query,
        retrieved_docs=[r.model_dump() for r in request.results]
    )
    return ChatResponse(query=request.query, answer=answer)

@app.get("/recommend", response_model=List[RecommendationResult], summary="Recomendar películas similares", tags=["Recomendación"])
async def get_recommendations(doc_id: int, top_k: int = 5):
    r"""
    Retorna las películas más similares a la indicada por `doc_id`.
    Utiliza un modelo híbrido basado en contenido (VSM sobre TF-IDF + similitud estructurada Jaccard).

    =======================================================================================================
                    MATHEMATICAL DESIGN OF THE CONTENT RECOMMENDATION ENGINE
    =======================================================================================================
    Let $d_{\text{seed}} \in \mathcal{D}$ be the seed movie document identified by `doc_id`, and 
    $d_j \in \mathcal{D} \setminus \{d_{\text{seed}}\}$ be any candidate movie in the database.
    We compute the hybrid content similarity metric $\text{Sim}_{\text{Hybrid}}(d_{\text{seed}}, d_j)$ 
    by convexly fusing vector space textual similarity and structural categorical attribute overlap:
        $$\text{Sim}_{\text{Hybrid}}(d_{\text{seed}}, d_j) = \alpha \cdot \text{Sim}_{\text{Cosine}}(d_{\text{seed}}, d_j) + (1.0 - \alpha) \cdot \text{Sim}_{\text{Meta}}(d_{\text{seed}}, d_j)$$
    where \alpha \in [0, 1] represents the unstructured-to-structured textual blending weight (default \alpha = 0.5).

    1. Sparse Unstructured Text Vector Space Model (VSM) Cosine Similarity
    -----------------------------------------------------------------------
    Let $w_{t, i}$ denote the TF-IDF weight of word token $t$ in document $d_i$:
        $$\text{Sim}_{\text{Cosine}}(d_{\text{seed}}, d_j) = \frac{\sum_{t \in (d_{\text{seed}} \cap d_j)} w_{t, \text{seed}} \cdot w_{t, j}}{\|d_{\text{seed}}\|_2 \cdot \|d_j\|_2} = \frac{\sum_{t \in (d_{\text{seed}} \cap d_j)} w_{t, \text{seed}} \cdot w_{t, j}}{\sqrt{\sum_{t \in d_{\text{seed}}} w_{t, \text{seed}}^2} \cdot \sqrt{\sum_{t \in d_j} w_{t, j}^2}}$$
    To guarantee high-throughput under $O(1)$ real-time latency constraints, we employ an inverted-index sparse 
    intersection scan rather than brute-force pairwise matrix computation.

    2. Structured Metadata Categorical Coefficients
    ----------------------------------------------
    Structured categorical fields (genres, director, cast) are compared using a combination of Jaccard set coefficients 
    and exact Kronecker delta match metrics:
        $$\text{Sim}_{\text{Meta}}(d_{\text{seed}}, d_j) = \beta_1 \cdot J(\mathcal{G}_{\text{seed}}, \mathcal{G}_j) + \beta_2 \cdot \mathbb{I}(\text{dir}_{\text{seed}} = \text{dir}_j) + \beta_3 \cdot J(\mathcal{C}_{\text{seed}}, \mathcal{C}_j)$$
    where:
    - $J(A, B) = \frac{|A \cap B|}{|A \cup B|}$ is the Jaccard similarity between finite sets $A$ and $B$.
    - $\mathcal{G}_i$ represents the genre set of document $d_i$, weighted by \beta_1 = 0.5.
    - \mathbb{I}(\cdot) \in \{0, 1\} is the binary Kronecker indicator function verifying direct matching of 
      canonicalized directors \text{dir}_i, weighted by \beta_2 = 0.3.
    - $\mathcal{C}_i$ is the set containing the top 5 billed cast members of document $d_i$, weighted by \beta_3 = 0.2.

    3. Ranking and Recommendation Space Trimming
    --------------------------------------------
    The final selection of recommendation results is defined by ordering candidates in descending order of hybrid similarity:
        $$\mathcal{R}_{\text{recommendations}} = \text{Top-K} \Big( \arg\text{sort}_{d_j \in \mathcal{D} \setminus \{d_{\text{seed}}\}} \text{Sim}_{\text{Hybrid}}(d_{\text{seed}}, d_j) \Big)$$
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
