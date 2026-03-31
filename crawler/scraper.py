"""
crawler/scraper.py
Módulo de Adquisición — Oscar Insight Search (SRI 2025-2026)

LetterboxdReviewScraper: sesión única persistente con cloudscraper.

Diseño clave:
  - UN solo objeto cloudscraper. Todas las peticiones reutilizan cookies/TLS.
  - Precalentamiento: visita la homepage para obtener cookies Cloudflare antes
    de ir a cualquier URL de película.
  - Endpoints validados 2025:
      /film/{slug}/reviews/by/popularity/  → 200, ~12 reseñas/página
      /film/{slug}/reviews/by/activity/    → 200, fallback
  - Delay aleatorio 2–4 s entre peticiones (patrón humano).
  - Log explícito del status_code de cada GET para trazabilidad.

Uso:
    scraper = LetterboxdReviewScraper()
    reviews = scraper.get_reviews(imdb_id="tt15398776",
                                  title="Oppenheimer",
                                  year=2023,
                                  max_reviews=10)
    # → ["Trading your peace of mind for the power of the sun...", ...]
"""

from __future__ import annotations

import logging
import random
import re
import time
import unicodedata
from typing import Optional
from urllib.robotparser import RobotFileParser

import cloudscraper
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────

LETTERBOXD_BASE = "https://letterboxd.com"
ROBOTS_TXT_URL  = "https://letterboxd.com/robots.txt"
BOT_AGENT       = "OscarInsightBot/0.3 (+academia)"

DELAY_MIN = 2.0   # segundos delay mínimo entre peticiones
DELAY_MAX = 4.0   # segundos delay máximo
TIMEOUT   = 20    # timeout HTTP

# Señales de Cloudflare challenge (llega con 200 pero es una barrera JS)
CF_SIGNALS = ["Just a moment", "Checking your browser", "cf-browser-verification"]

# Endpoints de reviews en orden de preferencia (validados en 2025)
REVIEW_ENDPOINTS = [
    "reviews/by/popularity/",
    "reviews/by/activity/",
]

# Headers de Chrome real
_HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://letterboxd.com/",
    "Connection":      "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


class LetterboxdReviewScraper:
    """
    Extractor de reseñas de Letterboxd con sesión única persistente.

    La sesión se precalienta visitando la homepage para obtener las cookies
    de Cloudflare antes de cualquier request a páginas de reviews.

    Args:
        respect_robots: Respetar robots.txt (default: True).
        warmup:         Visitar homepage al iniciar para obtener cookies
                        Cloudflare (default: True, desactivar en tests).

    Example::

        scraper = LetterboxdReviewScraper()
        reviews = scraper.get_reviews(
            imdb_id="tt15398776",
            title="Oppenheimer",
            year=2023,
            max_reviews=10,
        )
    """

    def __init__(self, respect_robots: bool = True, warmup: bool = True) -> None:
        # ── Sesión única — todas las peticiones comparten cookies/TLS ─────────
        self._s = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "desktop": True},
            delay=10,           # Tiempo máximo que cloudscraper espera para JS challenge
        )
        self._s.headers.update(_HEADERS)

        # ── robots.txt ────────────────────────────────────────────────────────
        self._rp: Optional[RobotFileParser] = None
        if respect_robots:
            self._load_robots()

        # ── Precalentamiento: homepage → cookies Cloudflare ───────────────────
        if warmup:
            self._warmup()

    # ─── Helpers de sesión ────────────────────────────────────────────────────

    def _load_robots(self) -> None:
        try:
            rp = RobotFileParser()
            rp.set_url(ROBOTS_TXT_URL)
            rp.read()
            self._rp = rp
        except Exception:
            pass   # Postura permisiva si robots.txt no es accesible

    def _can_fetch(self, url: str) -> bool:
        if self._rp is None:
            return True
        return self._rp.can_fetch(BOT_AGENT, url)

    def _sleep(self, extra: float = 0.0) -> None:
        """Delay aleatorio entre DELAY_MIN y DELAY_MAX segundos."""
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX) + extra)

    def _warmup(self) -> None:
        """
        Visita la homepage de Letterboxd para obtener las cookies de Cloudflare.
        Sin esto, la primera petición a una página de película puede devolver 403.
        """
        logger.info("Precalentando sesión Letterboxd (homepage)...")
        self._get_html(LETTERBOXD_BASE + "/", label="warmup")
        self._sleep()

    # ─── GET central ──────────────────────────────────────────────────────────

    def _get_html(
        self,
        url: str,
        label: str = "",
        allow_redirects: bool = True,
        retries: int = 2,
    ) -> Optional[tuple[str, str]]:
        """
        GET HTTP con la sesión única. Logea siempre el status_code.

        Args:
            url:             URL a obtener.
            label:           Etiqueta para el log (facilita debug).
            allow_redirects: Seguir redirects (default: True).
            retries:         Reintentos en caso de error (default: 2).

        Returns:
            Tupla ``(html: str, final_url: str)`` o ``None`` si falla.
        """
        if not self._can_fetch(url):
            logger.debug("[%s] robots.txt bloquea: %s", label, url)
            return None

        for attempt in range(retries + 1):
            if attempt > 0:
                extra_wait = attempt * 3.0
                logger.debug("[%s] Reintento %d — esperando %.0fs", label, attempt, extra_wait)
                time.sleep(extra_wait)
            else:
                self._sleep()

            try:
                resp = self._s.get(url, timeout=TIMEOUT, allow_redirects=allow_redirects)

                # Log explícito de status para depuración
                logger.info("[%s] GET %s -> %d (final: %s)",
                            label or "req", url, resp.status_code, resp.url)

                if resp.status_code == 404:
                    return None
                if resp.status_code == 403:
                    logger.warning("[%s] 403 Forbidden en %s", label, url)
                    return None
                if resp.status_code == 429:
                    logger.warning("[%s] 429 Rate Limited — esperando 45s", label)
                    time.sleep(45)
                    continue
                if resp.status_code != 200:
                    logger.warning("[%s] HTTP %d en %s", label, resp.status_code, url)
                    continue

                # Detectar Cloudflare challenge disfrazado de 200
                if any(sig in resp.text[:2000] for sig in CF_SIGNALS):
                    logger.warning("[%s] Cloudflare challenge detectado (intento %d)", label, attempt + 1)
                    time.sleep(6 * (attempt + 1))
                    continue

                return (resp.text, resp.url)

            except Exception as exc:
                logger.warning("[%s] Excepción en intento %d: %s", label, attempt + 1, exc)

        return None

    # ─── Resolución del slug de Letterboxd ────────────────────────────────────

    @staticmethod
    def _slugify(text: str) -> str:
        """Convierte texto en slug Letterboxd (ascii lowercase, guiones)."""
        nfkd = unicodedata.normalize("NFKD", text)
        ascii_t = nfkd.encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_t.lower())
        return slug.strip("-")

    def _resolve_film_url(
        self,
        imdb_id: Optional[str],
        title: str,
        year: Optional[int],
    ) -> Optional[str]:
        """
        Resuelve la URL del film en Letterboxd.

        Estrategia 1 — IMDb redirect (más precisa):
            GET /imdb/{imdb_id}/ → 302 → /film/{slug}/

        Estrategia 2 — Heurística (fallback):
            Prueba /film/{slug}-{year}/ y /film/{slug}/

        Returns:
            URL del film con / final, ej: "https://letterboxd.com/film/oppenheimer-2023/"
            o None si no se localiza.
        """
        # ── Estrategia 1: redirect por IMDb ID ────────────────────────────────
        if imdb_id:
            result = self._get_html(
                f"{LETTERBOXD_BASE}/imdb/{imdb_id}/",
                label=f"imdb-redirect:{imdb_id}",
            )
            if result:
                _, final_url = result
                if "/film/" in final_url:
                    film_url = final_url.rstrip("/") + "/"
                    logger.info("Slug via IMDb redirect: %s", film_url)
                    return film_url

        # ── Estrategia 2: slug heurístico ─────────────────────────────────────
        base = self._slugify(title)
        candidates = []
        if year:
            candidates.append(f"{base}-{year}")
        candidates.append(base)

        for slug in candidates:
            url = f"{LETTERBOXD_BASE}/film/{slug}/"
            result = self._get_html(url, label=f"slug:{slug}")
            if result:
                _, final_url = result
                if "/film/" in final_url:
                    film_url = final_url.rstrip("/") + "/"
                    logger.info("Slug via heurística: %s", film_url)
                    return film_url

        return None

    # ─── Parseo de reseñas ────────────────────────────────────────────────────

    @staticmethod
    def _parse_reviews(soup: BeautifulSoup, max_n: int) -> list[str]:
        """
        Extrae texto de reseñas del HTML de Letterboxd.

        Selector validado 2025:
            <div class="body-text ...">
                <p>Texto de la reseña aquí.</p>
            </div>
        """
        reviews: list[str] = []

        for div in soup.find_all("div", class_=lambda c: c and "body-text" in c):
            # Priorizar párrafos internos; fallback a texto del div completo
            paras = div.find_all("p")
            text = (
                " ".join(p.get_text(separator=" ", strip=True) for p in paras)
                if paras
                else div.get_text(separator=" ", strip=True)
            )
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) >= 50 and text not in reviews:
                reviews.append(text)
            if len(reviews) >= max_n:
                break

        return reviews

    # ─── Extracción de reseñas ────────────────────────────────────────────────

    def _fetch_reviews(self, film_url: str, max_reviews: int) -> list[str]:
        """
        Prueba los endpoints de reviews en orden y retorna los textos extraídos.
        Pagina hasta 2 páginas si necesita más reseñas.
        """
        for endpoint in REVIEW_ENDPOINTS:
            url = film_url + endpoint
            result = self._get_html(url, label=f"reviews:{endpoint.strip('/')}")
            if not result:
                continue

            html, _ = result
            soup = BeautifulSoup(html, "lxml")
            reviews = self._parse_reviews(soup, max_reviews)

            if reviews:
                logger.info("  %d reseñas en /%s", len(reviews), endpoint)

                # Página 2 si necesitamos más
                if len(reviews) < max_reviews:
                    result2 = self._get_html(url + "page/2/", label="reviews:p2")
                    if result2:
                        soup2 = BeautifulSoup(result2[0], "lxml")
                        more = self._parse_reviews(soup2, max_reviews - len(reviews))
                        reviews.extend(more)

                return reviews[:max_reviews]

        return []

    # ─── API pública ──────────────────────────────────────────────────────────

    def get_reviews(
        self,
        title: str,
        year: Optional[int] = None,
        imdb_id: Optional[str] = None,
        max_reviews: int = 10,
    ) -> list[str]:
        """
        Obtiene hasta ``max_reviews`` reseñas de Letterboxd para una película.

        Args:
            title:       Título en inglés.
            year:        Año de estreno.
            imdb_id:     IMDb ID (tt1234567) — muy recomendado para precisión.
            max_reviews: Máx. reseñas a devolver (default: 10).

        Returns:
            Lista de strings. Vacía si no se encuentra o Letterboxd bloquea.
        """
        logger.info("=== Letterboxd: '%s' (%s) | imdb=%s ===",
                    title, year or "?", imdb_id or "N/A")

        film_url = self._resolve_film_url(imdb_id=imdb_id, title=title, year=year)
        if not film_url:
            logger.warning("  -> No localizado en Letterboxd")
            return []

        reviews = self._fetch_reviews(film_url, max_reviews)
        logger.info("  -> Total reseñas obtenidas: %d", len(reviews))
        return reviews


# ─── Alias backward ───────────────────────────────────────────────────────────

class LetterboxdScraper(LetterboxdReviewScraper):
    """Alias de compatibilidad con código anterior."""

    def scrape_film(self, url: str) -> dict:
        from urllib.parse import urlparse
        parts = urlparse(url).path.strip("/").split("/")
        title = parts[1].replace("-", " ").title() if len(parts) > 1 else url
        return {
            "title": title, "year": "", "synopsis": "",
            "reviews": self.get_reviews(title, max_reviews=5),
            "source_url": url,
        }


# ─── Prueba directa ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    scraper = LetterboxdReviewScraper()
    reviews = scraper.get_reviews(
        title="Oppenheimer", year=2023,
        imdb_id="tt15398776", max_reviews=5,
    )
    print(f"\nReseñas obtenidas: {len(reviews)}")
    for i, r in enumerate(reviews, 1):
        print(f"\n[{i}] {r[:250]}")
