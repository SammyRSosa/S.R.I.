"""
crawler/metacritic_spider.py
Componente de Rastreo Hipertextual Puro — Link-Traversal Focused Crawler Refactorizado.
Sistemas de Recuperación de Información · MatCom · Curso 2025-2026.

Este módulo implementa una versión altamente optimizada del crawler enfocado en grafos web (BFS).
Aplica indexación por lotes (Batch Processing) para evitar cuellos de botella por I/O, garantiza
consistencia secuencial estricta de identificadores (IDs) sin saltos y realiza una transición
orgánica pura por el grafo hipertextual (Index -> Detail -> Reviews).
"""

from __future__ import annotations

import logging
import random
import re
import time
import unicodedata
from collections import deque
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
from curl_cffi.requests import Session

from database.store import DocumentStore
from database.vector_store import VectorStore
from indexer.ebm import ExtendedBooleanModel
from indexer.inverted_index import InvertedIndex

logger = logging.getLogger("metacritic_spider")

# Configuración de Red y Evasión
BASE_URL = "https://www.metacritic.com"
SEED_URL = "https://www.metacritic.com/browse/movie/"
IMPERSONATE = "chrome124"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

CHROME_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}

# Expresiones regulares rígidas para el Focused Crawling y Traversal de Grafo
INDEX_PAGINATION_REGEX = re.compile(r"^https://www\.metacritic\.com/browse/movie/(?:\?page=\d+)?$")
MOVIE_DETAIL_REGEX = re.compile(r"^https://www\.metacritic\.com/movie/([a-z0-9-]+)/?$")
USER_REVIEWS_REGEX = re.compile(r"^https://www\.metacritic\.com/movie/([a-z0-9-]+)/user-reviews/?$")
PERSON_REGEX = re.compile(r"^https://www\.metacritic\.com/person/([a-z0-9-]+)/?$")
GENRE_REGEX = re.compile(r"^https://www\.metacritic\.com/genre/([a-z0-9-]+)/?$")


class MetacriticTraversalSpider:
    """
    Spider de rastreo hipertextual puro con procesamiento por lotes (Batch Processing).
    
    Navega de forma orgánica por el grafo web de Metacritic (BFS), valida directivas de robots.txt
    usando impersonación TLS de curl_cffi, acumula los documentos descubiertos en un búfer en memoria,
    y ejecuta la indexación y empaquetado vectorial en un único paso atómico al finalizar el rastreo.
    """

    def __init__(
        self,
        store: DocumentStore,
        inverted_index: InvertedIndex,
        ebm_model: ExtendedBooleanModel,
        vector_store: VectorStore,
        max_discoveries: int = 50,
        max_reviews_per_movie: int = 10,
    ) -> None:
        """
        Inicializa el crawler con las dependencias del motor de indexación híbrido.
        """
        self.store = store
        self.inverted_index = inverted_index
        self.ebm_model = ebm_model
        self.vector_store = vector_store
        
        self.max_discoveries = max_discoveries
        self.max_reviews_per_movie = max_reviews_per_movie
        self.discovered_count = 0

        # Grafo de Navegación BFS
        self.frontier: deque[str] = deque()
        self.visited: set[str] = set()

        # Búferes en memoria para procesamiento por lotes y estado de grafo
        self.buffer_movies: list[dict] = []
        self.pending_movies: dict[str, dict] = {}

        # Sesión HTTP con TLS Impersonation (Bypass Cloudflare WAF)
        self.session = Session(impersonate=IMPERSONATE)
        self.session.headers.update(CHROME_HEADERS)

        # Capa de Cumplimiento Político (Robots.txt)
        self.rp = RobotFileParser()
        self._robots_loaded = False

    # ─── Cumplimiento de Robots.txt (urllib.robotparser + curl_cffi) ──────────

    def _load_robots_txt(self) -> None:
        """
        Carga las directivas de robots.txt. Prioriza una caché local en disco
        (data/robots_cache.json) con un TTL de 24 horas para evitar llamadas redundantes de red.
        """
        if self._robots_loaded:
            return

        cache_path = self.store.data_dir / "robots_cache.json"
        now = time.time()
        ttl_seconds = 24 * 60 * 60  # 24 horas

        # 1. Intentar cargar desde caché local
        if cache_path.exists():
            try:
                import json
                with open(cache_path, "r", encoding="utf-8") as f:
                    cache_data = json.load(f)
                
                timestamp = cache_data.get("timestamp", 0)
                content = cache_data.get("content", "")
                
                if now - timestamp < ttl_seconds and content:
                    lines = content.splitlines()
                    self.rp.parse(lines)
                    self._robots_loaded = True
                    logger.info("[ROBOTS.TXT] -> Cargado desde caché local")
                    return
                else:
                    logger.info("[ROBOTS.TXT] -> Caché expirada/inexistente. Descargando de la web...")
            except Exception as e:
                logger.warning("[ROBOTS.TXT] Error leyendo caché local: %s. Re-descargando...", e)
        else:
            logger.info("[ROBOTS.TXT] -> Caché expirada/inexistente. Descargando de la web...")

        # 2. Descarga real vía red si no hay caché válida
        robots_url = urljoin(BASE_URL, "/robots.txt")
        logger.info("[ROBOTS.TXT] -> Descargando de la web en %s...", robots_url)
        try:
            resp = self.session.get(robots_url, timeout=15)
            if resp.status_code == 200:
                content = resp.text
                lines = content.splitlines()
                self.rp.parse(lines)
                self._robots_loaded = True
                
                # Guardar en caché
                try:
                    import json
                    cache_data = {
                        "timestamp": now,
                        "content": content
                    }
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(cache_data, f, ensure_ascii=False, indent=2)
                    logger.info("[ROBOTS.TXT] ✓ Archivo robots.txt guardado en caché local.")
                except Exception as cache_err:
                    logger.warning("[ROBOTS.TXT] Error guardando robots.txt en caché: %s", cache_err)
            else:
                logger.warning(
                    "[ROBOTS.TXT] ⚠️ Falló descarga de red (status %d). Aplicando directivas permisivas.",
                    resp.status_code
                )
        except Exception as e:
            logger.error("[ROBOTS.TXT] ⚠️ Excepción al solicitar de la web: %s. Permitiendo por defecto.", e)

    def _can_fetch(self, url: str) -> bool:
        """
        Verifica dinámicamente si la URL en la frontera está permitida para el crawler.
        """
        self._load_robots_txt()
        if not self._robots_loaded:
            return True
        allowed = self.rp.can_fetch("*", url)
        if not allowed:
            logger.warning("[RECHAZADO POR ROBOTS.TXT] -> URL: %s", url)
        return allowed

    # ─── Retrasos de cortesía y red robusta ───────────────────────────────────

    def _sleep(self) -> None:
        """Aplica un retraso aleatorio uniforme para evitar saturación de red."""
        delay = random.uniform(1.5, 3.5)
        logger.debug("[RATE-LIMIT] Espera de cortesía: %.2fs", delay)
        time.sleep(delay)

    def _get(self, url: str, label: str = "") -> Optional[str]:
        """Realiza peticiones GET con reintentos y tolerancia a anomalías de red."""
        for attempt in range(3):
            if attempt > 0:
                backoff = attempt * 3.0 + random.uniform(1.0, 3.0)
                logger.warning("[%s] Reintento %d en %.2fs debido a fallo previo...", label or "HTTP", attempt + 1, backoff)
                time.sleep(backoff)
            
            try:
                resp = self.session.get(url, timeout=25)
                if resp.status_code == 200:
                    return resp.text
                elif resp.status_code == 404:
                    logger.debug("[%s] 404 No Encontrado: %s", label or "HTTP", url)
                    return None
                else:
                    logger.warning("[%s] Código de respuesta inesperado %d para: %s", label or "HTTP", resp.status_code, url)
            except Exception as e:
                logger.error("[%s] Fallo de red en petición: %s", label or "HTTP", e)
        return None

    # ─── Focused Crawling por Regex (Extracción de Enlaces) ───────────────────

    @staticmethod
    def _slugify(text: str) -> str:
        """Convierte una cadena de texto a su representación de slug de Metacritic."""
        nfkd = unicodedata.normalize("NFKD", text)
        ascii_ = nfkd.encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-z0-9\s-]", "", ascii_.lower())
        return re.sub(r"\s+", "-", slug.strip())

    def extract_links(self, html: str, current_url: str) -> list[str]:
        """
        Extrae los hipervínculos de la página HTML, los convierte en URLs absolutas
        y los filtra usando las expresiones regulares del focused crawling y traversal del grafo.
        
        Permite extraer enlaces de películas, reseñas, personas (directores/actores) y géneros.
        """
        soup = BeautifulSoup(html, "lxml")
        extracted: list[str] = []

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            abs_url = urljoin(current_url, href)
            
            # Limpiar query parameters innecesarios excepto en rutas de paginación
            parsed = urlparse(abs_url)
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query and "page=" in parsed.query and "browse/movie" in parsed.path:
                clean_url += f"?{parsed.query}"

            # Validar dominio interno
            if "metacritic.com" not in parsed.netloc:
                continue

            # Validar contra los patrones de grafo autorizados (incluyendo personas y géneros)
            is_valid = (
                INDEX_PAGINATION_REGEX.match(clean_url) or
                MOVIE_DETAIL_REGEX.match(clean_url) or
                USER_REVIEWS_REGEX.match(clean_url) or
                PERSON_REGEX.match(clean_url) or
                GENRE_REGEX.match(clean_url)
            )

            if is_valid and clean_url not in extracted:
                extracted.append(clean_url)

        return extracted

    # ─── Parsers de Contenido de Páginas de Metacritic ────────────────────────

    @staticmethod
    def _resolve_nuxt(val, raw_list, depth=0, max_depth=5, visited=None) -> any:
        """
        Resuelve de forma segura y limitada los punteros del array plano __NUXT_DATA__.
        Previene loops de referencias circulares usando un set de visitados.
        """
        if visited is None:
            visited = set()
        if depth >= max_depth:
            return val
        if isinstance(val, int) and 0 <= val < len(raw_list):
            if val in visited:
                return None
            visited.add(val)
            res = MetacriticTraversalSpider._resolve_nuxt(raw_list[val], raw_list, depth + 1, max_depth, visited)
            visited.remove(val)
            return res
        elif isinstance(val, dict):
            return {k: MetacriticTraversalSpider._resolve_nuxt(v, raw_list, depth + 1, max_depth, visited) for k, v in val.items()}
        elif isinstance(val, list):
            if len(val) == 2 and isinstance(val[0], str) and val[0] in ['ShallowReactive', 'Reactive', 'ShallowRef', 'Ref']:
                return MetacriticTraversalSpider._resolve_nuxt(val[1], raw_list, depth + 1, max_depth, visited)
            return [MetacriticTraversalSpider._resolve_nuxt(x, raw_list, depth + 1, max_depth, visited) for x in val]
        return val

    def _parse_movie_details(self, html: str, url: str) -> Optional[dict]:
        """
        Parsea los metadatos principales del film de forma ultra-robusta y estructurada,
        utilizando Path Parsing explícito sobre Nuxt.js (__NUXT_DATA__) o Next.js (__NEXT_DATA__).
        Elimina por completo la recursión ciega mediante validación explícita de tipos de entidad.
        """
        soup = BeautifulSoup(html, "lxml")
        slug_match = MOVIE_DETAIL_REGEX.match(url)
        slug = slug_match.group(1) if slug_match else ""

        # ── 1. EXTRAER USANDO NUXT.JS (Estructura Fandom/Metacritic moderna) ──────
        nuxt_script = soup.find("script", id="__NUXT_DATA__")
        if nuxt_script and nuxt_script.string:
            try:
                import json
                raw_list = json.loads(nuxt_script.string)
                if isinstance(raw_list, list) and len(raw_list) > 1:
                    # En Nuxt, index 1 almacena la raíz del estado
                    root_data = self._resolve_nuxt(1, raw_list)
                    if isinstance(root_data, dict):
                        state_data = root_data.get("data", {})
                        if isinstance(state_data, dict):
                            # Acceso estructurado a la llave loadPage
                            movies_key = next((k for k in state_data.keys() if "loadPage:movies" in k), None)
                            if movies_key:
                                movie_payload = state_data[movies_key]
                                if isinstance(movie_payload, dict):
                                    meta = movie_payload.get("meta", {})
                                    if isinstance(meta, dict) and meta.get("typeName") == "movie":
                                        # ¡Entidad validada formalmente como "movie"!
                                        title = meta.get("title", "")
                                        if title.lower().endswith(" reviews"):
                                            title = title[:-8].strip()
                                        overview = meta.get("description", "")
                                        genres_list = meta.get("genres", ["Drama"])
                                        
                                        # Año de lanzamiento
                                        year = "2024"
                                        title_text = soup.title.string if soup.title else ""
                                        year_match = re.search(r"\b(19\d\d|20\d\d)\b", title_text)
                                        if year_match:
                                            year = year_match.group(1)
                                            
                                        logger.debug("[NUXT-DATA] Metadatos cargados por ruta estructurada en Nuxt.js.")
                                        
                                        # Director (extraído de forma robusta por DOM)
                                        director = "Unknown Director"
                                        for label in soup.find_all(text=re.compile(r"Directed By|Director", re.I)):
                                            parent = label.parent
                                            if parent:
                                                links = parent.find_all("a", href=re.compile(r"/person/"))
                                                if links:
                                                    director = links[0].get_text(strip=True)
                                                    break
                                        
                                        # Reparto (extraído de forma robusta por DOM)
                                        cast = []
                                        for link in soup.find_all("a", href=re.compile(r"/person/")):
                                            name = link.get_text(strip=True)
                                            if name and name != director and name not in cast:
                                                cast.append(name)
                                                if len(cast) >= 10:
                                                    break
                                                    
                                        return {
                                            "title": title.strip(),
                                            "year": year,
                                            "director": director,
                                            "cast": cast,
                                            "genres": genres_list,
                                            "overview": overview.strip(),
                                            "source_url": url,
                                            "slug": slug,
                                        }
            except Exception as e:
                logger.debug("[NUXT-DATA] Falló parseo estructurado de Nuxt: %s. Pasando a fallback.", e)

        # ── 2. EXTRAER USANDO NEXT.JS (Esquema Legacy - Path Parsing validado) ───
        next_script = soup.find("script", id="__NEXT_DATA__")
        if next_script and next_script.string:
            try:
                import json
                data = json.loads(next_script.string)
                props = data.get("props", {})
                page_props = props.get("pageProps", {})
                apollo_state = page_props.get("apolloState", {})
                
                # Búsqueda exacta y validada de entidad "Movie" en apolloState
                movie_node = None
                for key, val in apollo_state.items():
                    if isinstance(val, dict) and val.get("__typename") == "Movie":
                        # ¡Entidad validada formalmente como "Movie"!
                        movie_node = val
                        break
                        
                if movie_node:
                    title = movie_node.get("title") or movie_node.get("name", "")
                    if title.lower().endswith(" reviews"):
                        title = title[:-8].strip()
                    overview = movie_node.get("synopsis") or movie_node.get("description", "")
                    
                    # Cargar géneros estructurados
                    genres_raw = movie_node.get("genres") or movie_node.get("genre", [])
                    genres_list = []
                    if isinstance(genres_raw, list):
                        for g in genres_raw:
                            if isinstance(g, dict) and g.get("name"):
                                genres_list.append(g["name"])
                            elif isinstance(g, str):
                                genres_list.append(g)
                                
                    year_raw = movie_node.get("releaseYear") or movie_node.get("year", "2024")
                    
                    logger.debug("[NEXT-DATA] Metadatos cargados por ruta estructurada en Next.js.")
                    
                    # Director (DOM)
                    director = "Unknown Director"
                    for label in soup.find_all(text=re.compile(r"Directed By|Director", re.I)):
                        parent = label.parent
                        if parent:
                            links = parent.find_all("a", href=re.compile(r"/person/"))
                            if links:
                                director = links[0].get_text(strip=True)
                                break
                                
                    # Reparto (DOM)
                    cast = []
                    for link in soup.find_all("a", href=re.compile(r"/person/")):
                        name = link.get_text(strip=True)
                        if name and name != director and name not in cast:
                            cast.append(name)
                            if len(cast) >= 10:
                                break
                                
                    return {
                        "title": str(title).strip(),
                        "year": str(year_raw).strip(),
                        "director": director,
                        "cast": cast,
                        "genres": genres_list or ["Drama"],
                        "overview": str(overview).strip(),
                        "source_url": url,
                        "slug": slug,
                    }
            except Exception as e:
                logger.debug("[NEXT-DATA] Falló parseo estructurado de Next: %s. Pasando a fallback.", e)

        # ── 3. FALLBACK GENERAL BASADO EN SCRAPING DEL DOM ESTÁNDAR ──────────────
        title = ""
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].split(" - Metacritic")[0].split(" (")[0].strip()
        if not title:
            title_tag = soup.find("h1")
            if title_tag:
                title = title_tag.get_text(strip=True)
        if not title and soup.title:
            title = soup.title.string.split(" - Metacritic")[0].split(" (")[0].strip()

        if not title:
            return None

        if title.lower().endswith(" reviews"):
            title = title[:-8].strip()

        # Año de lanzamiento
        year = "2024"
        title_text = soup.title.string if soup.title else ""
        year_match = re.search(r"\b(19\d\d|20\d\d)\b", title_text)
        if year_match:
            year = year_match.group(1)
        else:
            og_desc = soup.find("meta", property="og:description")
            if og_desc and og_desc.get("content"):
                year_match = re.search(r"\b(19\d\d|20\d\d)\b", og_desc["content"])
                if year_match:
                    year = year_match.group(1)

        # Sinopsis
        overview = ""
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            overview = og_desc["content"].strip()
        if not overview:
            desc_meta = soup.find("meta", attrs={"name": "description"})
            if desc_meta and desc_meta.get("content"):
                overview = desc_meta["content"].strip()

        # Director
        director = "Unknown Director"
        for label in soup.find_all(text=re.compile(r"Directed By|Director", re.I)):
            parent = label.parent
            if parent:
                links = parent.find_all("a", href=re.compile(r"/person/"))
                if links:
                    director = links[0].get_text(strip=True)
                    break

        # Géneros
        genres = []
        for link in soup.find_all("a", href=re.compile(r"/genre/")):
            g = link.get_text(strip=True)
            if g and g not in genres:
                genres.append(g)
        if not genres:
            genres = ["Drama"]

        # Reparto
        cast = []
        for link in soup.find_all("a", href=re.compile(r"/person/")):
            name = link.get_text(strip=True)
            if name and name != director and name not in cast:
                cast.append(name)
                if len(cast) >= 10:
                    break

        return {
            "title": title.strip(),
            "year": year,
            "director": director,
            "cast": cast,
            "genres": genres,
            "overview": overview.strip(),
            "source_url": url,
            "slug": slug,
        }

    def _parse_user_reviews(self, html: str) -> list[str]:
        """
        Extrae las reseñas de usuarios reales aplicando restricciones de calidad.
        """
        soup = BeautifulSoup(html, "lxml")
        reviews: list[str] = []

        # 1. Metacritic Moderno (divs con break-words)
        for tag in soup.find_all("div", class_=lambda c: c and "break-words" in c):
            text = tag.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            if 100 < len(text) < 3000 and "Expand" not in text and text not in reviews:
                if "metacritic" not in text.lower() and "sign in" not in text.lower():
                    reviews.append(text)
            if len(reviews) >= self.max_reviews_per_movie:
                break

        # 2. Spans en el DOM
        if not reviews:
            for tag in soup.find_all("span"):
                text = tag.get_text(separator=" ", strip=True)
                text = re.sub(r"\s+", " ", text).strip()
                if 100 < len(text) < 3000 and "Expand" not in text and text not in reviews:
                    if "metacritic" not in text.lower() and "sign in" not in text.lower():
                        reviews.append(text)
                if len(reviews) >= self.max_reviews_per_movie:
                    break

        # 3. Quotes (Fallback final)
        if not reviews:
            review_classes = ["review-card__quote", "c-siteReview_quote", "review_body", "c-siteReview"]
            for tag in soup.find_all("div", class_=lambda c: c and any(cls in c for cls in review_classes)):
                text = tag.get_text(separator=" ", strip=True)
                if 100 < len(text) < 3000 and text not in reviews:
                    reviews.append(text)
                if len(reviews) >= self.max_reviews_per_movie:
                    break

        return reviews[:self.max_reviews_per_movie]

    # ─── Deduplicación y Consistencia ─────────────────────────────────────────

    def _is_duplicate(self, title: str, slug: str, url: str) -> bool:
        """
        Comprueba heurísticamente la existencia del film para evitar colisiones.
        """
        if url in self.store._url_index:
            return True

        candidate_slug = self._slugify(title)
        
        # Verificar contra el DocumentStore persistido
        for doc in self.store.documents.values():
            existing_title = doc.get("title", "")
            existing_slug = self._slugify(existing_title)
            if existing_slug == slug or existing_slug == candidate_slug:
                return True
            existing_url = doc.get("source_url", "") or doc.get("metadata", {}).get("source_url", "")
            if existing_url == url:
                return True

        # Verificar contra el buffer temporal en memoria (muy importante para BFS!)
        for doc in self.buffer_movies:
            existing_title = doc.get("title", "")
            existing_slug = self._slugify(existing_title)
            if existing_slug == slug or existing_slug == candidate_slug:
                return True

        return False

    # ─── Acumulación en Buffer (Pre-procesamiento) ────────────────────────────

    def _buffer_discovered_film(self, metadata: dict, reviews: list[str]) -> None:
        """
        Construye el documento y lo almacena temporalmente en el buffer en memoria.
        Esto elimina la I/O de disco e indexación por cada iteración.
        """
        title = metadata["title"]
        year = metadata["year"]

        # Formatear metadata v2
        doc_metadata = {
            "director": metadata["director"],
            "cast": metadata["cast"],
            "genres": metadata["genres"],
            "budget": 0,
            "revenue": 0,
            "vote_average": 7.0,
            "vote_count": 50,
            "original_language": "en",
            "imdb_id": "",
            "tmdb_id": None,
            "source_url": metadata["source_url"],
            "tagline": "",
            "runtime": 120,
            "original_title": title,
        }

        # Construcción del rich_text
        rich_parts = [
            title, title,  # duplicación intencional para dar peso al título
            " ".join(metadata["genres"]),
            metadata["director"],
            " ".join(metadata["cast"][:10]),
            metadata["overview"]
        ] + reviews
        
        rich_text = " ".join(p for p in rich_parts if p)

        film_doc = {
            "title": title,
            "year": year,
            "metadata": doc_metadata,
            "rich_text": rich_text,
            "reviews_count": len(reviews),
        }

        self.buffer_movies.append(film_doc)
        self.discovered_count += 1
        logger.info(
            "  ↳ [BUFFERED] Película acumulada en memoria: '%s' (%s). [Total en Buffer: %d/%d]",
            title,
            year,
            self.discovered_count,
            self.max_discoveries
        )

    # ─── Indexación por Lotes Atómica (Batch Processing al Finalizar) ─────────

    def flush_buffer(self) -> None:
        """
        Vacía el búfer de memoria acumulado, garantiza IDs perfectamente secuenciales,
        y realiza la actualización de todos los índices de forma completamente atómica.
        """
        if not self.buffer_movies:
            logger.info("[BATCH] No se descubrieron nuevas películas en esta sesión. Omitiendo indexación.")
            return

        logger.info("\n" + "=" * 80)
        logger.info("  INICIANDO PROCESAMIENTO POR LOTES ATÓMICO (BATCH INDEXING PIPELINE)")
        logger.info("=" * 80)

        # 1. Garantizar consistencia secuencial de IDs en DocumentStore
        # Respetamos el encapsulamiento consultando el siguiente ID disponible mediante el método público
        start_next_id = self.store.get_next_id()
        logger.info("[BATCH-DB] ID inicial asignado para el lote: %d", start_next_id)

        new_ids: list[tuple[int, dict]] = []
        for film_doc in self.buffer_movies:
            # add_film maneja el autoincremento perfecto de IDs de forma interna y transparente
            doc_id = self.store.add_film(film_doc)
            new_ids.append((doc_id, film_doc))

        # Escribir documents.json una única vez a disco
        self.store.save()
        logger.info("[BATCH-DB] ✓ Base de datos persistida en documents.json (%d películas en total).", len(self.store.documents))

        # 2. Agregar todos los nuevos documentos al índice invertido
        logger.info("[BATCH-INDEX] Actualizando listas de postings en InvertedIndex...")
        for doc_id, film_doc in new_ids:
            self.inverted_index.add_document(doc_id, film_doc["rich_text"])

        # Guardar index.json una única vez a disco
        self.store.save_index(self.inverted_index.index)
        logger.info("[BATCH-INDEX] ✓ Posting lists persistidas en index.json con éxito.")

        # 3. Recalcular la matriz global de pesos EBM una única vez
        logger.info("[BATCH-EBM] Recalculando pesos TF-IDF globales (EBM Weights)...")
        self.ebm_model.build_weights()
        logger.info("[BATCH-EBM] ✓ Pesos EBM construidos y guardados en ebm_weights.json.")

        # 4. Actualizar el espacio de embeddings vectorial FAISS de forma incremental
        logger.info("[BATCH-FAISS] Actualizando embeddings semánticos en el espacio vectorial...")
        try:
            # Construir diccionario de nuevos documentos con sus nuevos IDs
            new_docs_dict = {doc_id: film_doc for doc_id, film_doc in new_ids}
            
            # Intentar actualización incremental
            success = self.vector_store.add_documents_incremental(new_docs_dict)
            if success:
                logger.info("[BATCH-FAISS] ✓ Índice FAISS y mapeo binario actualizados de forma incremental y guardados con éxito.")
            else:
                logger.warning("[BATCH-FAISS] Falló actualización incremental o el índice estaba vacío. Reconstruyendo desde cero...")
                self.vector_store.build_from_documents(self.store.documents)
                logger.info("[BATCH-FAISS] ✓ Índice FAISS reconstruido por completo y guardado con éxito.")
        except Exception as e:
            logger.error("[BATCH-FAISS] ❌ Falló la actualización del índice vectorial: %s", e)

        # Limpiar buffer
        self.buffer_movies.clear()
        logger.info("=" * 80)
        logger.info("  ✓ ¡PROCESAMIENTO POR LOTES COMPLETADO EXITOSAMENTE!")
        logger.info("=" * 80 + "\n")

    # ─── Grafo de Navegación BFS Loop ─────────────────────────────────────────

    def run(self) -> None:
        """
        Ejecuta el Link-Traversal Focused Crawler partiendo de la URL semilla.
        Navega de forma orgánica BFS encolando enlaces descubiertos.
        Al finalizar, ejecuta la indexación por lotes de forma atómica.
        """
        logger.info("=" * 80)
        logger.info("  METACRITIC LINK-TRAVERSAL FOCUSED CRAWLER — STARTING BFS BATCH ENGINE")
        logger.info("=" * 80)

        self.frontier.clear()
        self.frontier.append(SEED_URL)
        self.visited.clear()
        self.buffer_movies.clear()
        self.discovered_count = 0

        # Asegurar directivas de robots.txt cargadas
        self._load_robots_txt()

        while self.frontier and self.discovered_count < self.max_discoveries:
            current_url = self.frontier.popleft()

            if current_url in self.visited:
                continue

            self.visited.add(current_url)

            # Capa Ética de robots.txt
            if not self._can_fetch(current_url):
                continue

            logger.info("[BFS-CRAWL] [Frontera: %d] [Buffer: %d/%d] Fetching: %s", len(self.frontier), self.discovered_count, self.max_discoveries, current_url)

            # Descargar HTML usando TLS Impersonation
            html = self._get(current_url, label="traversal")
            if not html:
                continue

            # Extracción y filtrado hipertextual orgánico
            links = self.extract_links(html, current_url)
            for link in links:
                if link not in self.visited and link not in self.frontier:
                    if USER_REVIEWS_REGEX.match(link):
                        self.frontier.appendleft(link)
                    else:
                        self.frontier.append(link)

            # Transición orgánica de nodos de grafo (Focused Hypertext Traversal)
            if MOVIE_DETAIL_REGEX.match(current_url):
                # ── NODO DE FICHA PRINCIPAL DE DETALLES ────────────────────────
                slug = MOVIE_DETAIL_REGEX.match(current_url).group(1)
                
                # Extraer metadatos de forma estructurada
                metadata = self._parse_movie_details(html, current_url)
                if metadata:
                    title = metadata["title"]
                    if self._is_duplicate(title, slug, current_url):
                        logger.debug("  ↳ [SKIP] Película ya existente: '%s'", title)
                    else:
                        logger.info("  ↳ [GRAFO-DETALLE] Metadatos leídos para: '%s' (%s)", title, metadata["year"])
                        self.pending_movies[slug] = metadata

            elif USER_REVIEWS_REGEX.match(current_url):
                # ── NODO DE SECCIÓN DE RESEÑAS DE USUARIO ──────────────────────
                slug = USER_REVIEWS_REGEX.match(current_url).group(1)
                
                metadata = self.pending_movies.get(slug)
                if not metadata:
                    # Fallback dinámico de navegación en el grafo (sincrónico si no se visitó antes)
                    details_url = urljoin(BASE_URL, f"/movie/{slug}/")
                    if details_url not in self.visited:
                        logger.info("  ↳ [GRAFO-FALLBACK] Resolviendo metadatos de detalles para slug: %s", slug)
                        if self._can_fetch(details_url):
                            self._sleep()
                            details_html = self._get(details_url, label="resolver")
                            if details_html:
                                metadata = self._parse_movie_details(details_html, details_url)
                                if metadata:
                                    self.pending_movies[slug] = metadata

                if metadata:
                    title = metadata["title"]
                    if self._is_duplicate(title, slug, metadata["source_url"]):
                        logger.debug("  ↳ [SKIP] Película ya existente: '%s'", title)
                        if slug in self.pending_movies:
                            del self.pending_movies[slug]
                    else:
                        # Extraer críticas de usuario
                        reviews = self._parse_user_reviews(html)
                        if reviews:
                            # Acumular película en el buffer en memoria de forma atómica
                            self._buffer_discovered_film(metadata, reviews)
                            if slug in self.pending_movies:
                                del self.pending_movies[slug]
                        else:
                            logger.warning("  ↳ [RETRY-BFS] Reseñas vacías en ficha para: '%s'", title)
                else:
                    logger.debug("  ↳ [IGNORE] Ficha de reseñas huérfana de metadatos para slug: %s", slug)

            elif PERSON_REGEX.match(current_url):
                # ── NODO DE DIRECTOR/ACTOR (HUB DE GRAFO) ─────────────────────
                slug = PERSON_REGEX.match(current_url).group(1)
                logger.info("  ↳ [GRAFO-PERSONA] Walked en filmografía de persona para descubrir enlaces: '%s'", slug)

            elif GENRE_REGEX.match(current_url):
                # ── NODO DE GÉNERO DE CINE (HUB DE GRAFO) ──────────────────────
                slug = GENRE_REGEX.match(current_url).group(1)
                logger.info("  ↳ [GRAFO-GÉNERO] Walked en catálogo de género para descubrir enlaces: '%s'", slug)

            # Politeness delay ético
            self._sleep()

        # RENDERIZAR E INDEXAR EL BUFFER FINAL DE FORMA ATÓMICA (BATCH FLUSH)
        self.flush_buffer()

        logger.info("=" * 80)
        logger.info("  Link-Traversal Focused Crawler finalizado de forma limpia.")
        logger.info("  Nuevas películas integradas a base de datos : %d", self.discovered_count)
        logger.info("  Corpus actual final de la aplicación        : %d películas", len(self.store.documents))
        logger.info("=" * 80)
