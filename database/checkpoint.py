"""
database/checkpoint.py
Sistema de Checkpointing — Oscar Insight Search (SRI 2025-2026)

Permite que el proceso de población sea interrumpible y reanudable sin
duplicar datos. Estado persistido en data/checkpoint.json.

Estructura del checkpoint:
    {
        "last_page_popularity": 45,
        "last_page_quality": 12,
        "processed_tmdb_ids": [872585, 11036, ...],
        "failed_tmdb_ids": [99999],
        "total_indexed": 900,
        "last_updated": "2026-03-31T14:00:00"
    }

Uso:
    ck = Checkpoint()
    if ck.is_processed(872585):
        continue
    # ... proceso la película ...
    ck.mark_done(872585)
    ck.save()
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_CHECKPOINT_PATH = Path(__file__).parent.parent / "data" / "checkpoint.json"


class Checkpoint:
    """
    Gestor de estado de progreso para el proceso de población.

    Mantiene en memoria los tmdb_ids ya procesados (set para O(1) lookup)
    y persiste el estado en JSON para poder reanudar tras una interrupción.

    Attributes:
        path (Path): Ruta al archivo checkpoint.json.
        processed_ids (set[int]): IDs de TMDB ya procesados correctamente.
        failed_ids (set[int]): IDs de TMDB que fallaron en el scraping.
        last_page_popularity (int): Última página de strategy="popularity" procesada.
        last_page_quality (int):    Última página de strategy="quality" procesada.
        total_indexed (int): Número total de documentos indexados.

    Example::

        ck = Checkpoint()
        # Al inicio del loop:
        if ck.is_processed(tmdb_id):
            continue
        # Al final del proceso exitoso:
        ck.mark_done(tmdb_id)
        ck.total_indexed += 1
        ck.save()   # Persiste en disco
    """

    def __init__(self, path: str | Path = DEFAULT_CHECKPOINT_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Estado
        self.processed_ids: set[int] = set()
        self.failed_ids: set[int]    = set()
        self.last_page_popularity: int = 0
        self.last_page_quality: int    = 0
        self.total_indexed: int        = 0

        # Cargar estado previo si existe
        if self.path.exists():
            self._load()

    # ─── API pública ──────────────────────────────────────────────────────────

    def is_processed(self, tmdb_id: int) -> bool:
        """True si el tmdb_id ya fue procesado (éxito o fallo)."""
        return tmdb_id in self.processed_ids or tmdb_id in self.failed_ids

    def mark_done(self, tmdb_id: int) -> None:
        """Marca un tmdb_id como procesado exitosamente."""
        self.processed_ids.add(tmdb_id)
        self.failed_ids.discard(tmdb_id)  # Quitar de fallidos si estaba

    def mark_failed(self, tmdb_id: int) -> None:
        """Marca un tmdb_id como fallido (se puede reintentar con --retry-failed)."""
        self.failed_ids.add(tmdb_id)

    def save(self) -> None:
        """Persiste el estado actual en checkpoint.json."""
        payload = {
            "last_page_popularity":  self.last_page_popularity,
            "last_page_quality":     self.last_page_quality,
            "processed_tmdb_ids":    sorted(self.processed_ids),
            "failed_tmdb_ids":       sorted(self.failed_ids),
            "total_indexed":         self.total_indexed,
            "last_updated":          datetime.now(timezone.utc).isoformat(),
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        logger.debug(
            "Checkpoint guardado: %d procesados, %d fallidos, idx=%d",
            len(self.processed_ids), len(self.failed_ids), self.total_indexed,
        )

    def reset(self) -> None:
        """Borra todo el estado (para empezar desde cero)."""
        self.processed_ids = set()
        self.failed_ids    = set()
        self.last_page_popularity = 0
        self.last_page_quality    = 0
        self.total_indexed = 0
        if self.path.exists():
            self.path.unlink()
        logger.info("Checkpoint reseteado.")

    # ─── Carga ────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Carga el estado desde checkpoint.json."""
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.processed_ids        = set(data.get("processed_tmdb_ids", []))
            self.failed_ids           = set(data.get("failed_tmdb_ids", []))
            self.last_page_popularity = data.get("last_page_popularity", 0)
            self.last_page_quality    = data.get("last_page_quality",    0)
            self.total_indexed        = data.get("total_indexed", 0)
            logger.info(
                "Checkpoint cargado: %d procesados | %d fallidos | idx=%d | "
                "pop_page=%d | quality_page=%d",
                len(self.processed_ids), len(self.failed_ids),
                self.total_indexed,
                self.last_page_popularity, self.last_page_quality,
            )
        except Exception as exc:
            logger.warning("No se pudo cargar checkpoint: %s. Empezando desde cero.", exc)

    # ─── Representación ───────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Retorna un dict con las estadísticas del checkpoint."""
        return {
            "processed": len(self.processed_ids),
            "failed":    len(self.failed_ids),
            "indexed":   self.total_indexed,
            "pop_page":  self.last_page_popularity,
            "qua_page":  self.last_page_quality,
        }

    def __repr__(self) -> str:
        s = self.stats()
        return (
            f"Checkpoint(processed={s['processed']}, failed={s['failed']}, "
            f"indexed={s['indexed']}, path='{self.path}')"
        )
