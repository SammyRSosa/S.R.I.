"""
indexer/__init__.py
Módulo de Indexación — Oscar Insight Search (SRI 2025-2026)

Exporta la clase InvertedIndex para uso externo.
"""

from .inverted_index import InvertedIndex
from .ebm            import ExtendedBooleanModel

__all__ = ["InvertedIndex", "ExtendedBooleanModel"]
