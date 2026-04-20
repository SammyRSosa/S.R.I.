# ════════════════════════════════════════════════════════════════════════════════
# Oscar Insight Search — Dockerfile multietapa
# Python 3.11-slim | builder → runtime
# ════════════════════════════════════════════════════════════════════════════════

# ── Etapa 1: builder ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Herramientas de compilación necesarias para lxml y cloudscraper
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# Descargar recursos NLTK en tiempo de build (evita descarga en runtime)
RUN PYTHONPATH=/install/lib/python3.11/site-packages python -c "\
import nltk; \
nltk.download('punkt',     download_dir='/install/nltk_data'); \
nltk.download('punkt_tab', download_dir='/install/nltk_data'); \
nltk.download('stopwords', download_dir='/install/nltk_data')"


# ── Etapa 2: runtime ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="SRI 2025-2026 Team" \
      description="Oscar Insight Search — Sistema de Recuperación de Información" \
      version="0.2.0"

WORKDIR /app

# Dependencias instaladas desde el builder
COPY --from=builder /install /usr/local

# Datos NLTK pre-descargados
COPY --from=builder /install/nltk_data /usr/share/nltk_data

# Variables de entorno
ENV NLTK_DATA=/usr/share/nltk_data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Variable requerida para el script de población (se pasa con docker run -e)
# ENV TMDB_API_KEY=your_key_here

# Copiar código fuente (data/ queda fuera: se monta como volumen)
COPY api/       ./api/
COPY crawler/   ./crawler/
COPY database/  ./database/
COPY indexer/   ./indexer/
COPY scripts/   ./scripts/

# Puerto del servicio FastAPI
EXPOSE 8000

# Arrancar la API (los datos se montan como volumen externo)
# docker run -p 8000:8000 -v $(pwd)/data:/app/data oscar-insight:0.2
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
