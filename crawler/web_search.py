"""
crawler/web_search.py
Módulo de Búsqueda Web Fallback y Crawler Vectorial en tiempo real (Corte 2).

Realiza una búsqueda web a través de DuckDuckGo si los resultados locales fallan,
descarga las páginas de forma concurrente, extrae y limpia el texto usando BeautifulSoup,
realiza chunking de la información y construye un VectorStore temporal de FAISS en memoria
para realizar búsqueda semántica en tiempo real sobre los contenidos web.
"""

import logging
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from database.vector_store import VectorStore

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def extract_text_from_html(html_content: str) -> str:
    """Extrae y limpia el texto principal de una página HTML filtrando ruido."""
    soup = BeautifulSoup(html_content, "html.parser")
    # Eliminar elementos no textuales o de maquetación/UI
    for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]):
        element.extract()
    text = soup.get_text(separator=" ")
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    return " ".join(chunk for chunk in chunks if chunk)

def chunk_text(text: str, chunk_size: int = 600, overlap: int = 120) -> List[str]:
    """Divide un texto plano en chunks con solapamiento."""
    chunks = []
    if not text:
        return chunks
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end].strip())
        start += chunk_size - overlap
    return chunks

def fetch_url(url: str, title: str) -> Optional[Dict[str, Any]]:
    """Descarga una URL y devuelve su contenido limpio."""
    try:
        logger.info(f"Crawler descargando página: {url}")
        r = requests.get(url, headers=HEADERS, timeout=4.0)
        if r.status_code == 200:
            text = extract_text_from_html(r.text)
            return {"text": text, "url": url, "title": title}
        else:
            logger.warning(f"Error {r.status_code} al descargar {url}")
    except Exception as e:
        logger.warning(f"Error en crawler al descargar {url}: {e}")
    return None

class WebSearchModule:
    """
    Módulo de búsqueda web inteligente con crawler vectorial temporal.
    """

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    def search_and_format(self, query: str) -> List[Dict[str, Any]]:
        """
        Realiza búsqueda web en DuckDuckGo, descarga el contenido de las páginas,
        las divide en chunks, inicializa un índice FAISS temporal en memoria,
        y devuelve los 5 snippets más relevantes vectorialmente.
        """
        logger.info(f"Disparando búsqueda web fallback y crawling vectorial para: '{query}'")
        ddg_results = []
        
        try:
            with DDGS() as ddgs:
                search_query = query
                # Forzar a lista para materializar la búsqueda inmediatamente
                ddg_results = list(ddgs.text(search_query, max_results=self.max_results))
        except Exception as e:
            logger.error(f"Error en búsqueda web DuckDuckGo: {e}")
            
        if not ddg_results:
            logger.warning("DuckDuckGo no devolvió ningún resultado web.")
            return []

        # 1. Crawlear las páginas en paralelo
        pages_to_crawl = []
        for r in ddg_results:
            url = r.get("href")
            title = r.get("title", "Resultado Web")
            if url:
                pages_to_crawl.append((url, title))

        chunks_data = []
        # Limitar número de hilos según URLs a descargar
        max_workers = min(5, len(pages_to_crawl) or 1)
        
        logger.info(f"Iniciando descarga concurrente de {len(pages_to_crawl)} páginas con {max_workers} trabajadores...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(fetch_url, url, title) for url, title in pages_to_crawl]
            for future in futures:
                res = future.result()
                if res and res["text"]:
                    chunks = chunk_text(res["text"])
                    for chunk in chunks:
                        if len(chunk) > 100:  # Evitar chunks vacíos o demasiado pequeños
                            chunks_data.append({
                                "text": chunk,
                                "url": res["url"],
                                "title": res["title"]
                            })

        # Fallback: si el crawl falló por completo o no dio chunks de calidad,
        # usamos el snippet plano devuelto directamente por DuckDuckGo
        if not chunks_data:
            logger.info("El crawler no pudo extraer texto de las URLs. Usando snippets de DuckDuckGo como fallback.")
            for r in ddg_results:
                body = r.get("body", "")
                if body:
                    chunks_data.append({
                        "text": body,
                        "url": r.get("href", ""),
                        "title": r.get("title", "Resultado Web")
                    })

        if not chunks_data:
            logger.warning("No hay datos textuales de la web para indexar temporalmente.")
            return []

        # 2. Indexación temporal en FAISS (en caliente/en memoria)
        try:
            chunk_texts = [c["text"] for c in chunks_data]
            logger.info(f"Indexando temporalmente {len(chunk_texts)} chunks web en FAISS en memoria...")
            
            # Inicializar VectorStore limpio en memoria
            temp_v_store = VectorStore(data_dir=None, in_memory=True)
            temp_v_store.build_from_texts(chunk_texts)
            
            # 3. Búsqueda vectorial semántica sobre los chunks en memoria
            logger.info(f"Buscando '{query}' en el índice vectorial web...")
            # Retorna (chunk_idx, similitud_coseno)
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
                    "snippet": f"{matching_chunk['text']}... (Fuente: {matching_chunk['url']})",
                    "is_web_result": True
                })
                
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error en el procesamiento vectorial temporal de la web: {e}")
            # Fallback seguro: devolver los primeros resultados en formato plano compatible
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
