r"""
database/checkpoint.py
Sistema de Checkpointing — Oscar Insight Search (SRI 2025-2026)

=======================================================================================================
                      MATHEMATICAL STATE-SPACE MODEL OF THE CHECKPOINT ENGINE
=======================================================================================================

Let $\mathcal{S}_t$ represent the total execution state of the crawler/indexer pipeline at time $t$. 
We formally define this state space as a 5-tuple:
    $$\mathcal{S}_t = \left( \mathcal{P}_t, \mathcal{F}_t, p_t^{pop}, p_t^{qual}, N_t \right)$$

where:
1. $\mathcal{P}_t \subset \mathbb{N}$ represents the set of TMDB unique identifiers successfully 
   crawled, processed, and inverted:
    $$\mathcal{P}_t = \{ id_1, id_2, \dots, id_k \}$$
2. $\mathcal{F}_t \subset \mathbb{N}$ represents the set of TMDB unique identifiers that failed during 
   the fetching or scraping phases (due to TLS handshake failures, 404 HTTP errors, or selector timeouts):
    $$\mathcal{F}_t = \{ id'_1, id'_2, \dots, id'_m \}$$
3. $p_t^{pop} \in \mathbb{N}$ is the high-watermark page index reached by the TMDB discover API 
   under the popularity-driven seed strategy: $\text{strategy} = \text{"popularity"}$.
4. $p_t^{qual} \in \mathbb{N}$ is the high-watermark page index reached by the TMDB discover API 
   under the quality-driven seed strategy: $\text{strategy} = \text{"quality"}$.
5. $N_t \in \mathbb{N}$ represents the total cardinal count of fully committed documents:
    $$N_t = |\mathcal{P}_t|$$

State Transformations & Transitions:
- Success Commit:
  When a document with TMDB ID $x$ is processed successfully, the state transition is defined as:
    $$\mathcal{P}_{t+1} = \mathcal{P}_t \cup \{x\}$$
    $$\mathcal{F}_{t+1} = \mathcal{F}_t \setminus \{x\}$$
- Failure Commit:
  When a document with TMDB ID $x$ fails:
    $$\mathcal{F}_{t+1} = \mathcal{F}_t \cup \{x\}$$
    $$\mathcal{P}_{t+1} = \mathcal{P}_t \setminus \{x\}$$

Membership Assertions (O(1) Hash-Set Lookup Complexity):
To decide whether to skip a seed candidate $x$, the parser queries the state:
    $$\text{Skip}(x) = [x \in \mathcal{P}_t \cup \mathcal{F}_t]$$
Using hash-sets, this boolean membership resolution takes $O(1)$ average-case time complexity.
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
        r"""
        Inicializa la estructura de datos del checkpoint cargando cualquier estado previo del disco.
        
        Mathematical Initialization:
        Allocates $\mathcal{P}_0 = \emptyset$ and $\mathcal{F}_0 = \emptyset$ as memory sets, 
        then attempts to deserialize $\mathcal{S}_{saved}$ from the disk store.
        """
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
        r"""
        True si el tmdb_id ya fue procesado (pertenece a los conjuntos de éxito o fallo).
        
        Mathematical Definition:
        $$x \in \mathcal{P}_t \lor x \in \mathcal{F}_t$$
        Returns `True` if the TMDB ID exists in either set, triggering an immediate execution bypass.
        """
        return tmdb_id in self.processed_ids or tmdb_id in self.failed_ids

    def mark_done(self, tmdb_id: int) -> None:
        r"""
        Marca un tmdb_id como procesado exitosamente.
        
        Mathematical State Transition:
        $$\mathcal{P}_{t+1} \leftarrow \mathcal{P}_t \cup \{x\}$$
        $$\mathcal{F}_{t+1} \leftarrow \mathcal{F}_t \setminus \{x\}$$
        """
        self.processed_ids.add(tmdb_id)
        self.failed_ids.discard(tmdb_id)  # Quitar de fallidos si estaba

    def mark_failed(self, tmdb_id: int) -> None:
        r"""
        Marca un tmdb_id como fallido (se puede reintentar con --retry-failed).
        
        Mathematical State Transition:
        $$\mathcal{F}_{t+1} \leftarrow \mathcal{F}_t \cup \{x\}$$
        """
        self.failed_ids.add(tmdb_id)

    def save(self) -> None:
        r"""
        Persiste el estado actual en checkpoint.json de forma transaccional.
        
        Persistency Transformation:
        Let $f_{serialize}: \mathcal{S}_t \to \text{JSON\_String}$ be a transformation that maps 
        sets $\mathcal{P}_t$ and $\mathcal{F}_t$ to sorted integer arrays to guarantee canonical representation 
        and deterministic file diffs:
        $$f_{serialize}(\mathcal{P}_t) = \text{sort}(\mathcal{P}_t)$$
        $$f_{serialize}(\mathcal{F}_t) = \text{sort}(\mathcal{F}_t)$$
        """
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
        r"""
        Borra todo el estado (para empezar desde cero).
        
        Reset Boundary:
        $$\mathcal{P}_{new} = \emptyset, \quad \mathcal{F}_{new} = \emptyset$$
        $$p^{pop} = 0, \quad p^{qual} = 0, \quad N = 0$$
        Deletes the physical backing file on the filesystem to restore clean state.
        """
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
        r"""
        Carga y deserializa el estado desde checkpoint.json.
        
        Deserialisation Mapping:
        $$\mathcal{P}_t \leftarrow \{ x \in \text{JSON.processed\_tmdb\_ids} \}$$
        $$\mathcal{F}_t \leftarrow \{ x \in \text{JSON.failed\_tmdb\_ids} \}$$
        """
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
