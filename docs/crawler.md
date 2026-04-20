Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./crawler/tmdb_client.py#1-1), lines 1 to 50

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./crawler/tmdb_client.py#51-51), lines 51 to 100

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./crawler/tmdb_client.py#101-101), lines 101 to 150

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./crawler/tmdb_client.py#151-151), lines 151 to 200

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./crawler/tmdb_client.py#201-201), lines 201 to 250

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./crawler/scraper.py#1-1), lines 1 to 50

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./crawler/scraper.py#51-51), lines 51 to 100

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./crawler/scraper.py#101-101), lines 101 to 150

Read [](file:///home/nebur02/Documents/3er%20Ano/2do%20SEMESTRE/SRI/Proyecto/S.R.I./crawler/scraper.py#151-151), lines 151 to 192

### Detalles del Funcionamiento del Crawler

Hola! Te explico con más detalles cómo funciona el módulo de **crawler** en la aplicación "Oscar Insight Search". Este módulo se encarga de adquirir datos de películas desde fuentes externas. Se divide en dos partes principales: el cliente para la **API de TMDB** (para metadatos estructurados) y el **scraper** para reseñas de usuarios (originalmente Letterboxd, pero actualizado a Metacritic por razones técnicas). Vamos paso a paso.

#### 1. **Cliente TMDB (tmdb_client.py)**
Este es un cliente ligero en Python que se comunica con la **API v3 de TMDB (The Movie Database)**, una base de datos gratuita y pública de películas. TMDB es la fuente principal de metadatos estructurados (título, director, géneros, etc.), ya que proporciona datos limpios y organizados.

##### **¿Cómo se comunica con la API de TMDB?**
- **Protocolo**: HTTP GET requests a endpoints RESTful de TMDB (ej.: `https://api.themoviedb.org/3/discover/movie`).
- **Autenticación**: TMDB requiere credenciales para evitar abuso. El cliente soporta dos métodos:
  - **API Key (v3)**: Se pasa como parámetro de query (`?api_key=tu_clave`).
  - **Access Token (v4/v3)**: Se pasa en el header `Authorization: Bearer tu_token`.
- **Rate Limiting**: TMDB limita las requests gratuitas a ~40 por 10 segundos. El cliente aplica un delay conservador de 0.27 segundos entre llamadas para no exceder el límite.
- **Librería**: Usa `requests` para las HTTP requests, con una sesión persistente para eficiencia.
- **Formato de respuesta**: JSON. El cliente parsea el JSON y lo convierte en diccionarios Python.

##### **¿Cómo extrae los datos?**
- **Método `discover_movies()`**: Descubre listas de películas.
  - Envía una request a `/discover/movie` con parámetros como `sort_by` (ordenar por popularidad o calidad), `page` (página de resultados), `language=en-US`, `primary_release_date.gte=1990-01-01`, etc.
  - Filtra películas en inglés (para maximizar reseñas en Letterboxd/Metacritic) y con al menos ciertos votos.
  - Extrae campos básicos: `tmdb_id`, `title`, `year`, `overview`, `vote_average`, `vote_count`, etc.
- **Método `get_movie_details(tmdb_id)`**: Obtiene detalles completos de una película específica.
  - Envía una request a `/movie/{tmdb_id}` con `append_to_response=credits,external_ids` (para obtener todo en una sola llamada).
  - Parse el JSON para extraer:
    - **Créditos**: Del campo `credits`, saca el director (de `crew` donde `job == "Director"`) y el top 10 de actores (de `cast`).
    - **Géneros**: Lista de nombres de géneros.
    - **IDs externos**: Como `imdb_id` (de `external_ids`).
    - Otros: presupuesto, ingresos, duración, tagline, etc.
  - Retorna un diccionario con todos los campos enriquecidos.

##### **¿Por qué necesita una API Key?**
- **Razones de TMDB**: La API es gratuita, pero requiere autenticación para:
  - **Control de uso**: Evitar que bots abusen del servicio (rate limits).
  - **Acceso a datos**: Algunos endpoints requieren credenciales; sin ellas, las requests fallan con error 401 (Unauthorized).
  - **Personalización**: Permite rastrear uso por aplicación (útil para desarrolladores).
- **Sin key**: No puedes hacer requests; el cliente lanza un error si no se proporciona al menos una key o token.

##### **¿Cómo se usa la API Key?**
- En el código: Se pasa al constructor `TmdbClient(api_key="tu_clave")`.
- En requests: Se añade automáticamente como `?api_key=tu_clave` en la URL, o como header `Authorization: Bearer tu_token` si usas access token.
- En el script de población (populate_tmdb.py): Se lee de variable de entorno `TMDB_API_KEY` o se pasa como argumento `--api-key`.

##### **¿Cómo conseguir la API Key?**
1. Ve al sitio oficial: [https://www.themoviedb.org/settings/api](https://www.themoviedb.org/settings/api).
2. Crea una cuenta gratuita en TMDB (si no tienes).
3. En "API" > "Request an API Key", selecciona "Developer" (para uso no comercial).
4. Llena el formulario: describe tu aplicación (ej.: "Proyecto académico SRI para búsqueda de películas"), acepta términos.
5. Recibirás una **API Key v3** (un string largo como `b2119ca4292283dc53299bdf3c3998db`) y opcionalmente un **Access Token**.
6. Guárdala segura (no la subas a repositorios públicos). Úsala en el código o como variable de entorno.

#### 2. **Scraper de Reseñas (scraper.py)**
Originalmente diseñado para Letterboxd, pero actualizado a **Metacritic** porque:
- Letterboxd tiene mucho "ruido" (chistes internos, spoilers cortos).
- Otros sitios (IMDb, Rotten Tomatoes) bloquean con protecciones anti-bot (DataDome, Cloudflare).

##### **¿Cómo funciona el scraper?**
- **Librería**: Usa `curl_cffi` (en lugar de `requests` estándar) para impersonar un navegador real (TLS fingerprinting de Chrome 124). Esto evade protecciones WAF/Cloudflare que bloquean bots.
- **Sesión**: Una sesión persistente con headers de Chrome real (User-Agent, Accept, etc.).
- **Delay**: Espera aleatoria (1.5-3.5 segundos) entre requests para simular comportamiento humano y evitar bans.

##### **¿Cómo extrae los datos?**
- **Método `get_reviews(title, year, imdb_id, max_reviews)`**:
  - Convierte el título en un "slug" (ej.: "Oppenheimer" → "oppenheimer" o "oppenheimer-2023").
  - Construye URL: `https://www.metacritic.com/movie/{slug}/user-reviews/`.
  - Hace GET request y parsea el HTML con BeautifulSoup.
  - Busca reseñas en tags `<span>` o `<div>` con clases específicas (ej.: `review-card__quote`).
  - Filtra: Solo reseñas largas (100-3000 caracteres), sin texto de UI ("Sign in", "Expand").
  - Retorna lista de strings (reseñas limpias).
- **Compatibilidad**: El código mantiene alias como `LetterboxdReviewScraper` para no romper el pipeline existente.

##### **¿Por qué necesita evadir protecciones?**
- Metacritic (y otros) usan Cloudflare para detectar bots. Sin impersonation, las requests fallan o devuelven captchas/blocks.
- `curl_cffi` simula un navegador real, permitiendo acceso.

#### Integración en el Flujo General
- En populate_tmdb.py: Primero usa `TmdbClient` para obtener listas y detalles, luego `MetacriticReviewScraper` para reseñas.
- Los datos se combinan en un "rich_text" (título + sinopsis + reseñas) para indexación.
- Ejemplo de uso: `python populate_tmdb.py --api-key TU_CLAVE` pobla la DB con TMDB + reseñas.

Si quieres ver ejemplos de código o ejecutar una prueba (ej.: obtener detalles de una película), ¡dímelo! También puedo explicar cómo actualizar el scraper si cambian los selectores de Metacritic. 😊





-------------------------------------------------------------






### Definiciones Clave en el Contexto de la Aplicación

Hola! Te explico las definiciones de los términos que mencionas, enfocándome en cómo se aplican en el proyecto "Oscar Insight Search". Usaré lenguaje simple y directo.

#### 1. **¿Qué es un Crawler?**
Un **crawler** (o "rastreador" en español) es un programa o script que navega automáticamente por la web para recopilar información de múltiples páginas o sitios. En el contexto de esta aplicación:
- El módulo crawler actúa como un crawler general que coordina la adquisición de datos.
- No solo "raspa" contenido, sino que también maneja la lógica de navegación, autenticación y procesamiento de datos estructurados.
- Ejemplo: El `TmdbClient` "crawlea" la API de TMDB enviando requests HTTP a endpoints específicos para obtener listas de películas y detalles.

En resumen, un crawler es como un robot que explora y recolecta datos de fuentes web o APIs de manera sistemática, a menudo siguiendo enlaces o patrones.

#### 2. **¿Qué es un Scraper?**
Un **scraper** (o "raspador" en español) es una herramienta que extrae datos específicos de páginas web HTML, parseando el contenido (como texto, imágenes o tablas) y convirtiéndolo en un formato usable (ej.: JSON o base de datos). A diferencia de un crawler, se enfoca en una página o sitio a la vez, no en navegación amplia.
- En la aplicación: El `MetacriticReviewScraper` (en scraper.py) es un scraper que descarga páginas HTML de Metacritic, parsea el código con BeautifulSoup y extrae reseñas de usuarios.
- Usa técnicas como impersonación de navegador (con `curl_cffi`) para evadir bloqueos anti-bot.
- Ejemplo: De una página como `https://www.metacritic.com/movie/oppenheimer/user-reviews/`, extrae textos de reseñas largas y los limpia.

En resumen, un scraper es como un extractor quirúrgico que "raspa" datos de una página web específica, ideal para contenido no estructurado como reseñas.

#### 3. **¿Qué es TMDB?**
**TMDB** (The Movie Database) es una base de datos gratuita y colaborativa de películas, series y actores, similar a IMDb pero con API abierta para desarrolladores. Es propiedad de una comunidad y no de una empresa grande.
- En la aplicación: Es la fuente principal de metadatos estructurados (título, director, géneros, presupuesto, etc.). Se accede vía su API v3 (RESTful), que devuelve datos en JSON.
- Ventajas: Gratuita, actualizada por usuarios, cubre millones de títulos, y permite filtrar por popularidad, calidad, idioma, etc.
- Ejemplo: Para "Oppenheimer", TMDB proporciona ID único (872585), sinopsis, reparto, y enlaces a IMDb.

En resumen, TMDB es una "Wikipedia de películas" con API para integrar datos en aplicaciones, usada aquí para enriquecer el corpus de películas.

#### 4. **¿Qué es Metacritic?**
**Metacritic** es un sitio web y agregador de reseñas que recopila críticas de profesionales y usuarios para películas, juegos, música y TV. Asigna puntuaciones numéricas (ej.: 0-100) basadas en reseñas de fuentes confiables.
- En la aplicación: Se usa como fuente de reseñas de usuarios (User Reviews) para obtener texto en lenguaje natural rico. El scraper extrae críticas largas y analíticas, ideales para el modelo de búsqueda (ya que proporcionan vocabulario variado para consultas como "películas oscuras y claustrofóbicas").
- Razón de elección: Ofrece reseñas detalladas y críticas reales, a diferencia de sitios con más ruido (como Letterboxd, que tiene spoilers o chistes cortos).
- Ejemplo: Para "Oppenheimer", Metacritic tiene reseñas como "Una obra maestra de cine épico..." que se añaden al "rich_text" para indexación.

En resumen, Metacritic es un sitio de reseñas agregadas, usado aquí para complementar los metadatos de TMDB con opiniones subjetivas de usuarios.

Si quieres ejemplos de código o cómo estos se integran en el flujo, ¡házmelo saber! 😊