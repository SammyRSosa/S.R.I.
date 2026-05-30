# 🎬 Oscar Insight Search
## Sistema de Recuperación de Información Híbrido — Cine y Premios Oscar

> **Curso:** SRI 2025-2026 | **Corte Final: Entrega y Defensa Académica**
> **Integrantes:** Sammy R. Sosa, Daniela Guerrero y Rubén Martínez (Universidad de La Habana)
> **Tecnologías Core**: FastAPI, FAISS, Sentence-Transformers (multilingüe), EBM ($p$-norma), Link-Traversal Focused Crawler BFS, Hot-Indexing en tiempo real, NLTK, curl_cffi.

---

## 1. Resumen del Proyecto

*Oscar Insight Search* es un motor de búsqueda avanzado diseñado para el dominio cinematográfico, enfocado en las películas nominadas y ganadoras de los Premios Oscar. A diferencia de los buscadores tradicionales, el sistema implementa una **arquitectura de recuperación híbrida en dos niveles** y un sistema de enriquecimiento dinámico:

1.  **Modelo Booleano Extendido (EBM)**: Implementación rigurosa de la $p$-norma ($p = 2.0$, euclidiana) sobre un **índice invertido léxico** desarrollado desde cero con procesamiento de lenguaje natural (tokenización avanzada, stopwords bilingües y Snowball Stemmer). Permite consultas lógicas (AND/OR/NOT) "suaves" con ranking continuo en el rango $[0, 1]$.
2.  **Búsqueda Semántica Vectorial**: Conversión de textos en embeddings densos de 384 dimensiones mediante el modelo multilingüe de bi-encoders `paraphrase-multilingual-MiniLM-L12-v2`, indexados geométricamente con **FAISS** mediante similitud de coseno (producto interno con normalización $L_2$). Permite consultas conceptuales en español cruzando barreras idiomáticas sobre el corpus en inglés.
3.  **Link-Traversal Focused Crawler**: Un rastreador autónomo por grafos hipertextuales basado en BFS, clasificación rígida de 5 tipos de nodos (Movie, Review, Person, Genre, Index), caché de `robots.txt` física con TTL (24h) e indexación por lotes (*Batch Processing*).
4.  **Búsqueda Fallback con Hot-Indexing Real**: Detección inteligente de consultas insuficientes (umbral cuantitativo de $<3$ documentos o cualitativo de score $<0.15$) que dispara la recolección web instantánea, segmentación sliding window (600/120), inyección incremental en caliente a FAISS (`index.add()`) e indexación léxica con caché de frecuencias máximas (`_max_tf_per_doc`) para una velocidad inmediata en visitas posteriores.

El corpus local de producción contiene **1,652 películas** enriquecidas con metadatos estructurados de TMDB y aproximadamente **4,800 reseñas de usuarios** detalladas de Metacritic.

---

## 2. Estructura del Proyecto

El sistema se organiza de forma modular y limpia:

*   `crawler/`: Contiene el scraper TLS sigiloso (`scraper.py`), el focused crawler por grafos BFS (`metacritic_spider.py`) y el módulo de fallback con indexación en caliente (`web_search.py`).
*   `indexer/`: Pipeline de PLN (`inverted_index.py`), lógica matemática de la $p$-norma de similitud (`ebm.py`) y recomendador híbrido de contenido (`recommender.py`).
*   `database/`: Gestión documental persistente (`store.py`) e índice vectorial FAISS (`vector_store.py`).
*   `api/`: Servidor FastAPI asíncrono (`main.py`), respuestas del módulo conversacional RAG Llama3 (`rag.py`) y la interfaz de usuario de página única (`templates/index.html`).
*   `scripts/`: Utilidades ejecutables para arranque en frío, evaluación formal y ejecución del crawler.

---

## 3. Instalación, Arranque y Uso (Guía para el Profesor)

### 3.1 Requisitos Previos
- Python 3.11+
- Clave de API de TMDB (opcional para recolección inicial, provista en configuración).
- Clave de API de Groq (para habilitar el módulo RAG conversacional; el sistema degrada con elegancia a búsqueda tradicional si no está presente).

### 3.2 Configuración del Entorno
Clone el repositorio, ingrese a la carpeta e instale las dependencias en su entorno virtual:

```bash
# 1. Crear e iniciar entorno virtual (Recomendado)
python -m venv .venv
# En Windows (PowerShell):
.venv\Scripts\Activate.ps1
# En Linux/macOS:
source .venv/bin/activate

# 2. Instalar dependencias requeridas
pip install -r requirements.txt
```

Cree un archivo `.env` en la raíz del proyecto basado en `.env.example` o exporte sus claves de API en la terminal:
```bash
# Windows (PowerShell):
$env:TMDB_API_KEY = "tu_clave_de_tmdb"
$env:GROQ_API_KEY = "tu_clave_de_groq"
```

---

### 3.3 Paso 1: Re-Indexación y Arranque en Frío (Cold Start)
Para cumplir estrictamente las directrices de la cátedra de no depender de índices pre-existentes, el sistema incluye un orquestador que elimina físicamente los archivos previos y genera el índice invertido, pesos TF-IDF y embeddings de FAISS locales desde cero:

```bash
python scripts/reindex_all.py
```
*Tardará apenas unos segundos en CPU para indexar y codificar semánticamente las 1,652 películas del corpus.*

---

### 3.4 Paso 2: Ejecución de la API y UI
Una vez generados los índices locales, levante el servidor web de desarrollo:

```bash
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Abra su navegador web y acceda a:
- **Interfaz Visual Interactiva (Netflix UI-Style)**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Documentación Interactiva Swagger de la API**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Verificación de Salud de Índices (Healthcheck)**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## 4. Pruebas y Capacidades Avanzadas para Evaluar

El profesor puede validar de forma interactiva las siguientes 4 capacidades exclusivas de nuestra implementación:

### A. Prueba del Link-Traversal Focused Crawler BFS (Módulo Autónomo)
Para demostrar el rastreo hipertextual por grafos BFS con cumplimiento estricto de robots.txt, caché persistente TTL de 24 horas e indexación por lotes, ejecute el spider en la terminal:
```bash
python scripts/run_traversal_crawler.py --limit 3 --reviews-limit 2
```
*Los logs ilustrarán la descarga y validación de `data/robots_cache.json`, el encolamiento BFS por tipologías de nodos y la indexación en un lote atómico al finalizar.*

### B. Prueba de Evaluación Cuantitativa Formal (Benchmark Académico)
Para medir de forma objetiva la calidad del motor frente al Ground Truth experto, ejecute el script evaluador:
```bash
python scripts/evaluate.py
```
*Imprimirá en la consola las métricas académicas de **Precision@5, Recall@5, F1-Score, MRR y NDCG@5** calculadas para el ranking híbrido.*

### C. Prueba de Búsqueda Semántica Multilingüe y RAG
1. Ingrese a la UI web y realice la consulta conceptual en español: `"bomba atomica Christopher Nolan"` o `"pelicula sobre los sueños e inception"`.
2. Verifique que el primer resultado es *Oppenheimer* u *Inception* de forma impecable (gracias al alineamiento geométrico multilingüe de embeddings).
3. Presione el botón **"Respuesta Inteligente"** para ver al módulo RAG conversacional (Llama3-8b) redactar en vivo una síntesis libre de alucinaciones con citas y procedencias bibliográficas en base a un prompt con temperatura acotada a `0.2`.

### D. Prueba de Fallback Web con Indexación Incremental Real en Caliente
1. En la UI web, ingrese una película completamente ausente de la base local, por ejemplo: `"Wicked movie musical 2024 reviews"`.
2. Al presionar Buscar, observe la consola de FastAPI: el sistema detecta que la base local carece de cobertura ($<3$ resultados), activa DuckDuckGo, descarga concurrentemente las páginas verificando sus robots.txt individuales, aplica sliding-window (600/120), e inyecta incrementalmente en caliente los nuevos embeddings en FAISS (`index.add()`) e indexa en memoria/disco con caché de frecuencias máximas.
3. El frontend mostrará las tarjetas externas con una insignia distintiva de **"Fuente Web"** con su enlace.
4. **Vuelva a realizar la misma búsqueda**: ahora responderá de forma **instantánea** (apenas **0.037 segundos**) al estar indexada por completo en la base de datos local en caliente, reduciendo la latencia un 99.8%.

---

## 5. Despliegue en Producción con Docker

El proyecto incluye una configuración multi-etapa de Docker sumamente optimizada:

1. **Construir la imagen de Docker**:
   ```bash
   docker build -t oscar-insight:latest .
   ```

2. **Ejecutar el contenedor con variables y persistencia**:
   ```powershell
   # En Windows (PowerShell):
   docker run -d `
     -p 8000:8000 `
     -e GROQ_API_KEY="tu_clave_de_groq" `
     -e TMDB_API_KEY="tu_clave_de_tmdb" `
     -v ${PWD}/data:/app/data `
     --name oscar-insight-app `
     oscar-insight:latest
   ```
*La carpeta `data` se monta como volumen externo garantizando que todas las indexaciones en caliente y ejecuciones de crawler se mantengan persistentes de forma física.*

---

## 6. Referencias Bibliográficas

1. Salton, G., Fox, E.~A., Wu, H.: Extended Boolean information retrieval. *Communications of the ACM*, 26(11), 1022--1036 (1983).
2. Baeza-Yates, R., Ribeiro-Neto, B.: *Modern Information Retrieval: The Concepts and Technology behind Search*, 2nd edn. Addison-Wesley Professional (2011).
3. Reimers, N., Gurevych, I.: Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks. In: *Proceedings of EMNLP-IJCNLP 2019*, Hong Kong (2019).
4. Johnson, J., Douze, M., Jegou, H.: Billion-scale similarity search with GPUs. *IEEE Transactions on Big Data*, 7(3), 535--547 (2019).
5. Lewis, P., et~al.: Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. In: *Advances in Neural Information Processing Systems (NeurIPS) 2020* (2020).
