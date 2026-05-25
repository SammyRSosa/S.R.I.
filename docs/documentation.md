Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I)

Searched for files matching `**/README.md`, 1 match

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./README.md#1-1), lines 1 to 50

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./README.md#51-51), lines 51 to 100

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./README.md#101-101), lines 101 to 150

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./README.md#151-151), lines 151 to 200

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./api/main.py#1-1), lines 1 to 50

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./api/main.py#51-51), lines 51 to 100

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./api/main.py#101-101), lines 101 to 150

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./scripts/populate_tmdb.py#1-1), lines 1 to 50

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./scripts/populate_tmdb.py#51-51), lines 51 to 100

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./scripts/populate_tmdb.py#101-101), lines 101 to 150

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./scripts/populate_tmdb.py#151-151), lines 151 to 200

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./scripts/populate_tmdb.py#201-201), lines 201 to 250

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./scripts/populate_tmdb.py#251-251), lines 251 to 350

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./scripts/populate_tmdb.py#351-351), lines 351 to 450

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./scripts/populate_tmdb.py#451-451), lines 451 to 500

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./scripts/query.py#1-1), lines 1 to 50

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./scripts/query.py#51-51), lines 51 to 93

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./scripts/enrich_reviews.py#1-1), lines 1 to 30

### Flujo Completo de Funcionamiento de la Aplicación "Oscar Insight Search"

Hola! Te explico paso a paso el flujo completo de funcionamiento de esta aplicación, que es un **Sistema de Recuperación de Información (SRI)** enfocado en películas y premios Oscar. Está basado en el **Modelo Booleano Extendido (EBM)** combinado con búsqueda semántica vectorial. Usaré un lenguaje simple y estructurado para que lo vayas comprendiendo. El sistema se divide en módulos principales: **crawler** (adquisición), **indexer** (indexación), **database** (almacenamiento), **api** (recuperación) y **scripts** (orquestación).

#### 1. **Fase de Adquisición de Datos (Crawling)**
   - **Objetivo**: Recopilar datos de películas desde fuentes externas para crear un corpus (conjunto de documentos) rico en texto.
   - **Estrategias de Rastreo**:
     - **Estrategia A (API TMDB + Letterboxd Scraper)**: Consulta paginada y enriquecimiento ad-hoc para el corpus inicial de 1,650 películas.
     - **Estrategia B (Link-Traversal Focused Crawler Puro - Metacritic)**: Rastreo hipertextual autónomo sobre el grafo HTML de Metacritic (exigido por la cátedra) para la expansión orgánica del corpus.
   - **El Traversal Spider (`MetacriticTraversalSpider`)**:
     - **Seed URL (Semilla)**: Directorio de películas `https://www.metacritic.com/browse/movie/`.
     - **Frontera de Rastreo (Queue)**: BFS puro utilizando `collections.deque`.
     - **Evitación de Ciclos**: Conjunto (`set`) en memoria para registrar URLs ya visitadas.
     - **Capa Ética con Caché TTL (Robots.txt)**: Verificación dinámica de directivas mediante `urllib.robotparser`. Para evitar peticiones repetitivas a Metacritic, se implementó una **caché en disco con TTL de 24 horas** (`data/robots_cache.json`). Si la caché es válida, se parsea en memoria al instante sin tocar la red, ahorrando ancho de banda y protegiendo el pipeline contra cuellos de botella de red durante evaluaciones rápidas.
     - **Bypass de Firewalls (WAF Bypass)**: Uso de `curl_cffi.requests.Session` impersonando a Chrome 124 para descargar el robots.txt y las páginas, neutralizando bloqueos de Cloudflare por TLS Fingerprinting.
     - **Focused Crawling (Filtros Regex)**: Exclusividad estricta para enlaces de paginación del índice (`/browse/movie/?page=X`), fichas de detalles (`/movie/[slug]/`) y páginas de reseñas de usuarios (`/movie/[slug]/user-reviews/`).
     - **Ingestión e Indexación Atómica**: Al descubrir un film, se extraen sus metadatos principales (NEXT_DATA JSON / DOM fallback) y críticas, se valida contra el `DocumentStore` (evitando duplicidad por slug), y si es nuevo se guarda y se disparan de forma incremental `InvertedIndex`, `EBM Weights` y `VectorStore (FAISS)`.
   - **Herramientas**: `tmdb_client.py` (API TMDB), `scraper.py` (reviews Letterboxd), y `metacritic_spider.py` (Link-Traversal focused spider).
   - **Resultado**: Crecimiento orgánico controlado del corpus mediante autoevaluaciones del grafo de la Web.

#### 2. **Fase de Indexación**
   - **Objetivo**: Crear un índice invertido para búsquedas rápidas, basado en el texto "rich_text" de cada documento.
   - **Modelo de Recuperación**: Booleano Extendido (EBM), que extiende el modelo booleano clásico ponderando términos con tf-idf y calculando similitud con distancias euclidianas (produce scores continuos en [0,1] en lugar de solo sí/no).
   - **Proceso de tokenización**:
     - Texto en minúsculas.
     - Tokenización con NLTK (word_tokenize).
     - Eliminación de stop-words (palabras comunes como "the", "and").
     - Stemming con Snowball (reduce palabras a raíces, ej.: "running" → "run").
   - **Estructura del índice**: Un diccionario donde cada término apunta a una lista de postings: [(doc_id, tf), ...] donde tf es la frecuencia del término en el documento.
   - **Herramientas**: inverted_index.py (índice invertido) y ebm.py (motor EBM para búsquedas).
   - **Resultado**: Archivo index.json con el índice serializado, y un vocabulario de ~16,000 términos únicos.

#### 3. **Fase de Almacenamiento (Database)**
   - **Objetivo**: Persistir los documentos y el índice en disco para acceso rápido.
   - **Componentes**:
     - **DocumentStore**: Almacena documentos en documents.json (JSON con ~1,650 películas).
     - **Checkpoint**: Sistema para reanudar procesos interrumpidos (guarda estado en checkpoint.json).
     - **VectorStore**: Capa semántica de alta fidelidad basada en embeddings vectoriales generados por `sentence-transformers` e indexación de vecinos más cercanos vía FAISS (`faiss.IndexFlatIP`). Soporta **indexación incremental real** a través de `add_documents_incremental`. En lugar de recalcular el espacio vectorial completo de ~1,650 películas en disco (que es costoso en CPU/I/O), el sistema detecta de forma dinámica los nuevos documentos del crawler, computa exclusivamente sus representaciones neurales, las inyecta directamente al índice cargado mediante `index.add()` y guarda la nueva estructura. Cuenta con fallback automático completo a reconstrucción total en caso de corrupción o ausencia del archivo binario.
   - **Herramientas**: store.py, checkpoint.py, vector_store.py.
   - **Resultado**: Archivos JSON persistentes que se cargan en memoria al iniciar la aplicación.

#### 4. **Fase de Recuperación y Búsqueda (API)**
   - **Objetivo**: Permitir consultas de usuarios y devolver resultados relevantes.
   - **Motores de búsqueda**:
     - **EBM (Booleano Extendido)**: Para consultas textuales precisas (ej.: "dark cinematography"). Calcula scores basados en tf-idf y operaciones AND/OR.
     - **Vectorial (Semántica)**: Para consultas en lenguaje natural (ej.: "películas tristes sobre pérdida"). Usa embeddings para encontrar similitud semántica.
     - **Híbrido**: Combina ambos (60% EBM + 40% vectorial por defecto) para mejores resultados.
   - **API REST**: Construida con FastAPI.
     - Endpoint principal: `POST /search` (acepta query, top_k, p-norma, híbrido sí/no).
     - Devuelve resultados con score combinado, título, año, snippet (fragmento relevante del texto).
   - **Herramientas**: main.py (servidor FastAPI).
   - **Resultado**: Respuestas JSON con documentos rankeados por relevancia.

#### 5. **Scripts de Orquestación y Utilidades**
   - **Población inicial**: populate_tmdb.py — Orquesta todo el flujo de adquisición e indexación. Puede reanudarse si se interrumpe, filtrar por calidad, y guardar incrementalmente.
   - **Enriquecimiento**: enrich_reviews.py — Añade reseñas a documentos ya indexados (útil si se poblaron sin reseñas inicialmente).
   - **Consulta CLI**: query.py — Permite buscar desde terminal sin API (útil para pruebas).
   - **Otros**: Scripts de prueba en scripts para validar parsers, APIs, etc.

#### Flujo General de Ejecución
1. **Setup inicial**: Instalar dependencias (`pip install -r requirements.txt`), obtener API key de TMDB.
2. **Población**: Ejecutar `python populate_tmdb.py --api-key TU_CLAVE` para adquirir ~2,000 películas y crear índice.
3. **Enriquecimiento opcional**: Si no se incluyeron reseñas, ejecutar `python scripts/enrich_reviews.py`.
4. **Indexación vectorial**: El VectorStore se inicializa automáticamente al cargar documentos.
5. **Levantar API**: Ejecutar `uvicorn api.main:app --reload` (o similar) para servir búsquedas.
6. **Búsqueda**: Usuarios envían queries (ej.: "psychological thriller nolan") y reciben resultados híbridos.

#### 6. **Corte 2: Integración Avanzada (RAG y Web Search)**
   - **Módulo RAG**: Extiende la búsqueda híbrida permitiendo respuestas conversacionales. Utiliza el contexto recuperado para alimentar un LLM (Llama 3 vía Groq).
   - **Búsqueda Web Fallback**: Si la base de datos local no contiene suficiente información, el sistema consulta automáticamente a la web (DuckDuckGo), procesa los resultados e intenta responder con datos frescos.
   - **Posicionamiento**: Se ha refinado el ranking integrando la popularidad de TMDB y la frescura (año) en el score final.

#### 7. **Consideraciones Técnicas y Dependencias**
- **LLM**: Groq (Llama 3) para generación RAG.
- **Web Search**: DuckDuckGo Search API.
- **Idioma**: Soporte para consultas en Español/Inglés.

#### 8. **Despliegue y Reproducibilidad con Docker**
El sistema está completamente dockerizado para garantizar la máxima reproducibilidad académica y facilitar su ejecución en máquinas externas sin configuraciones previas de Python o dependencias nativas (como FAISS).

- **Dockerfile de Producción Multietapa**:
  - **Etapa 1 (`builder`)**: Usa `python:3.11-slim` para instalar librerías compilando librerías de C (como `lxml`) e instala las dependencias de `requirements.txt`. Además, descarga preventivamente todos los datasets y tokenizadores de `NLTK` (`punkt`, `punkt_tab`, `stopwords`) en `/install/nltk_data` para evitar llamadas de red lentas o fallos en caliente.
  - **Etapa 2 (`runtime`)**: Genera la imagen final ultraligera copiando únicamente los paquetes de Python ya instalados y los recursos de NLTK de la etapa previa, exponiendo el puerto `8000`.

- **Pasos para Ejecutar con Docker**:
  1. **Construir la imagen local**:
     ```bash
     docker build -t oscar-insight:latest .
     ```
  2. **Ejecutar el contenedor con volumen de persistencia y variables de entorno**:
     - *Linux / macOS*:
       ```bash
       docker run -d -p 8000:8000 --env-file .env -v $(pwd)/data:/app/data --name oscar-insight-app oscar-insight:latest
       ```
     - *Windows (PowerShell)*:
       ```powershell
       docker run -d -p 8000:8000 --env-file .env -v ${PWD}/data:/app/data --name oscar-insight-app oscar-insight:latest
       ```
  3. **Acceso al sistema**:
     Abra `http://localhost:8000/` en el navegador para interactuar con la interfaz visual.
