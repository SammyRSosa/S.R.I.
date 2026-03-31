# Oscar Insight Search
## Sistema de Recuperación de Información — Cine y Premios Oscar

> **Curso:** SRI 2025-2026 | **Corte actual:** 1 — Adquisición e Indexación
> **Modelo de Recuperación:** Booleano Extendido (Baeza-Yates & Ribeiro-Neto, 2011)

---

## Abstract

*Oscar Insight Search* es un Sistema de Recuperación de Información (SRI) de dominio restringido orientado al cine y los Premios Oscar. El sistema integra datos de **TMDB** (metadatos estructurados: director, reparto, géneros, presupuesto) y **Letterboxd** (reseñas de usuarios en lenguaje natural) para construir un corpus cinematográfico de 2000+ documentos. El modelo de recuperación empleado es el **Modelo Booleano Extendido** (EBM), que supera las limitaciones del modelo booleano clásico al incorporar ponderación tf-idf y distancias euclidianas para producir un ranking continuo de documentos relevantes.

---

## 1. Dominio del Conocimiento

| Atributo | Descripción |
|---|---|
| **Dominio** | Cine (películas en inglés, 1990–presente) |
| **Fuentes** | TMDB API v3 (metadatos) + Letterboxd (reseñas) |
| **Documentos** | 1,623+ películas indexadas |
| **Términos en índice** | 16,381 términos únicos |
| **Idioma** | Inglés (stop-words + stemming Snowball) |
| **Cobertura temporal** | 1990 – 2026 |

### 1.1 Estructura del Documento (schema v2)

Cada documento almacenado en `data/documents.json` tiene la siguiente estructura:

```json
{
  "title": "Oppenheimer",
  "year": "2023",
  "metadata": {
    "director": "Christopher Nolan",
    "cast": ["Cillian Murphy", "Emily Blunt", "Matt Damon"],
    "genres": ["Drama", "History"],
    "budget": 100000000,
    "revenue": 952000000,
    "vote_average": 8.1,
    "vote_count": 14200,
    "imdb_id": "tt15398776",
    "tmdb_id": 872585,
    "source_url": "https://www.themoviedb.org/movie/872585",
    "tagline": "The world forever changes."
  },
  "rich_text": "Oppenheimer. Drama History. Christopher Nolan. [sinopsis]. [reseñas...]",
  "reviews_count": 0
}
```

---

## 2. Modelo de Recuperación: Booleano Extendido

### 2.1 Fundamento Teórico

El Modelo Booleano Extendido (Salton et al., 1983; formalizado en Baeza-Yates & Ribeiro-Neto, 2011, Cap. 3) generaliza el modelo booleano clásico al:

1. **Ponderar los términos** mediante tf-idf.
2. **Calcular similitud** mediante distancias euclidianas, produciendo un score continuo ∈ [0, 1].

### 2.2 Fórmulas Clave

Para una consulta `q = t₁ AND t₂`:

```
sim_AND(d, q)  =  1 - sqrt( (1-w₁)² + (1-w₂)² ) / sqrt(2)
sim_OR(d, q)   =  1 - sqrt( w₁² + w₂² ) / sqrt(2)
```

donde `wᵢ = tf(i,d) · idf(i)` es el peso tf-idf del término `tᵢ` en el documento `d`.

---

## 3. Arquitectura del Sistema

```
eserrei/
├── crawler/                    # Módulo de Adquisición
│   ├── __init__.py
│   ├── tmdb_client.py          # Cliente TMDB API v3 (estrategia A: popularity + B: quality)
│   └── scraper.py              # LetterboxdReviewScraper (reseñas de usuarios)
│
├── indexer/                    # Módulo de Indexación
│   ├── __init__.py
│   └── inverted_index.py       # Índice Invertido + pipeline NLTK (lower→tokenize→stop-words→stem)
│
├── database/                   # Módulo de Almacenamiento
│   ├── __init__.py
│   ├── store.py                # DocumentStore — persistencia JSON (schema v2)
│   └── checkpoint.py           # Sistema de checkpointing para población incremental
│
├── api/                        # Módulo de Recuperación (FastAPI)
│   ├── __init__.py
│   └── main.py                 # Endpoints REST (search placeholder — Corte 2)
│
├── scripts/
│   ├── populate_tmdb.py        # Orquestador principal de población (TMDB + Letterboxd)
│   └── query.py                # Consulta interactiva del índice (CLI)
│
├── data/                       # Datos generados (excluidos del repo)
│   ├── documents.json          # Corpus (1623+ películas)
│   ├── index.json              # Índice invertido serializado
│   └── checkpoint.json         # Estado de progreso del scraping
│
├── Dockerfile                  # Imagen multietapa Python 3.11-slim
├── requirements.txt
├── .gitignore
└── README.md
```

### 3.1 Pipeline de Procesamiento

```
TMDB API (discover/movie)
     ↓  [Estrategia A: popularity.desc | Estrategia B: vote_average.desc]
Film básico {tmdb_id, title, year, overview, vote_count}
     ↓  [Filtro: vote_count ≥ 50, overview no vacío]
TMDB API (movie/{id}?append_to_response=credits,external_ids)
     ↓  [Enriquecimiento: director, cast, genres, budget, revenue, imdb_id]
Letterboxd /film/{slug}/reviews/
     ↓  [LetterboxdReviewScraper — hasta 15 reseñas/película]
rich_text = title + tagline + genres + director + cast + overview + reviews
     ↓  [InvertedIndex.add_film()]
     ↓  [_tokenize: lower → word_tokenize → stop-words → SnowballStemmer]
Posting List: término_stem → [(doc_id, tf), ...]
     ↓  [Checkpoint cada 25 docs | Guardado a disco cada 50 docs]
data/documents.json + data/index.json
```

---

## 4. Instalación y Uso

### 4.1 Prerrequisitos

- Python 3.11+
- API Key gratuita de TMDB → [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api)

### 4.2 Entorno local

```bash
# Crear entorno virtual e instalar dependencias
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

### 4.3 Poblar la base de datos

```bash
# Población completa: 100 páginas TMDB (~2000 películas) + reviews Letterboxd
python scripts/populate_tmdb.py --api-key TU_CLAVE_TMDB

# Prueba rápida (3 páginas, sin reviews, ~60 films en ~2 min)
python scripts/populate_tmdb.py --api-key TU_CLAVE_TMDB --pages 3 --no-reviews

# Reanudar desde donde se interrumpió
python scripts/populate_tmdb.py --api-key TU_CLAVE_TMDB --pages 100 --resume

# Empezar de cero
python scripts/populate_tmdb.py --api-key TU_CLAVE_TMDB --pages 100 --reset
```

> **Alternativa con variable de entorno:**
> ```bash
> $env:TMDB_API_KEY = "tu_clave"   # Windows PowerShell
> python scripts/populate_tmdb.py
> ```

### 4.4 Consultar el índice

```bash
# Búsqueda por término(s)
python scripts/query.py "dark cinematography"
python scripts/query.py "christopher nolan" --show-docs
python scripts/query.py "psychological thriller drama"
```

### 4.5 Uso programático

```python
from crawler import TmdbClient, LetterboxdReviewScraper
from database import DocumentStore
from indexer  import InvertedIndex

# Obtener metadatos de una película
client  = TmdbClient(api_key="...")
details = client.get_movie_details(872585)   # Oppenheimer
# → {title, year, director, cast, genres, budget, revenue, imdb_id, ...}

# Obtener reseñas de Letterboxd
scraper = LetterboxdReviewScraper()
reviews = scraper.get_reviews("Oppenheimer", year=2023, imdb_id="tt15398776")
# → ["A masterpiece of epic cinema...", ...]

# Consultar el índice
store = DocumentStore()
idx   = InvertedIndex()
for doc_id, film in store.documents.items():
    idx.add_film(doc_id, film)
print(idx.get_postings("nolan"))    # [(14, 2), (89, 1), ...]
```

### 4.6 API REST

```bash
# Arrancar servidor de desarrollo
uvicorn api.main:app --reload

# Health check
curl http://localhost:8000/

# Documentación interactiva
# http://localhost:8000/docs
```

### 4.7 Docker

```bash
# Construir imagen (incluye NLTK data)
docker build -t oscar-insight:0.2 .

# Ejecutar montando el volumen de datos
docker run -p 8000:8000 \
  -v "${PWD}/data:/app/data" \
  -e TMDB_API_KEY=tu_clave \
  oscar-insight:0.2
```

---

## 5. Estado del Proyecto

| Corte | Módulo | Estado |
|---|---|---|
| 1 | Adquisición TMDB (`crawler/tmdb_client.py`) | ✅ Implementado |
| 1 | Adquisición Letterboxd (`crawler/scraper.py`) | ✅ Implementado |
| 1 | Indexación (`indexer/inverted_index.py`) | ✅ Implementado |
| 1 | Almacenamiento (`database/store.py`) | ✅ Implementado |
| 1 | Checkpointing (`database/checkpoint.py`) | ✅ Implementado |
| 1 | Corpus (1623 docs, 16381 términos) | ✅ Generado |
| 2 | Motor EBM (`api/search`) | 🔲 Pendiente |
| 2 | Ranking tf-idf + distancias euclidianas | 🔲 Pendiente |
| 3 | RAG + Interfaz web | 🔲 Pendiente |

---

## 6. Control de Versiones

```bash
git init
git add .
git commit -m "feat(corte-1): adquisición TMDB + indexación — 1623 docs, 16381 términos"
```

---

## 7. Referencias Bibliográficas

1. Baeza-Yates, R., & Ribeiro-Neto, B. (2011). *Modern Information Retrieval: The Concepts and Technology behind Search* (2nd ed.). Addison-Wesley.
2. Salton, G., Fox, E. A., & Wu, H. (1983). Extended Boolean information retrieval. *Communications of the ACM*, 26(11), 1022–1036.
3. Bird, S., Klein, E., & Loper, E. (2009). *Natural Language Processing with Python*. O'Reilly Media.
4. The Movie Database. (2024). *TMDB API Documentation*. https://developer.themoviedb.org/
5. The Web Robots Pages. (2024). *robots.txt standard*. https://www.robotstxt.org/

---

*Documento generado para el Proyecto Integrador SRI 2025-2026.*
