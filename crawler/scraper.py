"""
crawler/scraper.py
Módulo de Adquisición — Oscar Insight Search (SRI 2025-2026)

LetterboxdReviewScraper: extrae exclusivamente el texto de las reseñas de
usuarios de Letterboxd dado un título + año de película.

Estrategia de localización del slug:
  1. Construye candidatos de slug a partir del título (slugify) con y sin año.
  2. Para cada candidato intenta GET /film/{slug}/reviews/ — si 200 OK, usa ese.
  3. Fallback: intenta el redirect de IMDb → /imdb/{imdb_id}/ para obtener el slug.

Respeta robots.txt de Letterboxd. Usa cloudscraper si está disponible para
evadir desafíos Cloudflare (JS challenge), con fallback a requests + headers.

Uso:
    scraper = LetterboxdReviewScraper()
    reviews = scraper.get_reviews("Oppenheimer", year=2023, max_reviews=15)
    # ["A masterpiece of epic cinema...", ...]
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
from typing import Optional
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
import requests

# Intentar cloudscraper (bypass de Cloudflare JS challenge)
try:
    import cloudscraper as _cloudscraper
    _HAS_CLOUDSCRAPER = True
except ImportError:
    _HAS_CLOUDSCRAPER = False

logger = logging.getLogger(__name__)

# ─── Constantes ───────────────────────────────────────────────────────────────

LETTERBOXD_BASE   = "https://letterboxd.com"
ROBOTS_TXT_URL    = "https://letterboxd.com/robots.txt"
ROBOTS_USER_AGENT = "OscarInsightBot/0.2 (+https://github.com/sri-2025/oscar-insight)"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://letterboxd.com/",
    "DNT":             "1",
    "Connection":      "keep-alive",
}

REQUEST_DELAY   = 1.5    # segundos entre peticiones (educado con el servidor)
REQUEST_TIMEOUT = 15


class LetterboxdReviewScraper:
    """
    Extractor de reseñas de Letterboxd.

    Dado un título + año (y opcionalmente un IMDb ID), localiza la página de
    reseñas de la película y devuelve hasta ``max_reviews`` textos de crítica.

    Args:
        respect_robots: Si True (default), respeta robots.txt de Letterboxd.

    Example::

        scraper = LetterboxdReviewScraper()
        reviews = scraper.get_reviews("Oppenheimer", year=2023, max_reviews=15)
    """

    def __init__(self, respect_robots: bool = True) -> None:
        self.respect_robots = respect_robots
        self._session = self._build_session()

        # Cache del robot parser para no volver a descargarlo
        self._robot_parser: Optional[RobotFileParser] = None
        if respect_robots:
            self._load_robots()

    # ─── Sesión HTTP ──────────────────────────────────────────────────────────

    @staticmethod
    def _build_session() -> requests.Session:
        """Crea sesión con cloudscraper si disponible, o requests + headers."""
        if _HAS_CLOUDSCRAPER:
            logger.debug("Usando cloudscraper para bypass Cloudflare.")
            sess = _cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "desktop": True}
            )
        else:
            logger.debug("cloudscraper no disponible — usando requests con browser headers.")
            sess = requests.Session()
        sess.headers.update(BROWSER_HEADERS)
        return sess

    # ─── Robots.txt ───────────────────────────────────────────────────────────

    def _load_robots(self) -> None:
        """Descarga y parsea robots.txt (una sola vez)."""
        try:
            rp = RobotFileParser()
            rp.set_url(ROBOTS_TXT_URL)
            rp.read()
            self._robot_parser = rp
            logger.debug("robots.txt cargado.")
        except Exception as exc:
            logger.warning("No se pudo cargar robots.txt: %s. Adoptando postura permisiva.", exc)
            self._robot_parser = None

    def _can_fetch(self, url: str) -> bool:
        """True si el bot tiene permiso para acceder a la URL."""
        if not self.respect_robots or self._robot_parser is None:
            return True
        return self._robot_parser.can_fetch(ROBOTS_USER_AGENT, url)

    # ─── Slug construction ────────────────────────────────────────────────────

    @staticmethod
    def _slugify(text: str) -> str:
        """
        Convierte un título en el slug de Letterboxd.

        Letterboxd usa slugs en minúsculas con guiones donde los espacios,
        sin caracteres especiales. Números y letras permitidos.
        """
        # Normalizar acentos (NFD → ASCII)
        nfkd = unicodedata.normalize("NFKD", text)
        ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
        lowered = ascii_text.lower()
        # Reemplazar caracteres no alfanuméricos por guiones
        slug = re.sub(r"[^a-z0-9]+", "-", lowered)
        slug = slug.strip("-")
        return slug

    def _candidate_slugs(self, title: str, year: Optional[int]) -> list[str]:
        """
        Genera candidatos de slug para la película, en orden de probabilidad.

        Letterboxd a veces añade el año al slug para desambiguar.
        """
        base = self._slugify(title)
        candidates = [base]
        if year:
            candidates.append(f"{base}-{year}")
            candidates.append(f"{base}-{year}-film")
        candidates.append(f"{base}-film")
        return candidates

    # ─── HTTP helper ──────────────────────────────────────────────────────────

    def _fetch(self, url: str) -> Optional[BeautifulSoup]:
        """
        GET con delay de cortesía. Retorna BeautifulSoup o None si falla.
        No lanza excepciones — devuelve None en caso de error.
        """
        if not self._can_fetch(url):
            logger.debug("robots.txt bloqueó: %s", url)
            return None
        try:
            time.sleep(REQUEST_DELAY)
            resp = self._session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "lxml")
        except Exception as exc:
            logger.debug("Error fetching %s: %s", url, exc)
            return None

    # ─── Localización del reviews URL ─────────────────────────────────────────

    def _find_reviews_url(
        self,
        title: str,
        year: Optional[int],
        imdb_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Localiza la URL de reviews de Letterboxd para la película.

        Estrategia:
          1. Probar slugs construidos desde el título (más rápido, sin redirect).
          2. Si falla y hay imdb_id, usar el redirect /imdb/{id}/ para obtener slug.

        Returns:
            URL de reviews (str) o None si no se encuentra.
        """
        # Estrategia 1: slug por título
        for slug in self._candidate_slugs(title, year):
            reviews_url = f"{LETTERBOXD_BASE}/film/{slug}/reviews/"
            if not self._can_fetch(reviews_url):
                continue
            # Prueba silenciosa: si devuelve soup válida, la usamos
            time.sleep(REQUEST_DELAY)
            try:
                resp = self._session.get(reviews_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                if resp.status_code == 200 and "/film/" in resp.url:
                    logger.debug("Slug encontrado por título: %s", slug)
                    return resp.url  # URL final tras posibles redirects
            except Exception:
                continue

        # Estrategia 2: redirect desde IMDb ID
        if imdb_id:
            imdb_url = f"{LETTERBOXD_BASE}/imdb/{imdb_id}/"
            if self._can_fetch(imdb_url):
                try:
                    time.sleep(REQUEST_DELAY)
                    resp = self._session.get(imdb_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                    if resp.status_code == 200 and "/film/" in resp.url:
                        # Tenemos la URL del film, construir la de reviews
                        film_url = resp.url.rstrip("/") + "/"
                        reviews_url = film_url + "reviews/"
                        logger.debug("Slug obtenido vía IMDb redirect: %s", reviews_url)
                        return reviews_url
                except Exception as exc:
                    logger.debug("IMDb redirect falló: %s", exc)

        return None

    # ─── Extracción de reseñas ────────────────────────────────────────────────

    def _parse_reviews(self, soup: BeautifulSoup, max_reviews: int) -> list[str]:
        """
        Extrae el texto de las reseñas de una página de reviews de Letterboxd.

        Letterboxd renderiza las reseñas en elementos <div class="body-text">
        dentro de <li class="film-detail">.
        """
        reviews: list[str] = []

        # Método principal: div.body-text (versión moderna de Letterboxd)
        for body in soup.find_all("div", class_="body-text", limit=max_reviews * 2):
            text = body.get_text(separator=" ", strip=True)
            # Filtrar reseñas demasiado cortas (menos de 50 chars)
            if text and len(text) >= 50:
                reviews.append(text)
            if len(reviews) >= max_reviews:
                break

        # Fallback: buscar párrafos en li.film-detail
        if not reviews:
            for block in soup.find_all("li", class_="film-detail", limit=max_reviews * 2):
                paragraphs = block.find_all("p")
                text = " ".join(p.get_text(strip=True) for p in paragraphs).strip()
                if text and len(text) >= 50:
                    reviews.append(text)
                if len(reviews) >= max_reviews:
                    break

        # Fallback 2: cualquier .review-body o .review .body
        if not reviews:
            for el in soup.find_all(class_=re.compile(r"review.*body|body.*review"), limit=max_reviews * 2):
                text = el.get_text(separator=" ", strip=True)
                if text and len(text) >= 50:
                    reviews.append(text)
                if len(reviews) >= max_reviews:
                    break

        return reviews[:max_reviews]

    # ─── Paginación ───────────────────────────────────────────────────────────

    def _get_reviews_from_url(self, reviews_url: str, max_reviews: int) -> list[str]:
        """
        Extrae reseñas de una URL de reviews, con paginación si hace falta.

        Letterboxd pagina las reviews como /reviews/page/2/, etc.
        """
        all_reviews: list[str] = []
        current_url = reviews_url
        page = 1
        max_pages = 3  # Máximo 3 páginas (≈60 reviews) para ser educados

        while current_url and len(all_reviews) < max_reviews and page <= max_pages:
            soup = self._fetch(current_url)
            if soup is None:
                break

            batch = self._parse_reviews(soup, max_reviews - len(all_reviews))
            all_reviews.extend(batch)

            if len(all_reviews) >= max_reviews or not batch:
                break

            # Buscar enlace a página siguiente
            next_link = soup.find("a", class_=re.compile(r"next"))
            if next_link and next_link.get("href"):
                href = next_link["href"]
                current_url = href if href.startswith("http") else LETTERBOXD_BASE + href
                page += 1
            else:
                break

        return all_reviews[:max_reviews]

    # ─── API pública ──────────────────────────────────────────────────────────

    def get_reviews(
        self,
        title: str,
        year: Optional[int] = None,
        imdb_id: Optional[str] = None,
        max_reviews: int = 15,
    ) -> list[str]:
        """
        Obtiene hasta ``max_reviews`` reseñas de usuarios de Letterboxd.

        Args:
            title:       Título de la película en inglés.
            year:        Año de estreno (mejora la localización del slug).
            imdb_id:     IMDb ID (fallback para localizar el slug vía redirect).
            max_reviews: Número máximo de reseñas a retornar (default: 15).

        Returns:
            Lista de strings con el texto de cada reseña.
            Lista vacía si no se encuentran reseñas o el acceso está bloqueado.
        """
        logger.info(
            "Buscando reviews de Letterboxd: '%s' (%s) | max=%d",
            title, year or "?", max_reviews,
        )

        reviews_url = self._find_reviews_url(title, year=year, imdb_id=imdb_id)
        if not reviews_url:
            logger.debug("No se encontró URL de reviews para: '%s' (%s)", title, year)
            return []

        reviews = self._get_reviews_from_url(reviews_url, max_reviews)
        logger.info(
            "Reviews obtenidas: %d | '%s' | URL: %s",
            len(reviews), title, reviews_url,
        )
        return reviews


# ─── Compatibilidad backward: alias ───────────────────────────────────────────
# El LetterboxdScraper original sigue disponible para no romper imports existentes.

class LetterboxdScraper(LetterboxdReviewScraper):
    """Alias de LetterboxdReviewScraper para compatibilidad con código anterior."""

    def scrape_film(self, url: str) -> dict:
        """Stub de compatibilidad — retorna dict vacío con reviews."""
        from urllib.parse import urlparse
        parts = urlparse(url).path.strip("/").split("/")
        # /film/{slug}
        title = parts[1].replace("-", " ").title() if len(parts) > 1 else url
        reviews = self.get_reviews(title, max_reviews=5)
        return {
            "title":    title,
            "year":     "",
            "synopsis": "",
            "reviews":  reviews,
            "source_url": url,
        }


# ─── Uso de ejemplo ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    scraper = LetterboxdReviewScraper()
    reviews = scraper.get_reviews("Oppenheimer", year=2023, imdb_id="tt15398776", max_reviews=10)
    print(f"Reviews obtenidas: {len(reviews)}")
    for i, r in enumerate(reviews, 1):
        print(f"\n[{i}] {r[:200]}...")
