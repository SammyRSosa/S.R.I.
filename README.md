# Oscar Insight Search
## Sistema de Recuperación de Información Híbrido — Cine y Premios Oscar

> **Curso:** SRI 2025-2026 | **Versión:** 0.3.0 (Corte 3)
> **Modelos:** Booleano Extendido ($p$-norm) + Búsqueda Semántica (Vectores FAISS)

---

## 1. Resumen del Proyecto

*Oscar Insight Search* es un motor de búsqueda avanzado diseñado para el dominio cinematográfico, específicamente películas vinculadas a los Premios Oscar. A diferencia de los buscadores tradicionales, este sistema utiliza una **arquitectura híbrida** que combina:

1.  **Modelo Booleano Extendido (EBM)**: Implementación de la $p$-norma para permitir consultas booleanas "suaves" con ranking continuo.
2.  **Búsqueda Semántica**: Uso de *embeddings* (Sentence-Transformers) y búsqueda aproximada (FAISS) para recuperar documentos por significado, superando la barrera del vocabulario exacto.

El corpus contiene **1,623 documentos** enriquecidos con metadatos de TMDB y críticas de alta calidad de Metacritic.

---

## 2. Arquitectura y Módulos

El sistema sigue una arquitectura modular y limpia:

*   `crawler/`: Adquisición sigilosa de datos usando TLS Fingerprinting (`curl_cffi`) para evadir bloqueos WAF.
*   `indexer/`: Pipeline de NLP (NLTK) y lógica matemática del modelo EBM ($p$-norma).
*   `database/`: Gestión de persistencia JSON y almacenamiento de vectores FAISS.
*   `api/`: Servidor FastAPI que expone el motor híbrido y sirve la interfaz web.
*   `scripts/`: Utilidades para la población masiva del corpus y pruebas de sistema.

---

## 3. Instalación y Despliegue

### 3.1 Requisitos
- Python 3.11+
- Clave de API de TMDB.

### 3.2 Configuración del Entorno
```bash
# 1. Clonar e instalar dependencias
pip install -r requirements.txt

# 2. Configurar API Key (opcional para ejecución, necesaria para recolección)
# Windows (PowerShell):
$env:TMDB_API_KEY = "tu_clave_aqui"
```

### 3.3 Preparación de Datos e Índices
Para que el sistema sea operativo, se deben generar los índices TF-IDF y Vectoriales:
```bash
# Generar pesos EBM y Embeddings FAISS (Corte 2)
python scripts/build_corte2.py
```

### 3.4 Ejecución Local de la API y UI
```bash
# Iniciar el servidor local
uvicorn api.main:app --host 127.0.0.1 --port 8000
```
Una vez iniciado, acceda a:
- **Interfaz Visual (UI)**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Documentación API**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 3.5 Despliegue con Docker
El proyecto cuenta con un `Dockerfile` multietapa optimizado que empaqueta las dependencias de Python y pre-descarga los corpus lingüísticos de `NLTK` en la etapa de compilación para garantizar la velocidad de arranque.

Siga los siguientes pasos para construir y ejecutar el contenedor:

1. **Construir la imagen de Docker**:
   ```bash
   docker build -t oscar-insight:latest .
   ```

2. **Ejecutar el contenedor**:
   Dado que el sistema requiere variables de entorno (como `GROQ_API_KEY` para el módulo RAG) y persiste su base de datos de películas e índices en el directorio `/app/data` del contenedor, debe pasar sus credenciales y montar un volumen para garantizar la persistencia física de los datos.

   * **En Linux o macOS (Bash)**:
     ```bash
     docker run -d \
       -p 8000:8000 \
       --env-file .env \
       -v $(pwd)/data:/app/data \
       --name oscar-insight-app \
       oscar-insight:latest
     ```

   * **En Windows (PowerShell)**:
     ```powershell
     docker run -d `
       -p 8000:8000 `
       --env-file .env `
       -v ${PWD}/data:/app/data `
       --name oscar-insight-app `
       oscar-insight:latest
     ```

   * **Pasando las claves de API directamente**:
     ```bash
     docker run -d \
       -p 8000:8000 \
       -e GROQ_API_KEY="tu_clave_de_groq" \
       -e TMDB_API_KEY="tu_clave_de_tmdb" \
       -v $(pwd)/data:/app/data \
       --name oscar-insight-app \
       oscar-insight:latest
     ```

3. **Verificar el contenedor**:
   * Acceda desde su navegador web a `http://localhost:8000/`.
   * Verifique el estado de carga del corpus consumiendo el healthcheck: `curl http://localhost:8000/health`.

---


## 4. Verificación del Sistema

Para asegurar que el sistema está funcionando correctamente, realice las siguientes comprobaciones:

1.  **Health Check**: Ejecute `curl http://127.0.0.1:8000/health`. Debe devolver un JSON con `status: "ok"` y el número de documentos cargados (>1600).
2.  **Prueba de Integración**: Ejecute el script de prueba de búsqueda:
    ```bash
    python scripts/test_search.py
    ```
    Si recibe resultados con títulos de películas y fragmentos de críticas, el motor híbrido está operativo.

---

## 5. Detalles Técnicos (Configuración NLP)

El sistema evita "valores mágicos" (hardcoded) permitiendo la configuración de parámetros críticos:

- **Parámetro $p$**: Ajustable en la consulta (default 2.0). Controla la "estrictez" booleana.
- **Pesos Híbridos**: La API permite balancear la importancia del modelo EBM vs Vectores (default 0.6 / 0.4).
- **Modelo de Lenguaje**: Utiliza `paraphrase-multilingual-MiniLM-L12-v2`, el cual soporta alineación semántica multilingüe real (español/inglés).

---

## 6. Estado de Avance

| Módulo | Descripción | Estado |
|---|---|---|
| Adquisición | TMDB + Metacritic (User Reviews) | ✅ Completado |
| Indexación | Inverted Index + Pipeline NLTK | ✅ Completado |
| Corte 2 | Modelo Booleano Extendido ($p$-norm) | ✅ Completado |
| Corte 2 | Búsqueda Semántica (FAISS) | ✅ Completado |
| Corte 3 | Interfaz Visual (HTML5/Inter JS) | ✅ Completado |
| Despliegue | Dockerización Multietapa | ✅ Completado |

---

## 7. Referencias

1. Baeza-Yates, R., & Ribeiro-Neto, B. (2011). *Modern Information Retrieval*.
2. Salton, G., et al. (1983). *Extended Boolean information retrieval*.
3. TMDB API Documentation: [developer.themoviedb.org](https://developer.themoviedb.org/)
