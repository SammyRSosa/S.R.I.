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
   - **Fuentes principales**:
     - **TMDB (The Movie Database)**: API gratuita que proporciona metadatos estructurados como título, año, director, reparto, géneros, presupuesto, ingresos, calificaciones, etc. Se usa una estrategia híbrida:
       - **Estrategia A**: Películas populares (ordenadas por `popularity.desc`).
       - **Estrategia B**: Películas de calidad (ordenadas por `vote_average.desc` con al menos 500 votos).
     - **Letterboxd**: Sitio web de reseñas de usuarios. Se scrapea hasta 15 reseñas por película para obtener texto en lenguaje natural (críticas subjetivas).
   - **Proceso**:
     - Se obtienen listas de películas básicas de TMDB (páginas de 20 películas cada una).
     - Para cada película, se filtra por calidad (ej.: al menos 50 votos, sinopsis no vacía, idioma inglés).
     - Se obtienen detalles completos de TMDB (director, cast, etc.).
     - Se scrapean reseñas de Letterboxd usando el título, año e IMDb ID.
     - Se construye un "rich_text" concatenando: título, tagline, géneros, director, cast, sinopsis y reseñas.
   - **Herramientas**: tmdb_client.py (cliente TMDB) y scraper.py (scraper Letterboxd).
   - **Resultado**: Documentos JSON con schema v2 (título, año, metadata, rich_text, número de reseñas).

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
     - **DocumentStore**: Almacena documentos en documents.json (JSON con ~1,623 películas).
     - **Checkpoint**: Sistema para reanudar procesos interrumpidos (guarda estado en checkpoint.json).
     - **VectorStore**: Para búsqueda semántica, usa embeddings (representaciones vectoriales) con FAISS (librería de búsqueda aproximada). Convierte el rich_text en vectores y permite búsquedas por similitud coseno.
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

#### Consideraciones Técnicas
- **Idioma y dominio**: Solo películas en inglés de 1990 en adelante, enfocadas en Oscars.
- **Rendimiento**: Checkpointing para procesos largos; guardado incremental cada 50 docs.
- **Calidad**: Filtros estrictos para asegurar texto rico (sinopsis + reseñas).
- **Escalabilidad**: Usa FAISS para búsquedas vectoriales eficientes en grandes datasets.

Si quieres profundizar en alguna parte (ej.: cómo funciona exactamente el EBM o ver código de un módulo específico), ¡dímelo! También puedo ejecutar pruebas o mostrar ejemplos de consultas. 😊