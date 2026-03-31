"""
api/__init__.py
Módulo de Recuperación / RAG — Oscar Insight Search (SRI 2025-2026)

Expone la aplicación FastAPI para uso con uvicorn:
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from .main import app

__all__ = ["app"]
