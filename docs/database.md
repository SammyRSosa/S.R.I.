Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./database/store.py#1-1), lines 1 to 50

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./database/store.py#51-51), lines 51 to 100

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./database/store.py#101-101), lines 101 to 150

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./database/store.py#151-151), lines 151 to 200

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./database/store.py#201-201), lines 201 to 250

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./database/checkpoint.py#1-1), lines 1 to 50

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./database/checkpoint.py#51-51), lines 51 to 100

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./database/checkpoint.py#101-101), lines 101 to 150

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./database/vector_store.py#1-1), lines 1 to 50

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./database/vector_store.py#51-51), lines 51 to 100

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./database/vector_store.py#101-101), lines 101 to 127

### Detalles de la Fase de Almacenamiento en "Oscar Insight Search"

Hola! Te explico con detalles la fase de almacenamiento, que es crucial para persistir datos y permitir búsquedas eficientes. Incluye el almacenamiento de documentos, el sistema de checkpoint, VectorStore y embeddings. Todo se basa en archivos JSON simples y librerías especializadas como FAISS.

#### 1. **Fase de Almacenamiento General**
La fase de almacenamiento persiste el corpus de películas y el índice invertido en disco, usando JSON para simplicidad y portabilidad (sin bases de datos externas). Se ejecuta durante la población (populate_tmdb.py) y al guardar la app.

- **Archivos Generados**:
  - documents.json: Corpus de películas (~1,623 docs).
  - index.json: Índice invertido serializado.
  - ebm_weights.json: Pesos TF-IDF para el EBM.
  - faiss_index.bin: Índice vectorial (FAISS).
  - vector_mapping.json: Mapeo de vectores a documentos.

- **¿Qué Parte del Código Almacena los Documentos?**
  - **Clase `DocumentStore`** (store.py): Es el núcleo del almacenamiento.
    - **Método `add_film(film_data)`**: Añade películas con deduplicación (por `tmdb_id` o `source_url`). Retorna `doc_id` (ID único).
    - **Método `save()`**: Persiste documentos en `documents.json` con metadata (_meta incluye next_id, total, schema v2).
    - **Método `save_index(index)`**: Guarda el índice invertido en `index.json`.
    - **Método `load()`**: Carga documentos al iniciar la app.
  - **Esquema de Documento (v2)**: `{title, year, metadata: {...}, rich_text: str, reviews_count: int}`. Compatible con v1 legacy.
  - **Deduplicación**: Evita duplicados usando índices internos (`_tmdb_id_index`, `_url_index`).
  - **Dónde se Llama**: En populate_tmdb.py, después de procesar cada película: `store.add_film(film_doc)` y guardado incremental cada 50 docs.

#### 2. **¿Qué es el Checkpoint?**
El checkpoint es un sistema de persistencia de estado que permite reanudar procesos largos (como la población de 2,000 películas) sin perder progreso o duplicar datos. Es esencial para pipelines interrumpibles.

- **¿Qué Parte del Código lo Maneja?**
  - **Clase `Checkpoint`** (checkpoint.py): Gestiona estado en checkpoint.json.
    - **Estado Persistido**: `processed_ids` (set de TMDB IDs exitosos), `failed_ids` (fallidos), `last_page_popularity/quality` (páginas procesadas), `total_indexed` (docs indexados).
    - **Métodos Clave**:
      - `is_processed(tmdb_id)`: Verifica si ya se procesó (O(1) con sets).
      - `mark_done(tmdb_id)` / `mark_failed(tmdb_id)`: Marca estado.
      - `save()`: Persiste en JSON cada 25 docs o al final de página.
      - `reset()`: Borra estado para empezar desde cero.
    - **Reanudación**: Al iniciar con `--resume`, carga estado y salta IDs ya procesados.

- **Cómo se Usa en el Proyecto**:
  - En populate_tmdb.py: Antes de procesar, verifica `if ck.is_processed(tmdb_id): continue`. Después, marca como done/failed y guarda.
  - Beneficios: Maneja interrupciones (ej.: red falla), evita re-procesar películas ya indexadas, y permite reset para pruebas.

#### 3. **¿Qué es VectorStore?**
VectorStore es un módulo que gestiona la indexación y búsqueda semántica (basada en vectores/embeddings), complementando el EBM textual. Usa FAISS para búsquedas aproximadas rápidas en grandes datasets.

- **¿Qué Parte del Código lo Implementa?**
  - **Clase `VectorStore`** (vector_store.py): Envuelve FAISS y Sentence-Transformers.
    - **Atributos**: `index` (FAISS IndexFlatIP para similitud coseno), `model` (SentenceTransformer), mapeos `vector_to_doc` y `doc_to_vector`.
    - **Método `build_from_documents(documents)`**: Codifica `rich_text` de cada doc en embeddings, normaliza y añade a FAISS. Guarda en `faiss_index.bin` y `vector_mapping.json`.
    - **Método `search(query, top_k)`**: Codifica query en embedding, busca en FAISS y retorna [(doc_id, score_coseno)].
    - **Método `load()`**: Carga índice y mapeos al iniciar.

- **Cómo se Usa en el Proyecto**:
  - Inicializado en main.py: `v_store = VectorStore()`.
  - En búsquedas híbridas: Combina con EBM (60% EBM + 40% vectorial) para resultados más ricos (ej.: "películas oscuras" encuentra semánticamente similares).
  - Construcción: Después de poblar documentos, se llama `v_store.build_from_documents(store.documents)`.

#### 4. **¿Qué es un Embedding y Cómo se Utilizan?**
Un **embedding** (o "incrustación") es una representación vectorial numérica (lista de floats) de texto, que captura significado semántico. Palabras/conceptos similares tienen vectores cercanos (medido por similitud coseno).

- **¿Cómo se Generan?**
  - Usa **Sentence-Transformers** con modelo `all-MiniLM-L6-v2` (384 dimensiones, ligero y rápido).
  - Proceso: `model.encode(text)` → vector de 384 floats, normalizado (L2) para similitud coseno.

- **¿Cómo se Utilizan en el Proyecto?**
  - **Codificación de Documentos**: Cada `rich_text` se convierte en embedding y se indexa en FAISS.
  - **Búsqueda Semántica**: Query (ej.: "thriller psicológico") se codifica y busca vectores similares en FAISS, retornando docs con alta similitud coseno (0-1).
  - **Híbrido**: En main.py, combina con EBM: score_final = (ebm_score * 0.6) + (vector_score * 0.4).
  - **Ventajas**: Captura contexto (ej.: sinónimos como "cine negro" ≈ "dark cinema"), supera limitaciones textuales del EBM.
  - **Limitaciones**: Computacionalmente intensivo; se pre-calcula y guarda.

En resumen, el almacenamiento asegura persistencia y eficiencia; checkpoint permite reanudación; VectorStore añade búsqueda semántica con embeddings para queries naturales. Si quieres ver ejemplos de código o ejecutar una búsqueda, ¡dímelo! 😊