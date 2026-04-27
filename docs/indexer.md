Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./indexer/inverted_index.py#1-1), lines 1 to 50

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./indexer/inverted_index.py#51-51), lines 51 to 100

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./indexer/inverted_index.py#101-101), lines 101 to 150

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./indexer/inverted_index.py#151-151), lines 151 to 200

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./indexer/inverted_index.py#201-201), lines 201 to 250

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./indexer/ebm.py#1-1), lines 1 to 50

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./indexer/ebm.py#51-51), lines 51 to 100

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./indexer/ebm.py#101-101), lines 101 to 139

### Detalles de la Fase de Indexación en "Oscar Insight Search"

Hola! Te explico con detalles la fase de indexación, que es el corazón del sistema de recuperación de información. Esta fase transforma el texto crudo de las películas (obtenido del crawler) en una estructura de datos eficiente para búsquedas rápidas. Usaré el Modelo Booleano Extendido (EBM) como base, con explicaciones paso a paso, fórmulas y ejemplos. Todo se basa en el código de inverted_index.py y ebm.py.

#### 1. **¿Cómo Funciona la Fase de Indexación?**
La indexación crea un **índice invertido**, una estructura de datos que mapea términos (palabras normalizadas) a listas de documentos donde aparecen, junto con su frecuencia. Esto permite búsquedas rápidas sin escanear todo el corpus cada vez.

- **Estructura del Índice**:
  - `self.index`: Un diccionario donde cada clave es un término normalizado (ej.: "oppenheim" para "Oppenheimer").
  - Valor: Lista de tuplas `(doc_id, tf)`, donde `doc_id` es el ID del documento y `tf` (term frequency) es la frecuencia del término en ese documento.
  - Ejemplo: `"award": [(0, 1), (5, 2)]` significa que "award" aparece 1 vez en el doc 0 y 2 veces en el doc 5.

- **Proceso General**:
  1. **Entrada**: Documentos de películas con "rich_text" (título + sinopsis + reseñas + metadatos).
  2. **Tokenización**: Convierte el texto en tokens normalizados (ver sección 2).
  3. **Construcción**: Para cada documento, cuenta frecuencias de términos y actualiza el índice.
  4. **Almacenamiento**: Se guarda en index.json como JSON serializado.
  5. **Uso en Búsqueda**: El EBM usa este índice para calcular similitudes.

- **Dónde se Hace**: En `InvertedIndex.add_document()` o `add_film()`. Se ejecuta durante la población (populate_tmdb.py) y se reconstruye al cargar la app.
- **Eficiencia**: El índice se construye incrementalmente; para grandes corpus, se guarda cada 50 documentos para evitar pérdida de datos.

#### 2. **¿Cómo y Dónde se Hace el Proceso de Tokenización?**
La tokenización normaliza el texto para reducir variaciones (ej.: "running" → "run") y eliminar ruido, asegurando búsquedas consistentes. Se hace en el método `_tokenize()` de `InvertedIndex`, llamado desde `add_document()`.

- **Dónde**: En inverted_index.py, método `_tokenize(text: str) -> list[str]`.
- **Pipeline de Normalización (5 pasos)**:
  1. **Minúsculas**: Todo el texto se convierte a lowercase (ej.: "Oppenheimer" → "oppenheimer").
  2. **Tokenización Lingüística**: Usa `nltk.word_tokenize()` para dividir en tokens basados en reglas del idioma (ej.: "It's a great film!" → ["it", "'s", "a", "great", "film", "!"]).
  3. **Filtro Alfanumérico**: Elimina tokens sin letras/números (ej.: "!" se descarta).
  4. **Eliminación de Stop-Words**: Remueve palabras comunes que no aportan significado (ej.: "the", "and", "a"). Usa listas de NLTK para inglés y español (combinadas para corpus bilingüe).
  5. **Stemming**: Reduce palabras a raíces con `SnowballStemmer` (ej.: "running" → "run", "films" → "film"). Idioma por defecto: inglés.

- **Ejemplo de Tokenización**:
  - Texto: "Oppenheimer won the Best Director Oscar in 2024."
  - Paso 1: "oppenheimer won the best director oscar in 2024."
  - Paso 2: ["oppenheimer", "won", "the", "best", "director", "oscar", "in", "2024", "."]
  - Paso 3: ["oppenheimer", "won", "the", "best", "director", "oscar", "in", "2024"]
  - Paso 4: ["oppenheimer", "won", "best", "director", "oscar", "2024"] (elimina "the", "in")
  - Paso 5: ["oppenheim", "won", "best", "director", "oscar", "2024"] (stemming)

- **Detalles Relevantes**:
  - **Idioma**: Configurable (inglés por defecto); soporta español.
  - **Eficiencia**: NLTK se descarga automáticamente si falta.
  - **Robustez**: Maneja texto vacío o no-string; logs warnings si no genera tokens.
  - **Consistencia**: La misma pipeline se aplica a consultas en búsquedas.

#### 3. **¿Cómo se Calculan las Ponderaciones en el Modelo Booleano Extendido (EBM)?**
El EBM extiende el modelo booleano clásico (solo sí/no) con ponderaciones tf-idf y distancias euclidianas para scores continuos [0,1]. Se calcula en `ExtendedBooleanModel` (ebm.py).

- **Fórmulas Clave** (basadas en Baeza-Yates & Ribeiro-Neto):
  - **Ponderación TF-IDF Normalizada** (para cada término `i` en documento `j`):
    - `tf_{i,j}`: Frecuencia del término en el documento.
    - `max_tf_j`: Máxima frecuencia en el documento (normalización por longitud).
    - `idf_i`: Inverso de frecuencia de documento, normalizado: `idf_i = log(N / n_i) / log(N)`, donde `N` es total de documentos y `n_i` es docs con el término.
    - `w_{i,j} = (tf_{i,j} / max_tf_j) * idf_i` (rango [0,1]).
  - **Similitud para Consultas**:
    - Para consulta `q` con términos `t1, t2, ..., tm`:
      - **OR**: `sim_OR(d, q) = (∑ w_{i,j}^p / m)^{1/p}` (p-norm euclidiana).
      - **AND**: `sim_AND(d, q) = 1 - (∑ (1 - w_{i,j})^p / m)^{1/p}` (distancia a la perfección).
    - `p` es el exponente (default 2.0, como distancia euclidiana).

- **Dónde se Calcula**:
  - **Pre-cálculo**: En `build_weights()` (llamado una vez al inicializar). Construye `self.weights: {término: {doc_id: w_ij}}` y guarda en ebm_weights.json.
  - **En Búsqueda**: En `search(query, op="OR")`, calcula similitudes para documentos candidatos (aquellos con al menos un término de la query).

- **Ejemplo de Cálculo**:
  - Supongamos N=100 docs, término "oscar" en n_i=10 docs.
  - idf = log(100/10) / log(100) ≈ 0.5.
  - En doc j con tf=3, max_tf=5: w = (3/5) * 0.5 = 0.3.
  - Para query "oscar award" (OR, p=2): Si doc tiene w_oscar=0.3, w_award=0.0, sim = ((0.3^2 + 0.0^2)/2)^{1/2} ≈ 0.212.

- **Detalles Relevantes**:
  - **Normalización**: IDF dividido por log(N) para rango [0,1]; evita pesos extremos.
  - **Operadores**: Soporta OR/AND; por defecto OR para lenguaje natural.
  - **Eficiencia**: Pesos pre-calculados; búsquedas solo en docs candidatos.
  - **Híbrido**: En la API, combina EBM con vectorial (FAISS) para mejores resultados.

#### Otros Detalles Relevantes
- **Reconstrucción del Índice**: Al iniciar la app, se reindexa desde `documents.json` si no hay índice guardado.
- **Vocabulario**: ~16,000 términos únicos; se expone en la API (`vocab`).
- **Checkpointing**: En población, guarda estado para reanudar.
- **Limitaciones**: No maneja sinónimos (eso vendría en Corte 2 con embeddings); stemming puede ser agresivo.
- **Pruebas**: Scripts como `test_search.py` validan el índice.

Si quieres ver código específico, ejecutar una búsqueda de prueba o profundizar en una fórmula, ¡dímelo! 😊