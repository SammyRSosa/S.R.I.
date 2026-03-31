"""
crawler/wikipedia_scraper.py
Adquisición vía Wikipedia API — Oscar Insight Search (SRI 2025-2026)

Extrae metadatos de películas desde Wikipedia usando la API oficial de
Wikimedia (sin clave de API, completamente gratuita y ética).

Datos extraídos por película:
  - title, year, synopsis (extracto largo), director, cast, genre,
    country, language, awards (si aparecen en el texto), source_url,
    imdb_id (si está en Wikidata), runtime, box_office.

API de referencia:
  https://en.wikipedia.org/api/rest_v1/  (Summary REST)
  https://en.wikipedia.org/w/api.php     (Action API — extracto completo)

Uso:
    scraper = WikipediaScraper()
    data = scraper.scrape_film("Oppenheimer (film)", year=2023)
    # o búsqueda automática:
    data = scraper.search_and_scrape("Oppenheimer", year=2023)
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ─── Constantes ───────────────────────────────────────────────────────────────

WIKIPEDIA_ACTION_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_REST_API   = "https://en.wikipedia.org/api/rest_v1"
WIKIDATA_API         = "https://www.wikidata.org/w/api.php"

USER_AGENT = (
    "OscarInsightBot/1.0 "
    "(https://github.com/sri-2025/oscar-insight; educational project) "
    "python-requests/2.31"
)
REQUEST_DELAY   = 1.0   # segundos entre peticiones (respetuoso con los servidores)
REQUEST_TIMEOUT = 15


class WikipediaScraper:
    """
    Scraper ético para Wikipedia vía API oficial (Action API + REST API).

    No requiere registro ni clave de API. Respeta el User-Agent recomendado
    por Wikimedia y aplica un delay de cortesía entre peticiones.

    Flujo de uso::

        scraper = WikipediaScraper()

        # Opción A: conoces el título exacto del artículo
        data = scraper.scrape_film("Oppenheimer (film)", year=2023)

        # Opción B: búsqueda automática por título de película
        data = scraper.search_and_scrape("Oppenheimer", year=2023)

    Returns:
        dict con las claves:
            title, year, synopsis, director, cast, genre, country,
            language, runtime, box_office, awards, source_url, imdb_id,
            reviews (lista vacía — Wikipedia no tiene reseñas de usuarios).
    """

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    # ─── HTTP helpers ─────────────────────────────────────────────────────────

    def _get_json(self, url: str, params: dict) -> dict:
        """GET con delay de cortesía → JSON."""
        time.sleep(REQUEST_DELAY)
        resp = self.session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    # ─── Búsqueda de artículo ─────────────────────────────────────────────────

    def _search_article(self, query: str, year: Optional[int] = None) -> Optional[str]:
        """
        Busca el título exacto del artículo de Wikipedia para una película.

        Estrategia:
          1. Prueba «{query} (film)» si el año no específica el artículo.
          2. Usa la Wikipedia search API con el query + año.
          3. Devuelve el primer resultado relevante.

        Returns:
            Título del artículo de Wikipedia o None si no se encuentra.
        """
        # Candidatos a probar en orden de prioridad
        candidates = []

        if year:
            candidates += [
                f"{query} ({year} film)",
                f"{query} (film)",
            ]
        else:
            candidates.append(f"{query} (film)")
        candidates.append(query)

        # Verificar existencia de cada candidato
        for candidate in candidates:
            params = {
                "action":  "query",
                "titles":  candidate,
                "format":  "json",
                "formatversion": "2",
            }
            data = self._get_json(WIKIPEDIA_ACTION_API, params)
            pages = data.get("query", {}).get("pages", [])
            if pages and pages[0].get("pageid") and pages[0].get("pageid") != -1:
                found = pages[0]["title"]
                logger.info("Artículo encontrado: '%s'", found)
                return found

        # Fallback: búsqueda de texto libre
        year_str = str(year) if year else ""
        search_query = f"{query} {year_str} film".strip()
        params = {
            "action":   "query",
            "list":     "search",
            "srsearch": search_query,
            "srlimit":  5,
            "srnamespace": 0,
            "format":   "json",
        }
        data = self._get_json(WIKIPEDIA_ACTION_API, params)
        results = data.get("query", {}).get("search", [])
        if results:
            found = results[0]["title"]
            logger.info("Búsqueda de texto devuelve: '%s'", found)
            return found

        logger.warning("No se encontró artículo de Wikipedia para: '%s' (%s)", query, year)
        return None

    # ─── Extracción de extracto / sinopsis ────────────────────────────────────

    def _get_extract(self, title: str) -> str:
        """Obtiene el extracto de texto completo del artículo (sin markup wiki)."""
        params = {
            "action":   "query",
            "titles":   title,
            "prop":     "extracts",
            "exintro":  True,        # Solo la introducción (antes de la primera sección)
            "explaintext": True,     # Sin HTML, texto plano
            "format":   "json",
            "formatversion": "2",
        }
        data = self._get_json(WIKIPEDIA_ACTION_API, params)
        pages = data.get("query", {}).get("pages", [])
        if pages:
            extract = pages[0].get("extract", "")
            # Limpiar caracteres extraños
            extract = re.sub(r"\n{3,}", "\n\n", extract).strip()
            return extract
        return ""

    # ─── Extracción de infobox vía Wikitext ───────────────────────────────────

    def _get_infobox(self, title: str) -> dict:
        """
        Extrae los campos de la infobox de película directamente del wikitext.

        Returns:
            dict con claves: director, cast, genre, country, language,
            runtime, box_office, release_date.
        """
        params = {
            "action": "query",
            "titles": title,
            "prop":   "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "rvsection": "0",
            "format": "json",
            "formatversion": "2",
        }
        data = self._get_json(WIKIPEDIA_ACTION_API, params)
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            return {}

        wikitext = pages[0].get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("content", "")
        return self._parse_infobox(wikitext)

    @staticmethod
    def _parse_infobox(wikitext: str) -> dict:
        """Parsea los campos relevantes de una infobox de película en wikitext."""
        fields = {}

        # Mapa de campos que nos interesan
        field_map = {
            "director":    "director",
            "starring":    "cast",
            "genre":       "genre",
            "country":     "country",
            "language":    "language",
            "runtime":     "runtime",
            "gross":       "box_office",
            "budget":      "budget",
            "released":    "release_date",
        }

        for wiki_key, out_key in field_map.items():
            # Regex tolerante a espacios alrededor del «=»
            pattern = rf"\|\s*{wiki_key}\s*=\s*(.*?)(?=\n\s*\||\n\s*\}}|\Z)"
            match = re.search(pattern, wikitext, re.IGNORECASE | re.DOTALL)
            if match:
                raw = match.group(1).strip()
                # 1. Eliminar referencias <ref...>...</ref>
                clean = re.sub(r"<ref[^>]*>.*?</ref>", "", raw, flags=re.DOTALL)
                # 2. Eliminar {{Plainlist|...}} y {{Unbulleted list|...}} conservando el contenido
                clean = re.sub(
                    r"\{\{(?:Plainlist|Unbulleted list|Flatlist|hlist)[^}]*\|([^}]*)\}\}",
                    r"\1", clean, flags=re.IGNORECASE | re.DOTALL,
                )
                # 3. Eliminar {{Plainlist| sin cierre que quede
                clean = re.sub(r"\{\{(?:Plainlist|Unbulleted list|Flatlist|hlist)\s*\|?", "", clean, flags=re.IGNORECASE)
                # 4. [[link|texto]] → texto, [[link]] → link
                clean = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", clean)
                # 5. Eliminar templates restantes {{...}}
                clean = re.sub(r"\{\{[^}]*\}\}", "", clean)
                # 6. Eliminar tags HTML
                clean = re.sub(r"<[^>]+>", "", clean)
                # 7. Convertir bullets (* item) a comas
                items = re.split(r"\*|\n", clean)
                items = [i.strip().strip(",").strip() for i in items if i.strip().strip(",").strip()]
                clean = ", ".join(items)
                # 8. Limpiar comas dobles y espacios
                clean = re.sub(r",\s*,", ",", clean).strip(" ,{}")
                if clean:
                    fields[out_key] = clean

        return fields

    # ─── Extracción de URL de IMDb desde Wikidata ─────────────────────────────

    def _get_imdb_id(self, title: str) -> str:
        """
        Consulta Wikidata para obtener el IMDb ID a partir del título de Wikipedia.
        Retorna cadena vacía si no se encuentra.
        """
        # Primero obtener el Wikidata QID de la página de Wikipedia
        params = {
            "action": "query",
            "titles": title,
            "prop":   "pageprops",
            "ppprop": "wikibase_item",
            "format": "json",
            "formatversion": "2",
        }
        data = self._get_json(WIKIPEDIA_ACTION_API, params)
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            return ""
        qid = pages[0].get("pageprops", {}).get("wikibase_item", "")
        if not qid:
            return ""

        # Luego consultar Wikidata por P345 (IMDb ID)
        params = {
            "action": "wbgetclaims",
            "entity": qid,
            "property": "P345",
            "format": "json",
        }
        data = self._get_json(WIKIDATA_API, params)
        claims = data.get("claims", {}).get("P345", [])
        if claims:
            imdb_id = claims[0]["mainsnak"]["datavalue"]["value"]
            logger.info("IMDb ID para '%s': %s", title, imdb_id)
            return imdb_id

        return ""

    # ─── Método principal de scraping ─────────────────────────────────────────

    def scrape_film(self, wikipedia_title: str, year: Optional[int] = None) -> dict:
        """
        Extrae metadatos completos de una película dado el título exacto del
        artículo de Wikipedia.

        Args:
            wikipedia_title: Título exacto del artículo, ej. "Oppenheimer (film)".
            year: Año de estreno (opcional, añadido al resultado).

        Returns:
            dict compatible con DocumentStore.add_film() y InvertedIndex.add_film().
        """
        logger.info("Scraping Wikipedia: '%s'", wikipedia_title)

        # Obtener sinopsis (introducción del artículo)
        synopsis = self._get_extract(wikipedia_title)

        # Obtener campos de la infobox
        infobox = self._get_infobox(wikipedia_title)

        # Obtener IMDb ID desde Wikidata
        imdb_id = self._get_imdb_id(wikipedia_title)

        # Construir año final (infobox puede tener fecha completa)
        year_str = str(year) if year else ""
        if not year_str and infobox.get("release_date"):
            m = re.search(r"\b(19|20)\d{2}\b", infobox["release_date"])
            if m:
                year_str = m.group(0)

        # Limpiar sinopsis: a veces la intro de Wikipedia tiene todo el resumen
        # Limitamos a ~800 caracteres para mantenerlo legible en el índice
        synopsis_trimmed = synopsis[:1500].strip() if synopsis else "Sinopsis no disponible."

        film_data = {
            "title":      wikipedia_title.replace(" (film)", "").replace(" (2023 film)", ""),
            "year":       year_str,
            "synopsis":   synopsis_trimmed,
            "director":   infobox.get("director", ""),
            "cast":       infobox.get("cast", ""),
            "genre":      infobox.get("genre", ""),
            "country":    infobox.get("country", ""),
            "language":   infobox.get("language", ""),
            "runtime":    infobox.get("runtime", ""),
            "box_office": infobox.get("box_office", ""),
            "budget":     infobox.get("budget", ""),
            "awards":     "",                   # Se enriquece desde el extracto
            "reviews":    [],                   # Wikipedia no tiene reseñas de usuarios
            "source_url": f"https://en.wikipedia.org/wiki/{wikipedia_title.replace(' ', '_')}",
            "imdb_id":    imdb_id,
        }

        # Extraer menciones a premios del texto de la sinopsis
        # La intro de Wikipedia suele mencionar los premios ganados más importantes
        awards_mentions = []
        award_patterns = [
            r"Academy Award[s]? for [A-Z][^,\.\n]{0,60}",
            r"won (?:seven|six|five|four|three|two|one|\d+) Academy Award[s]?[^,\.\n]{0,50}",
            r"nominated for (?:thirteen|twelve|eleven|ten|nine|eight|seven|six|five|four|three|two|one|\d+) Academy Award[s]?",
            r"Golden Globe Award[s]? for [A-Z][^,\.\n]{0,50}",
            r"BAFTA Award[s]? for [A-Z][^,\.\n]{0,50}",
            r"Palme d[\''\u2019]Or[^,\.\n]{0,40}",
            r"C\u00e9sar Award[s]? for [A-Z][^,\.\n]{0,50}",
        ]
        # Normalizamos la synopsis a una sola línea para el regex
        synopsis_flat = re.sub(r"\s+", " ", synopsis)
        for pattern in award_patterns:
            for m in re.finditer(pattern, synopsis_flat, re.IGNORECASE):
                snippet = re.sub(r"\s+", " ", m.group(0)).strip().rstrip(",")
                if snippet and len(snippet) > 10 and snippet not in awards_mentions:
                    awards_mentions.append(snippet)

        film_data["awards"] = "; ".join(awards_mentions[:5])

        # Limpiar el título (quitar " (film)" del nombre)
        raw_title = wikipedia_title
        raw_title = re.sub(r"\s*\(\d{4}\s+film\)", "", raw_title)
        raw_title = re.sub(r"\s*\(film\)", "", raw_title)
        film_data["title"] = raw_title.strip()

        logger.info(
            "OK: '%s' (%s) | director=%s | imdb=%s",
            film_data["title"], film_data["year"],
            film_data["director"][:30] if film_data["director"] else "?",
            imdb_id or "—",
        )
        return film_data

    def search_and_scrape(self, movie_title: str, year: Optional[int] = None) -> dict:
        """
        Busca automáticamente el artículo de Wikipedia para una película y
        luego extrae sus metadatos.

        Args:
            movie_title: Título de la película (no necesariamente el art. de WP).
            year: Año de estreno (mejora la búsqueda y la precisión).

        Returns:
            dict compatible con DocumentStore / InvertedIndex.

        Raises:
            ValueError: Si no se encuentra ningún artículo de Wikipedia.
        """
        article_title = self._search_article(movie_title, year=year)
        if not article_title:
            raise ValueError(
                f"No se encontró artículo de Wikipedia para: '{movie_title}' ({year})"
            )
        return self.scrape_film(article_title, year=year)


# ─── Uso de ejemplo ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    scraper = WikipediaScraper()
    result = scraper.search_and_scrape("Oppenheimer", year=2023)
    print(json.dumps(result, indent=2, ensure_ascii=False))
