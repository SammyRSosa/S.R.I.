# Oscar Insight Search  
## Sistema de Recuperación de Información sobre Cine y Premios Oscar

> **Curso:** SRI 2025-2026 | **Corte:** 1 — Adquisición e Indexación  
> **Modelo de Recuperación:** Booleano Extendido (Baeza-Yates & Ribeiro-Neto, 2011)

---

## Abstract

*Oscar Insight Search* es un Sistema de Recuperación de Información (SRI) de dominio restringido orientado al cine y los Premios Oscar. El sistema integra datos de **Letterboxd** (críticas de usuarios y metadatos de películas) e **IMDb** (datos estructurados de producciones nominadas) con el objetivo de permitir búsquedas semánticas y booleanas sobre un corpus cinematográfico curado. El modelo de recuperación empleado es el **Modelo Booleano Extendido** (EBM), que supera las limitaciones del modelo booleano clásico al incorporar ponderación tf-idf y distancias euclidianas para producir un ranking continuo de documentos relevantes.

---

## 1. Dominio del Conocimiento

| Atributo | Descripción |
|---|---|
| **Dominio** | Cine y Premios Academia (Oscar) |
| **Fuentes** | Letterboxd, IMDb |
| **Tipo de documentos** | Fichas de película (título, año, sinopsis) + críticas de usuarios |
| **Idioma(s)** | Inglés (principal), Español (soporte parcial en stop-words) |
| **Cobertura temporal** | 1927 – Presente |

### 1.1 Justificación del Dominio

Los Premios Oscar concentran anualmente la atención mediática global y generan una vasta producción textual: reseñas críticas, análisis comparativos y comentarios de audiencia. Este corpus presenta variedad léxica y temática suficiente para evaluar un SRI en condiciones realistas.

---

## 2. Modelo de Recuperación: Booleano Extendido

### 2.1 Fundamento Teórico

El Modelo Booleano Extendido (Salton et al., 1983; formalizado en Baeza-Yates & Ribeiro-Neto, 2011, Cap. 3) generaliza el modelo booleano clásico al:

1. **Ponderar los términos** mediante tf-idf, convirtiendo cada documento en un vector en el espacio de términos del vocabulario.
2. **Calcular similitud** mediante distancias euclidianas, en lugar de coincidencia exacta, produciendo un score continuo ∈ [0, 1].

### 2.2 Fórmulas Clave

Para una consulta `q = t₁ AND t₂`:

```
sim_AND(d, q)  =  1 - sqrt( (1-w₁)² + (1-w₂)² ) / sqrt(2)
sim_OR(d, q)   =  1 - sqrt( w₁² + w₂² ) / sqrt(2)
```

donde `wᵢ = tf(i,d) · idf(i)` es el peso tf-idf del término `tᵢ` en el documento `d`.

### 2.3 Por qué EBM y no el Modelo Vectorial Clásico

| Criterio | Modelo Vectorial | Modelo Booleano Extendido |
|---|---|---|
| Expresividad de consulta | Baja (sólo similitud de coseno) | Alta (operadores AND / OR / NOT) |
| Ranking | Sí | Sí |
| Coincidencia exacta soportada | No | Sí (límite del modelo) |
| Interpretabilidad | Media | Alta |

---

## 3. Arquitectura del Sistema

```
eserrei/
├── crawler/            # Adquisición (Letterboxd, IMDb)
│   ├── __init__.py
│   └── scraper.py      # LetterboxdScraper con validación robots.txt
│
├── indexer/            # Indexación (Índice Invertido + normalización NLTK)
│   ├── __init__.py
│   └── inverted_index.py
│
├── database/           # Almacenamiento (Corte 2+)
│   └── __init__.py
│
├── api/                # Recuperador / RAG (FastAPI)
│   ├── __init__.py
│   └── main.py
│
├── Dockerfile          # Imagen multietapa Python 3.11-slim
├── requirements.txt
├── .gitignore
└── README.md
```

### 3.1 Pipeline de Procesamiento (Corte 1)

```
URL Letterboxd
     ↓  [LetterboxdScraper — robots.txt check]
Film Dict {title, year, synopsis, reviews}
     ↓  [InvertedIndex.add_film()]
     ↓  [_tokenize: lower → word_tokenize → stop-words → SnowballStemmer]
Posting List: término → [(doc_id, tf), ...]
```

---

## 4. Instalación y Uso

### 4.1 Entorno local (Python 3.11+)

```bash
# Clonar el repositorio
git clone https://github.com/sri-2025/oscar-insight.git
cd oscar-insight

# Crear entorno virtual e instalar dependencias
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

### 4.2 Despliegue con Docker

```bash
# Construir imagen multietapa (incluye descarga de corpora NLTK)
docker build -t oscar-insight:0.1 .

# Ejecutar el servicio
docker run -p 8000:8000 oscar-insight:0.1
```

### 4.3 Uso del Crawler

```python
from crawler import LetterboxdScraper

scraper = LetterboxdScraper()
film = scraper.scrape_film("https://letterboxd.com/film/oppenheimer-2023/")
# → {"title": "Oppenheimer", "year": "2023", "synopsis": "...", "reviews": [...]}
```

### 4.4 Uso del Índice Invertido

```python
from indexer import InvertedIndex

idx = InvertedIndex()
idx.add_film(0, film)

print(idx.get_postings("oscar"))    # [(0, 2)]
print(idx)                          # InvertedIndex(docs=1, terms=47, lang='english')
```

### 4.5 API REST

```bash
# Health check
curl http://localhost:8000/

# Búsqueda (Corte 2)
curl -X POST http://localhost:8000/search \
     -H "Content-Type: application/json" \
     -d '{"query": "Best Picture 2024", "top_k": 5}'
```

Documentación interactiva: `http://localhost:8000/docs`

---

## 5. Control de Versiones

El proyecto sigue el flujo **Git Flow** simplificado:

| Rama | Propósito |
|---|---|
| `main` | Entregas estables (un commit por Corte) |
| `dev` | Integración continua |
| `feature/*` | Desarrollo de módulos individuales |

```bash
git init
git add .
git commit -m "feat(corte-1): scaffold inicial — crawler, indexer, api skeleton"
```

---

## 6. Estado del Proyecto

| Corte | Módulo | Estado |
|---|---|---|
| 1 | Adquisición (`crawler/`) | ✅ Implementado |
| 1 | Indexación (`indexer/`) | ✅ Implementado |
| 2 | Motor EBM (`api/search`) | 🔲 Pendiente |
| 2 | Almacenamiento (`database/`) | 🔲 Pendiente |
| 3 | RAG + Interfaz | 🔲 Pendiente |

---

## 7. Referencias Bibliográficas

1. Baeza-Yates, R., & Ribeiro-Neto, B. (2011). *Modern Information Retrieval: The Concepts and Technology behind Search* (2nd ed.). Addison-Wesley.
2. Salton, G., Fox, E. A., & Wu, H. (1983). Extended Boolean information retrieval. *Communications of the ACM*, 26(11), 1022–1036. https://doi.org/10.1145/182.358466
3. Bird, S., Klein, E., & Loper, E. (2009). *Natural Language Processing with Python*. O'Reilly Media.
4. Richardson, L. (2007). *Beautiful Soup Documentation*. https://www.crummy.com/software/BeautifulSoup/
5. The Web Robots Pages. (2024). *robots.txt standard*. https://www.robotstxt.org/

---

*Documento generado para el Proyecto Integrador SRI 2025-2026. Formato adaptado de la plantilla LNCS (Lecture Notes in Computer Science), Springer.*
