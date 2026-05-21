"""
scripts/seed_crawler.py
Crawler de Páginas Semilla — Oscar Insight Search (Corte 3)

Descarga páginas HTML desde URLs semilla predefinidas (Wikipedia, etc.),
extrae el texto limpio, y las inserta como documentos especiales en el
DocumentStore local para que la búsqueda EBM + FAISS las encuentre sin
necesidad de consultas web en tiempo real.

Uso:
    python -m scripts.seed_crawler
"""

from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Asegurar que el proyecto esté en el path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.store import DocumentStore
from indexer.inverted_index import InvertedIndex
from indexer.ebm import ExtendedBooleanModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ─── URLs SEMILLA ────────────────────────────────────────────────────────────
# Estas son las páginas que queremos tener en nuestro corpus local
# para responder preguntas sobre los Oscar sin depender de DuckDuckGo.

SEED_URLS = [
    # Ceremonias de los Oscar por año (2010-2025)
    {"url": "https://en.wikipedia.org/wiki/97th_Academy_Awards", "title": "97th Academy Awards (2025 Ceremony)", "year": "2025", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/96th_Academy_Awards", "title": "96th Academy Awards (2024 Ceremony)", "year": "2024", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/95th_Academy_Awards", "title": "95th Academy Awards (2023 Ceremony)", "year": "2023", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/94th_Academy_Awards", "title": "94th Academy Awards (2022 Ceremony)", "year": "2022", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/93rd_Academy_Awards", "title": "93rd Academy Awards (2021 Ceremony)", "year": "2021", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/92nd_Academy_Awards", "title": "92nd Academy Awards (2020 Ceremony)", "year": "2020", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/91st_Academy_Awards", "title": "91st Academy Awards (2019 Ceremony)", "year": "2019", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/90th_Academy_Awards", "title": "90th Academy Awards (2018 Ceremony)", "year": "2018", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/89th_Academy_Awards", "title": "89th Academy Awards (2017 Ceremony)", "year": "2017", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/88th_Academy_Awards", "title": "88th Academy Awards (2016 Ceremony)", "year": "2016", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/87th_Academy_Awards", "title": "87th Academy Awards (2015 Ceremony)", "year": "2015", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/86th_Academy_Awards", "title": "86th Academy Awards (2014 Ceremony)", "year": "2014", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/85th_Academy_Awards", "title": "85th Academy Awards (2013 Ceremony)", "year": "2013", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/84th_Academy_Awards", "title": "84th Academy Awards (2012 Ceremony)", "year": "2012", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/83rd_Academy_Awards", "title": "83rd Academy Awards (2011 Ceremony)", "year": "2011", "category": "oscar_ceremony"},
    {"url": "https://en.wikipedia.org/wiki/82nd_Academy_Awards", "title": "82nd Academy Awards (2010 Ceremony)", "year": "2010", "category": "oscar_ceremony"},
    # Listas completas de premios por categoría
    {"url": "https://en.wikipedia.org/wiki/Academy_Award_for_Best_Picture", "title": "Academy Award for Best Picture - Complete History", "year": "2025", "category": "oscar_history"},
    {"url": "https://en.wikipedia.org/wiki/Academy_Award_for_Best_Director", "title": "Academy Award for Best Director - Complete History", "year": "2025", "category": "oscar_history"},
    {"url": "https://en.wikipedia.org/wiki/Academy_Award_for_Best_Actor", "title": "Academy Award for Best Actor - Complete History", "year": "2025", "category": "oscar_history"},
    {"url": "https://en.wikipedia.org/wiki/Academy_Award_for_Best_Actress", "title": "Academy Award for Best Actress - Complete History", "year": "2025", "category": "oscar_history"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def extract_clean_text(html: str) -> str:
    """Extrae texto limpio de HTML, eliminando navegación, scripts y ruido."""
    soup = BeautifulSoup(html, "html.parser")

    # Eliminar elementos de UI/navegación
    for tag in soup(["script", "style", "nav", "footer", "header", "aside",
                     "form", "iframe", "noscript", "link", "meta"]):
        tag.decompose()

    # Para Wikipedia: eliminar elementos de navegación específicos
    for cls in ["navbox", "mw-jump-link", "mw-editsection", "reflist",
                "reference", "sidebar", "toc", "catlinks", "mw-indicators",
                "printfooter", "sistersitebox", "noprint"]:
        for el in soup.find_all(class_=cls):
            el.decompose()
    for el in soup.find_all(id=["mw-navigation", "footer", "catlinks",
                                "siteSub", "contentSub"]):
        el.decompose()

    # Extraer texto del cuerpo principal
    content = soup.find(id="mw-content-text") or soup.find("body") or soup
    text = content.get_text(separator=" ")

    # Limpiar espacios múltiples
    text = re.sub(r"\s+", " ", text).strip()
    # Limitar a ~15,000 caracteres para no sobrecargar el índice
    return text[:15000]


def crawl_seed_url(seed: dict) -> dict | None:
    """Descarga y procesa una URL semilla."""
    url = seed["url"]
    logger.info("Crawleando: %s", url)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        logger.error("Error descargando %s: %s", url, e)
        return None

    text = extract_clean_text(resp.text)
    if len(text) < 200:
        logger.warning("Texto demasiado corto para %s (%d chars). Saltando.", url, len(text))
        return None

    logger.info("Extraídos %d caracteres de: %s", len(text), seed["title"])

    # Construir documento en formato v2 compatible con DocumentStore
    return {
        "title": seed["title"],
        "year": seed.get("year", "N/A"),
        "metadata": {
            "director": "Wikipedia",
            "cast": [],
            "genres": ["Reference", seed.get("category", "general")],
            "budget": 0,
            "revenue": 0,
            "vote_average": 0.0,
            "vote_count": 0,
            "original_language": "en",
            "imdb_id": "",
            "tmdb_id": None,
            "source_url": url,
            "letterboxd_url": "",
            "tagline": f"Crawled from {url}",
        },
        "rich_text": f"{seed['title']}. {text}",
        "reviews_count": 0,
    }


def main():
    logger.info("=" * 60)
    logger.info("SEED CRAWLER — Oscar Insight Search")
    logger.info("Crawleando %d URLs semilla...", len(SEED_URLS))
    logger.info("=" * 60)

    store = DocumentStore()
    initial_count = len(store.documents)
    logger.info("Corpus actual: %d documentos.", initial_count)

    added = 0
    failed = 0

    for seed in SEED_URLS:
        doc = crawl_seed_url(seed)
        if doc:
            doc_id = store.add_film(doc)
            logger.info("  → Añadido como doc_id=%d: %s", doc_id, doc["title"])
            added += 1
        else:
            failed += 1
        # Pausa cortés entre requests
        time.sleep(1.0)

    # Guardar corpus actualizado
    store.save()
    final_count = len(store.documents)

    logger.info("=" * 60)
    logger.info("RESULTADO: %d añadidas, %d fallidas.", added, failed)
    logger.info("Corpus: %d → %d documentos.", initial_count, final_count)
    logger.info("=" * 60)

    if added > 0:
        logger.info("")
        logger.info("PASO 2: Reconstruyendo índice EBM con el corpus actualizado...")
        idx = InvertedIndex()
        
        for doc_id, film in store.documents.items():
            text = film.get("rich_text", "") or film.get("synopsis", "")
            if text:
                idx.add_document(doc_id, text)

        ebm = ExtendedBooleanModel(store, idx)
        ebm.build_weights()
        ebm.save_weights()
        logger.info("Índice EBM reconstruido con %d documentos.", len(store.documents))

        logger.info("")
        logger.info("IMPORTANTE: Ahora ejecuta también:")
        logger.info("  python -m scripts.build_vector_index")
        logger.info("para reconstruir el índice FAISS con los nuevos documentos.")


if __name__ == "__main__":
    main()
