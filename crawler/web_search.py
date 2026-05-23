"""
crawler/web_search.py
Módulo de Búsqueda Web Fallback con Crawler Persistente y Vectorización Temporal.

=======================================================================================================
                        MATHEMATICAL AND ALGORITHMIC FORMALISMS OF WEB SEARCH & CRAWL
=======================================================================================================

This module implements a dynamic fallback web searching and parallel crawling pipeline designed to 
mitigate corpus incompleteness. It bypasses conventional search engines via a direct scraper targeting
the lightweight DuckDuckGo HTML engine, and then processes retrieved target URLs.

1. Mathematical Text Chunking (Sliding Window Model)
---------------------------------------------------
To prevent input token saturation in downstream embedding models (e.g., SentenceTransformers), 
raw web content is split using a sliding window chunking partitioner.
Let $T$ be the input sequence of characters of length $|T|$.
Given a chunk size $L_{chunk}$ and a sliding overlap $O_{overlap}$, the step size $S$ is defined as:
    $$S = L_{chunk} - O_{overlap}$$
The $k$-th chunk is defined by the slice of text:
    $$C_k = T[\, k \cdot S \;\;:\;\; k \cdot S + L_{chunk} \,]$$
where $k \in \mathbb{N}_0$ and $k \cdot S < |T|$.
This guarantees that structural and grammatical context at boundary divisions is preserved in at least 
one adjacent chunk block.

2. Concurrent Crawling (ThreadPool Threading Model)
---------------------------------------------------
Let $U = \{u_1, u_2, ..., u_n\}$ be the set of valid, non-blocked URLs discovered from the search engine.
To maximize network bandwidth utilization while staying within polite thread-pool bounds, we model 
crawling via a Parallel Thread Pool Executor with $W$ workers.
The concurrent latency is modeled as:
    $$\text{Latency}_{total} = \max_{p \in [1..W]} \left( \sum_{i \in S_p} \text{RTT}(u_i) + \delta_i \right)$$
where $S_p$ is the partition of URLs assigned to worker thread $p$, $\text{RTT}(u_i)$ is the network round-trip time, 
and $\delta_i$ is the HTML parsing overhead.

3. Temporal Vector Space Model (FAISS FlatIP Cosine Space)
-----------------------------------------------------------
Once page contents are downloaded, they are chunked and embedded in a temporal in-memory FAISS Vector Store.
Let $C_1, C_2, ..., C_m$ be the text chunks. We map each chunk to a dense numerical vector using a bi-encoder 
neural network model $\phi(C_i)$:
    $$\mathbf{e}_i = \phi(C_i) \in \mathbb{R}^d$$
To compute semantic similarity using the inner product efficiently, the vectors are normalized under the $L_2$ norm:
    $$\mathbf{\hat{e}}_i = \frac{\mathbf{e}_i}{\|\mathbf{e}_i\|_2} = \frac{\mathbf{e}_i}{\sqrt{\sum_{j=1}^d e_{i,j}^2}}$$
For a normalized query vector $\mathbf{\hat{e}}_q = \frac{\phi(Q)}{\|\phi(Q)\|_2}$, the inner product computed 
by `faiss.IndexFlatIP` matches the mathematical cosine similarity exactly:
    $$\text{Sim}_{cosine}(Q, C_i) = \langle \mathbf{\hat{e}}_q, \mathbf{\hat{e}}_i \rangle = \sum_{j=1}^d \hat{e}_{q,j} \cdot \hat{e}_{i,j}$$
The temporary FAISS index performs an exact brute-force search over the $m$ temporal vectors, sorting in $O(m \cdot d)$ time.

4. Algorithmic Pipeline & Data Flow
------------------------------------
  [User Query] ──> [Query Context Enrichment] ──> [DuckDuckGo HTML POST Request]
                                                               │
                                                               ▼
  [In-Memory FAISS Retrieval] <── [L2 Norm] <── [Temporal Embeddings] <── [Filtered URL Collection]
               │                                                      (Exclude Blocked Domains)
               ▼                                                               │
  [Output Top-K JSON Results] <── [DB Corpus Auto-Enrichment] <── [Thread Pool Parallel Scraping]
                                  (Permanent Store Insertion)
"""

import logging
import re
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

from database.vector_store import VectorStore

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def extract_text_from_html(html_content: str) -> str:
    """
    HEURISTIC HTML TEXT PARSING AND DOM NOISE REDUCTION
    ===================================================
    Converts raw, structurally noisy HTML content into highly clean raw text suitable for indexation.
    
    1. DOM Decoupling:
       Removes non-semantic structural nodes by matching:
       $$E_{noise} = \{\text{script}, \text{style}, \text{nav}, \text{footer}, \text{header}, \text{aside}, \text{form}, \text{iframe}, \text{noscript}, \text{link}, \text{meta}\}$$
       These nodes are stripped entirely from the DOM tree.
       
    2. Wikipedia Specific Cleaning Heuristics:
       Wikipedia documents contain redundant layout classes that degrade TF-IDF precision. 
       We decompose elements containing the following CSS classes:
       $$C_{noise} = \{\text{navbox}, \text{mw-jump-link}, \text{mw-editsection}, \text{reflist}, \text{reference}, \text{sidebar}, \text{toc}, \text{catlinks}, \text{noprint}\}$$
       
    3. Normalization:
       Extracts child text nodes and maps any sequence of multiple whitespace characters $\geq 1$ to a single space:
       $$f_{clean}(T) = \text{regex\_sub}(\text{"\s+"}, \text{" "}, \text{strip}(T))$$
    """
    soup = BeautifulSoup(html_content, "html.parser")
    # Eliminar elementos no textuales o de maquetación/UI
    for element in soup(["script", "style", "nav", "footer", "header", "aside",
                         "form", "iframe", "noscript", "link", "meta"]):
        element.extract()
    # Para Wikipedia: eliminar navboxes y referencias
    for cls in ["navbox", "mw-jump-link", "mw-editsection", "reflist",
                "reference", "sidebar", "toc", "catlinks", "noprint"]:
        for el in soup.find_all(class_=cls):
            el.decompose()
    text = soup.get_text(separator=" ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def chunk_text(text: str, chunk_size: int = 600, overlap: int = 120) -> List[str]:
    """
    SLIDING WINDOW PARTITIONING ALGORITHM
    =====================================
    Divides an unstructured text document into overlapping blocks to maintain semantic continuity.
    
    Formulation:
      Let $L_{text}$ be the string length.
      Let $L_{chunk}$ be the chunk size in characters (default 600).
      Let $O_{overlap}$ be the character overlap (default 120).
      Step size: $S = L_{chunk} - O_{overlap} = 480$.
      The set of windows $I$ is defined as:
      $$I = \left\{ [S \cdot k, \; S \cdot k + L_{chunk}] \;\middle|\; k \in \mathbb{N}_0, \; S \cdot k < L_{text} \right\}$$
    
    This ensures that any phrase of length $\leq O_{overlap}$ falls fully within at least one chunk.
    """
    chunks = []
    if not text:
        return chunks
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        start += chunk_size - overlap
    return chunks


def generate_smart_snippet(text: str, query: str) -> str:
    """
    SEMANTIC SENTINEL SNIPPET GENERATION
    ====================================
    Locates the most relevant slice of text matching query tokens to provide context-rich UI snippets.
    
    1. Term Filtering:
       Extracts set of significant query terms $Q_{sig} = \{ t \in \text{split}(Q) \mid \text{len}(t) > 3 \}$.
       
    2. Exact Substring Matching:
       For each term $t \in Q_{sig}$, finds the first matching character index $i_t$ in the text:
       $$i_t = \text{find}(t, \text{lowercase}(T))$$
       
    3. Window Extraction:
       Extracts a window of radius $R_{left} = 80$ and $R_{right} = 160$ around the match:
       $$W = T[\max(0, i_t - 80) \;\;:\;\; \min(|T|, i_t + 160)]$$
       
    Returns the snippet string prepended/appended with ellipses if boundaries are truncated.
    """
    text_lower = text.lower()
    tokens = [t.lower() for t in query.split() if len(t) > 3]
    
    snippet = text[:200] + "..."
    for t in tokens:
        idx = text_lower.find(t)
        if idx != -1:
            start = max(0, idx - 80)
            end = min(len(text), idx + 160)
            snippet = ("..." if start > 0 else "") + text[start:end].strip() + "..."
            break
    return snippet


# Cache global en memoria para no descargar robots.txt repetidamente por el mismo dominio externo
ROBOTS_CACHE: dict[str, RobotFileParser] = {}

def can_fetch_external(url: str) -> bool:
    """
    Verifica si una URL externa está permitida por su respectivo archivo robots.txt.
    Descarga y parsea el robots.txt en vivo con un timeout corto de 2.0 segundos.
    """
    from urllib.robotparser import RobotFileParser
    from urllib.parse import urlparse
    
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True
            
        domain = f"{parsed.scheme}://{parsed.netloc}"
        
        # Consultar cache en memoria
        if domain in ROBOTS_CACHE:
            rp = ROBOTS_CACHE[domain]
        else:
            logger.debug("[Robots.txt-Web] Descargando robots.txt para el dominio externo: %s", domain)
            rp = RobotFileParser()
            rp.set_url(f"{domain}/robots.txt")
            
            # Timeout corto de 2s para no degradar el tiempo de respuesta semántica de la API
            r = requests.get(f"{domain}/robots.txt", headers=HEADERS, timeout=2.0)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            else:
                # Si robots.txt no existe o da error, asumimos permitido
                rp.parse(["User-agent: *", "Allow: /"])
            ROBOTS_CACHE[domain] = rp
            
        user_agent = HEADERS["User-Agent"]
        allowed = rp.can_fetch(user_agent, url)
        logger.debug("[Robots.txt-Web] Validación de URL externa: %s | Permitida: %s", url, allowed)
        return allowed
    except Exception as e:
        logger.warning("[Robots.txt-Web] Fallo al verificar robots.txt para %s: %s. Permitido por defecto.", url, e)
        return True


def fetch_url(url: str, title: str) -> Optional[Dict[str, Any]]:
    """
    HTML HTTP ACQUISITION AND CONTEXT EXTRACTION
    ============================================
    Downloads remote resource via standard HTTP GET with timeout constraints to avoid blocking threads.
    Verifies compliance against external domain robots.txt rules before requesting.
    
    Network Safety:
      - Timeout: $\tau = 8.0$ seconds.
      - Status Verification: Returns clean parsed text only on HTTP 200.
    """
    # ── Verificar cumplimiento de robots.txt (Requerimiento de Cátedra) ──
    if not can_fetch_external(url):
        logger.warning("[Robots.txt-Web] ❌ URL externa desautorizada por robots.txt: %s. Saltando descarga.", url)
        return None

    try:
        logger.info(f"Crawler descargando página: {url}")
        r = requests.get(url, headers=HEADERS, timeout=8.0)
        if r.status_code == 200:
            text = extract_text_from_html(r.text)
            return {"text": text, "url": url, "title": title}
        else:
            logger.warning(f"Error {r.status_code} al descargar {url}")
    except Exception as e:
        logger.warning(f"Error en crawler al descargar {url}: {e}")
    return None


def _persist_crawled_pages(crawled_pages: List[Dict[str, Any]], query: str) -> int:
    """
    COOPERATIVE CORPUS ENRICHMENT & DEDUPLICATION ALGORITHM
    =======================================================
    Persists web crawled documents permanently inside the JSON DocumentStore to expand local vocabulary.
    
    1. Size Filtering:
       Only documents containing substantial text content are persisted:
       $$|T| \geq 300\text{ characters}$$
       
    2. Document Formatting & Adapter Schema:
       Formats the text into the structural Document v2 schema:
       - Set Title: "[Crawled] {Original Title}"
       - Extract Year: Matches $\text{regex\_search}(\text{"(19\\d{2}|20\\d{2})"})$ in Title/URL, otherwise default to "N/A"
       - Metadata: Set genres to ["Reference", "web_crawled"] and source_url = url
       
    3. Deduplication Key Matching:
       Uses `source_url` inside DocumentStore to prevent duplicate insertions:
       $$\text{URL}_{new} \notin \text{Keys}(\text{Store.url\_index})$$
    """
    try:
        from database.store import DocumentStore
        store = DocumentStore()
        added = 0
        
        for page in crawled_pages:
            text = page.get("text", "")
            url = page.get("url", "")
            title = page.get("title", "Web Document")
            
            # Solo persistir páginas con contenido sustancial
            if len(text) < 300:
                continue
            
            # Limitar texto a 15,000 chars para no sobrecargar el índice
            text = text[:15000]
            
            # Extraer año de la URL o del texto si es posible
            year_match = re.search(r'(20\d{2}|19\d{2})', title + " " + url)
            year = year_match.group(1) if year_match else "N/A"
            
            # Construir documento v2 compatible
            doc = {
                "title": f"[Crawled] {title}",
                "year": year,
                "metadata": {
                    "director": "Web Crawler",
                    "cast": [],
                    "genres": ["Reference", "web_crawled"],
                    "budget": 0,
                    "revenue": 0,
                    "vote_average": 0.0,
                    "vote_count": 0,
                    "original_language": "en",
                    "imdb_id": "",
                    "tmdb_id": None,
                    "source_url": url,  # Deduplication key
                    "letterboxd_url": "",
                    "tagline": f"Crawled via web search for: {query[:80]}",
                },
                "rich_text": f"{title}. {text}",
                "reviews_count": 0,
            }
            
            doc_id = store.add_film(doc)
            added += 1
            logger.info(f"Crawler persistió página como doc_id={doc_id}: {title}")
        
        if added > 0:
            store.save()
            logger.info(f"Crawler enriqueció el corpus con {added} nuevos documentos web. "
                        f"Total corpus: {len(store.documents)} docs. "
                        f"(Los índices EBM/FAISS se actualizarán al reiniciar el servidor)")
        
        return added
    except Exception as e:
        logger.error(f"Error persistiendo páginas crawleadas: {e}")
        return 0



class WebSearchModule:
    """
    HEURISTIC INTELLIGENT WEB-SEARCH RETRIEVER & VECTOR FALLBACK MODULE
    ==================================================================
    Orchestrates the dynamic retrieval of external web resources to compensate for local corpus limits.
    Extracted pages are structured, deduplicated, and permanently indexed into the local storage.
    
    1. Retrieval Model:
       Hits the direct HTML version of DuckDuckGo via HTTP POST requests to prevent library rate limits.
       
    2. Parallel Crawler Pipeline:
       Crawls retrieved search pages concurrently, extracting structural sections, cleaning tags, 
       storing in DocumentStore, and indexating temporality via FAISS indexations.
    """

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    def _enrich_query(self, query: str) -> str:
        """
        QUERY CONTEXT EXPANSION HEURISTICS
        ==================================
        Expands the user query to steer the search engine toward academic and encyclopedic sources.
        
        Formula:
          Let $Q$ be the query.
          Let $K_{oscar} = \{\text{"oscar"}, \text{"academy"}, \text{"award"}, \text{"won"}, \text{"winner"}, \text{"best picture"}\}$
          Let $f_{enrich}(Q)$ be:
          $$f_{enrich}(Q) = \begin{cases} 
            Q \cup \{\text{"Academy Awards movie film wikipedia"}\} & \text{if } \exists w \in K_{oscar} \text{ s.t. } w \in \text{lowercase}(Q) \\
            Q \cup \{\text{"movie film"}\} & \text{otherwise}
          \end{cases}$$
        """
        q_lower = query.lower()
        # Si la query menciona Oscar/Academy/award, añadir contexto
        if any(kw in q_lower for kw in ["oscar", "academy", "award", "won", "winner", "best picture"]):
            return f"{query} Academy Awards movie film wikipedia"
        # Para consultas genéricas sobre cine
        return f"{query} movie film"

    # Dominios irrelevantes que DuckDuckGo suele devolver
    BLOCKED_DOMAINS = [
        "merriam-webster.com", "dictionary.com", "xe.com",
        "yelp.com", "tripadvisor.com", "urbandictionary.com",
    ]

    def _is_relevant_url(self, url: str) -> bool:
        """
        DOMAIN RELEVANCE FILTERING
        ==========================
        Performs static domain filtering against blacklist rules to prevent parsing non-informative sites.
        """
        url_lower = url.lower()
        return not any(domain in url_lower for domain in self.BLOCKED_DOMAINS)

    def search_and_format(self, query: str) -> List[Dict[str, Any]]:
        """
        Pipeline completo de búsqueda web con crawler persistente:
        1. Buscar en DuckDuckGo (con query enriquecida)
        2. Crawlear las páginas en paralelo (filtrando dominios basura)
        3. Persistir las páginas en el DocumentStore (enriquecimiento del corpus)
        4. Indexación temporal FAISS para respuesta inmediata
        """
        logger.info(f"Disparando búsqueda web fallback y crawling para: '{query}'")
        ddg_results = []
        
        # Enriquecer la query para obtener mejores resultados de DDG
        enriched_query = self._enrich_query(query)
        logger.info(f"Query enriquecida para DDG: '{enriched_query}'")
        
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
            url = "https://html.duckduckgo.com/html/"
            params = {"q": enriched_query}
            logger.info(f"Enviando solicitud POST a html.duckduckgo.com...")
            r = requests.post(url, data=params, headers=headers, timeout=10.0)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                result_divs = soup.find_all("div", class_="result")
                for div in result_divs[:self.max_results]:
                    title_el = div.find("a", class_="result__a")
                    snippet_el = div.find("a", class_="result__snippet")
                    if title_el:
                        href = title_el.get("href")
                        title = title_el.get_text().strip()
                        snippet = snippet_el.get_text().strip() if snippet_el else ""
                        ddg_results.append({
                            "title": title,
                            "href": href,
                            "body": snippet
                        })
                logger.info(f"Búsqueda directa DDG HTML obtuvo {len(ddg_results)} resultados.")
            else:
                logger.error(f"Error de status {r.status_code} al buscar en html.duckduckgo.com")
        except Exception as e:
            logger.error(f"Error en búsqueda directa DuckDuckGo HTML: {e}")
            
        if not ddg_results:
            logger.warning("DuckDuckGo no devolvió ningún resultado web.")
            return []

        # 1. Crawlear las páginas en paralelo (filtrando dominios basura)
        pages_to_crawl = []
        for r in ddg_results:
            url = r.get("href")
            title = r.get("title", "Resultado Web")
            if url and self._is_relevant_url(url):
                pages_to_crawl.append((url, title))
            elif url:
                logger.info(f"Filtrado dominio irrelevante: {url}")

        crawled_pages = []  # Páginas completas descargadas
        chunks_data = []    # Chunks para búsqueda vectorial
        max_workers = min(5, len(pages_to_crawl) or 1)
        
        logger.info(f"Iniciando descarga concurrente de {len(pages_to_crawl)} páginas...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(fetch_url, url, title) for url, title in pages_to_crawl]
            for future in futures:
                res = future.result()
                if res and res["text"]:
                    # Guardar la página completa para persistencia
                    crawled_pages.append(res)
                    # Dividir en chunks para búsqueda vectorial
                    chunks = chunk_text(res["text"])
                    for chunk in chunks:
                        if len(chunk) > 100:
                            chunks_data.append({
                                "text": chunk,
                                "url": res["url"],
                                "title": res["title"]
                            })

        # 2. PERSISTIR las páginas crawleadas en el corpus local
        #    (esto enriquece el DocumentStore para futuras consultas)
        if crawled_pages:
            _persist_crawled_pages(crawled_pages, query)

        # Fallback: si el crawl falló, usar snippets de DDG
        if not chunks_data:
            logger.info("Crawler no extrajo texto. Usando snippets de DuckDuckGo.")
            for r in ddg_results:
                body = r.get("body", "")
                if body:
                    chunks_data.append({
                        "text": body,
                        "url": r.get("href", ""),
                        "title": r.get("title", "Resultado Web")
                    })

        if not chunks_data:
            logger.warning("No hay datos textuales de la web para indexar.")
            return []

        # 3. Indexación temporal en FAISS para respuesta inmediata
        try:
            chunk_texts = [c["text"] for c in chunks_data]
            logger.info(f"Indexando temporalmente {len(chunk_texts)} chunks web en FAISS en memoria...")
            
            temp_v_store = VectorStore(data_dir=None, in_memory=True)
            temp_v_store.build_from_texts(chunk_texts)
            
            logger.info(f"Buscando '{query}' en el índice vectorial web...")
            search_results = temp_v_store.search(query, top_k=5)
            
            formatted_results = []
            for i, (chunk_idx, score) in enumerate(search_results):
                matching_chunk = chunks_data[chunk_idx]
                formatted_results.append({
                    "doc_id": 9000 + i,
                    "title": f"Web: {matching_chunk['title']}",
                    "year": "N/A",
                    "score": round(score, 4),
                    "ebm_score": 0.0,
                    "vector_score": round(score, 4),
                    "snippet": f"{generate_smart_snippet(matching_chunk['text'], query)} (Fuente: {matching_chunk['url']})",
                    "is_web_result": True
                })
                
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error en procesamiento vectorial temporal: {e}")
            formatted_results = []
            for i, r in enumerate(ddg_results[:5]):
                formatted_results.append({
                    "doc_id": 9000 + i,
                    "title": r.get("title", "Resultado Web"),
                    "year": "N/A",
                    "score": 0.5,
                    "ebm_score": 0.0,
                    "vector_score": 0.5,
                    "snippet": f"{r.get('body', '')} (Fuente: {r.get('href', '')})",
                    "is_web_result": True
                })
            return formatted_results

# Instancia global
web_searcher = WebSearchModule()
