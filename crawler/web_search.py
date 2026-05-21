"""
crawler/web_search.py
Módulo de Búsqueda Web Fallback con Crawler Persistente (Corte 3).

Pipeline:
  1. Busca en DuckDuckGo las URLs más relevantes para la consulta.
  2. Descarga las páginas en paralelo y extrae texto limpio.
  3. PERSISTE las páginas crawleadas en el DocumentStore local
     para enriquecer el corpus de forma orgánica ("Crawler Heurístico").
  4. Construye un VectorStore temporal de FAISS en memoria para
     realizar búsqueda semántica inmediata sobre el contenido descargado.

Así, cada búsqueda web ENRIQUECE permanentemente el corpus local.
La próxima vez que alguien pregunte algo similar, la respuesta ya
estará indexada localmente sin depender de internet.
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
    """Extrae y limpia el texto principal de una página HTML filtrando ruido."""
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


def generate_smart_snippet(text: str, query: str) -> str:
    """Genera un fragmento de texto centrado en las palabras clave de la consulta."""
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


def fetch_url(url: str, title: str) -> Optional[Dict[str, Any]]:
    """Descarga una URL y devuelve su contenido limpio."""
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
    Persiste las páginas crawleadas en el DocumentStore local.
    Solo guarda páginas con texto sustancial (>300 chars).
    Usa source_url para deduplicación: si la URL ya fue crawleada antes, no se duplica.
    
    Returns:
        Número de documentos nuevos añadidos al corpus.
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
    Módulo de búsqueda web inteligente con crawler vectorial temporal
    y persistencia automática al DocumentStore local.
    
    Cada búsqueda web enriquece permanentemente el corpus:
    las páginas descargadas se guardan en el DocumentStore para que
    futuras consultas similares se resuelvan localmente sin internet.
    """

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    def _enrich_query(self, query: str) -> str:
        """
        Enriquece la query para mejorar resultados de DuckDuckGo.
        Añade contexto cinematográfico si detecta keywords relevantes.
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
        """Filtra URLs de dominios claramente irrelevantes."""
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
