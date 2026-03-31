# ════════════════════════════════════════════════════════════════════════════════
# Oscar Insight Search — Dockerfile multietapa
# Python 3.11-slim | builder → runtime
# ════════════════════════════════════════════════════════════════════════════════

# ── Etapa 1: builder ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Herramientas de compilación necesarias para algunas dependencias C (lxml, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copiar e instalar dependencias en una carpeta aislada
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# Descargar recursos NLTK necesarios para el módulo de indexación
RUN python -c "\
import nltk; \
nltk.download('punkt',      download_dir='/install/nltk_data'); \
nltk.download('punkt_tab',  download_dir='/install/nltk_data'); \
nltk.download('stopwords',  download_dir='/install/nltk_data'); \
nltk.download('snowball_data', download_dir='/install/nltk_data')"


# ── Etapa 2: runtime ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="SRI 2025-2026 Team" \
      description="Oscar Insight Search — Sistema de Recuperación de Información" \
      version="0.1.0"

WORKDIR /app

# Copiar paquetes instalados desde el builder
COPY --from=builder /install /usr/local

# Copiar datos NLTK pre-descargados
COPY --from=builder /install/nltk_data /usr/share/nltk_data

# Variable de entorno para que NLTK encuentre los datos
ENV NLTK_DATA=/usr/share/nltk_data

# Copiar código fuente
COPY . .

# Puerto del servicio FastAPI
EXPOSE 8000

# Comando de arranque (uvicorn con recarga desactivada en producción)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
