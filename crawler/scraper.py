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
        
        # Metacritic renders user reviews primarily in spans inside review structures
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
                
        # Fallback si span no arroja resultados, buscar los divs de quotes
        if not reviews:
            for tag in soup.find_all("div", class_=lambda c: c and any(cls in c for cls in REVIEW_CLASSES)):
                text = tag.get_text(separator=" ", strip=True)
                if 100 < len(text) < 3000 and text not in reviews:
                    reviews.append(text)
                if len(reviews) >= max_n:
                    break

        return reviews[:max_n]

    # ─── API pública ──────────────────────────────────────────────────────────

    def get_reviews(
        self,
        title: str,
        year: Optional[int] = None,
        imdb_id: Optional[str] = None,
        max_reviews: int = 10,
    ) -> list[str]:
        """
        Obtiene `max_reviews` críticas largas (User Reviews) de Metacritic.
        """
        slug = self._slugify(title)
        logger.info("――― Metacritic: '%s' (%s) -> slug: %s", title, year or "?", slug)

        # Tratar variaciones de slug si Metacritic anexa el año 
        candidates = [slug]
        if year:
            candidates.append(f"{slug}-{year}")

        for s in candidates:
            url = f"{BASE_URL}/movie/{s}/user-reviews/"
            html = self._get(url, label=f"slug:{s}")
            
            if html:
                reviews = self._parse_reviews(html, max_reviews)
                if reviews:
                    logger.info("  -> Total: %d reseñas ricas (Metacritic)", len(reviews))
                    return reviews
                    
        logger.warning("  -> No localizado / Sin reseñas largas.")
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
