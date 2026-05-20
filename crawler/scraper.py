"""
crawler/scraper.py
Módulo de Adquisición — Oscar Insight Search (SRI 2025-2026)

MetacriticReviewScraper: extrae User Reviews detalladas empleando curl_cffi
para evadir la protección Cloudflare / WAF mediante TLS Fingerprinting real (impersonate="chrome124").

Se pivota a Metacritic (User/Critic Reviews) porque Letterboxd contiene
excesivo ruido ("chistes internos") e IMDb/RT bloquean a nivel de DataDome
o usan Shadow DOM no-indexable que ralentiza el pipeline completo. Metacritic
ofrece reseñas largas y críticas reales, ideal para el NLP del Modelo Booleano Extendido.

Funcionalidad:
  1. Sesión única curl_cffi.requests.Session con TLS fingerprint de Chrome.
  2. Resolución heurística de slugs: /movie/{slug}/user-reviews/
  3. Extracción de al menos 10 críticas largas (>100 caracteres).
"""

from __future__ import annotations

import logging
import random
import re
import time
import unicodedata
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi.requests import Session

logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

BASE_URL    = "https://www.metacritic.com"
IMPERSONATE = "chrome124"   # TLS fingerprint

# Headers de Chrome real
CHROME_HEADERS = {
    "User-Agent":                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                                 "Chrome/124.0.0.0 Safari/537.36",
    "Accept":                    "text/html,application/xhtml+xml,application/xml;"
                                 "q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language":           "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}

DELAY_MIN   = 1.5
DELAY_MAX   = 3.5
TIMEOUT     = 25
MAX_RETRIES = 2

# Selectores que Metacritic suele emplear para reseñas de usuarios
REVIEW_CLASSES = ["review-card__quote", "c-siteReview_quote", "review_body", "c-siteReview"]


class MetacriticReviewScraper:
    """
    Extractor de reseñas ricas de Metacritic con TLS fingerprinting.
    Proporciona texto analítico rico para el índice invertido.
    """

    def __init__(self, warmup: bool = True) -> None:
        self._s = Session(impersonate=IMPERSONATE)
        self._s.headers.update(CHROME_HEADERS)

        if warmup:
            self._warmup()

    # ─── Sesión ───────────────────────────────────────────────────────────────

    def _sleep(self, extra: float = 0.0) -> None:
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX) + extra)

    def _warmup(self) -> None:
        logger.info("Iniciando sesión Metacritic (warmup)...")
        res = self._get(BASE_URL + "/movie/")
        if res:
            logger.info("  Warmup OK (Metacritic).")
        self._sleep()

    def _get(self, url: str, label: str = "") -> Optional[str]:
        for attempt in range(MAX_RETRIES + 1):
            if attempt > 0:
                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX) + (attempt * 2))
                
            try:
                resp = self._s.get(url, timeout=TIMEOUT)
                
                logger.debug("[%s] GET %s -> %d", label or "req", url, resp.status_code)
                
                if resp.status_code == 404:
                    return None
                    
                if resp.status_code == 200:
                    return resp.text
                    
            except Exception as exc:
                logger.warning("[%s] Error (intento %d): %s", label, attempt + 1, exc)
                
        return None

    # ─── Lógica de extracción ─────────────────────────────────────────────────

    @staticmethod
    def _slugify(text: str) -> str:
        """Convierte título en slug Metacritic (alfa numérico lowercase y guiones)."""
        nfkd = unicodedata.normalize("NFKD", text)
        ascii_ = nfkd.encode("ascii", "ignore").decode("ascii")
        # En Metacritic los caracteres especiales se remueven de forma similar a otros sitios
        slug = re.sub(r"[^a-z0-9\s-]", "", ascii_.lower())
        return re.sub(r"\s+", "-", slug.strip())

    def _parse_reviews(self, html: str, max_n: int) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        reviews = []
        
        # 1. Modern Metacritic: Look for div elements inside the reviews list that have Tailwind classes like break-words
        for tag in soup.find_all("div", class_=lambda c: c and "break-words" in c):
            text = tag.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            if 100 < len(text) < 3000 and "Expand" not in text and text not in reviews:
                if "metacritic" not in text.lower() and "sign in" not in text.lower():
                    reviews.append(text)
            if len(reviews) >= max_n:
                break

        # 2. Metacritic renders user reviews primarily in spans inside review structures
        if not reviews:
            for tag in soup.find_all("span"):
                text = tag.get_text(separator=" ", strip=True)
                text = re.sub(r"\s+", " ", text).strip()
                
                # Filtro de calidad para Metacritic: evitar meta tags y buscar texto rico real
                if 100 < len(text) < 3000 and "Expand" not in text and text not in reviews:
                    # Omitir textos de UI si lograron pasar la longitud
                    if "metacritic" not in text.lower() and "sign in" not in text.lower():
                        reviews.append(text)
                        
                if len(reviews) >= max_n:
                    break
                    
        # 3. Fallback si span no arroja resultados, buscar los divs de quotes
        if not reviews:
            for tag in soup.find_all("div", class_=lambda c: c and any(cls in c for cls in REVIEW_CLASSES)):
                text = tag.get_text(separator=" ", strip=True)
                if 100 < len(text) < 3000 and text not in reviews:
                    reviews.append(text)
                if len(reviews) >= max_n:
                    break

        return reviews[:max_n]

    # ─── API pública ──────────────────────────────────────────────────────────

    @staticmethod
    def _is_internal(url: str) -> bool:
        """Verifica si un URL absoluto pertenece al dominio metacritic.com."""
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            # Aceptamos metacritic.com o subdominios
            return "metacritic.com" in (parsed.netloc or "")
        except Exception:
            return False

    def _is_movie_match(self, url_path: str, link_text: str, target_title: str, target_year: Optional[int]) -> bool:
        """Determina heurísticamente si una ruta de URL corresponde a la película buscada."""
        target_slug = self._slugify(target_title)
        path_parts = [p for p in url_path.split('/') if p]
        if not path_parts or path_parts[0] != "movie":
            return False
        
        url_slug = path_parts[1] if len(path_parts) > 1 else ""
        if not url_slug:
            return False
            
        # Comparación exacta de slugs
        if url_slug == target_slug:
            return True
            
        # Substring matching (ej. "oppenheimer-2023" contiene "oppenheimer")
        if target_slug in url_slug or url_slug in target_slug:
            if target_year:
                # Comprobar si el año está presente en el slug de la URL o en el texto del enlace
                if str(target_year) in url_slug or str(target_year) in link_text:
                    return True
            return True
            
        return False

    def get_reviews(
        self,
        title: str,
        year: Optional[int] = None,
        imdb_id: Optional[str] = None,
        max_reviews: int = 10,
    ) -> list[str]:
        """
        Obtiene `max_reviews` críticas largas (User Reviews) de Metacritic
        usando un pipeline de Focused Crawling dinámico.
        """
        from urllib.parse import urljoin, urlparse
        
        slug = self._slugify(title)
        logger.info("――― Dynamic Crawler: '%s' (%s) -> query slug: %s", title, year or "?", slug)

        # ── PASO 1: Página semilla de búsqueda ─────────────────────────────────
        # Construimos la URL de búsqueda como punto de inicio (seed URL)
        seed_url = f"{BASE_URL}/search/{slug}/"
        logger.info("  [1] Seed URL de busqueda: %s", seed_url)
        
        html_search = self._get(seed_url, label=f"search:{slug}")
        movie_url = None
        
        if html_search:
            # ── PASO 2: Extracción y análisis de enlaces en página de búsqueda ────
            soup_search = BeautifulSoup(html_search, "lxml")
            links = soup_search.find_all("a", href=True)
            logger.info("  [2] Extraidos %d enlaces de la busqueda. Analizando...", len(links))
            
            for link in links:
                href = link["href"]
                # A: Resolución de URL usando la URL donde fue encontrada como referencia (Carlos's requirement)
                abs_url = urljoin(seed_url, href)
                parsed = urlparse(abs_url)
                
                # B: Análisis de dominio: ¿es interno o sale del dominio?
                is_internal = self._is_internal(abs_url)
                if not is_internal:
                    # C: Elección: elegir no salir de metacritic.com
                    continue
                    
                # D: Análisis de ruta/heurística de película
                link_text = link.get_text(strip=True)
                if self._is_movie_match(parsed.path, link_text, title, year):
                    movie_url = abs_url
                    logger.info("  -> Descubierto enlace de pelicula coincidente: %s (Texto: '%s')", movie_url, link_text)
                    break
        
        # Fallback de seguridad si el crawling de búsqueda no dio resultados o falló
        if not movie_url:
            fallback_slug = f"{slug}-{year}" if year else slug
            movie_url = f"{BASE_URL}/movie/{fallback_slug}/"
            logger.warning("  -> Fallback: no se descubrio el enlace por busqueda. Probando ruta directa: %s", movie_url)

        # ── PASO 3: Crawler viaja a la página de detalles y busca user reviews ─
        logger.info("  [3] Crawleando pagina de detalles: %s", movie_url)
        html_details = self._get(movie_url, label="details")
        user_reviews_url = None
        
        if html_details:
            soup_details = BeautifulSoup(html_details, "lxml")
            details_links = soup_details.find_all("a", href=True)
            
            for link in details_links:
                href = link["href"]
                abs_url = urljoin(movie_url, href)
                
                # Comprobación de dominio
                if not self._is_internal(abs_url):
                    continue
                    
                # Comprobación de ruta de user-reviews
                parsed = urlparse(abs_url)
                if "/user-reviews/" in parsed.path or parsed.path.endswith("/user-reviews"):
                    user_reviews_url = abs_url
                    logger.info("  -> Descubierto enlace de reseñas de usuario: %s", user_reviews_url)
                    break

        # Fallback de seguridad si no se descubrió el enlace en la página de detalles
        if not user_reviews_url:
            user_reviews_url = urljoin(movie_url, "user-reviews/")
            logger.warning("  -> Fallback: no se encontro enlace de reseñas en la pagina. Probando: %s", user_reviews_url)

        # ── PASO 4: Crawler viaja a la página de reseñas y extrae ─────────────
        logger.info("  [4] Crawleando pagina de reseñas de usuario: %s", user_reviews_url)
        html_reviews = self._get(user_reviews_url, label="reviews")
        
        if html_reviews:
            reviews = self._parse_reviews(html_reviews, max_reviews)
            if reviews:
                logger.info("  -> Total: %d reseñas ricas (Metacritic)", len(reviews))
                return reviews
                
        logger.warning("  -> Sin reseñas localizadas tras el proceso de crawling.")
        return []

# Compatibilidad con el pipeline de enriquecimiento actual
LetterboxdReviewScraper = MetacriticReviewScraper
LetterboxdScraper = MetacriticReviewScraper

if __name__ == "__main__":
    import sys, io
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    scraper = MetacriticReviewScraper()
    revs = scraper.get_reviews(title="Oppenheimer", year=2023, max_reviews=5)
    print("\nResultados:")
    for i, r in enumerate(revs, 1):
        print(f"[{i}] {r[:150]}...\n")
