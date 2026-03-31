"""
database/__init__.py
Módulo de Almacenamiento — Oscar Insight Search (SRI 2025-2026)

Persistencia JSON de documentos (películas) e índice invertido.
"""

from .store      import DocumentStore
from .checkpoint import Checkpoint

__all__ = ["DocumentStore", "Checkpoint"]
