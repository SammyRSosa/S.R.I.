"""
database/vector_store.py
Dense Vector Space Model (VSM) and Semantic Indexing Engine.

=======================================================================================================
                        MATHEMATICAL AND ALGORITHMIC THEORY OF VECTOR STORE
=======================================================================================================

This module implements a state-of-the-art semantic search layer based on neural sentence embeddings 
and approximate nearest neighbor search via Facebook AI Similarity Search (FAISS).

1. Bi-Encoder Dense Embedding Model
-----------------------------------
Let $T$ be a given sequence of text tokens representing a document $d_j$.
We map $T$ into a low-dimensional dense continuous vector space:
    $$\mathbf{e}_j = \text{TransformerEncoder}(T) \in \mathbb{R}^d$$
In our system, $d = 384$ using the pretrained `paraphrase-multilingual-MiniLM-L12-v2` model, 
which maps multi-lingual contexts into a shared geometric space.

2. L2 Vector Normalization & Cosine Similarity Identity
-------------------------------------------------------
Raw embeddings extracted from neural networks do not lie on a standard unit hypersphere.
To guarantee that simple, high-performance inner products map strictly to Cosine Similarity, 
we apply an explicit $L_2$ normalization transform:
    $$\mathbf{\hat{e}}_j = \frac{\mathbf{e}_j}{\|\mathbf{e}_j\|_2} = \frac{\mathbf{e}_j}{\sqrt{\sum_{k=1}^d e_{j,k}^2}}$$
After normalization, the $L_2$ norm of every vector is exactly 1:
    $$\|\mathbf{\hat{e}}_j\|_2 = 1.0$$
Given a query $Q$ with normalized embedding $\mathbf{\hat{e}}_q$, the Cosine Similarity 
is defined as:
    $$\text{Sim}_{cosine}(\mathbf{e}_q, \mathbf{e}_j) = \frac{\langle \mathbf{e}_q, \mathbf{e}_j \rangle}{\|\mathbf{e}_q\|_2 \|\mathbf{e}_j\|_2} = \langle \mathbf{\hat{e}}_q, \mathbf{\hat{e}}_j \rangle = \mathbf{\hat{e}}_q \cdot \mathbf{\hat{e}}_j$$
Thus, by pre-normalizing all documents and query vectors, we can bypass slow division logic 
and perform fast inner product calculations.

3. FAISS Flat Inner Product Indexing (faiss.IndexFlatIP)
---------------------------------------------------------
FAISS operates over normalized vectors to execute brute force or approximate k-nearest neighbor retrieval:
    $$\text{Retrieval}(Q) = \operatorname{arg\,max}_{j \in [0, N-1]}^k \left( \mathbf{\hat{e}}_q \cdot \mathbf{\hat{e}}_j \right)$$
The inner product FLAT index (`faiss.IndexFlatIP`) guarantees 100% recall as it computes exact 
pairwise products across all records in $O(N \cdot d)$ time.

4. Two-Way Coordinate Mapper
----------------------------
Since FAISS operates strictly over zero-indexed integer IDs ($i \in [0, M-1]$), we maintain a bijective 
bi-directional mapping to the document store primary IDs:
    $$f_{map}: \text{FAISS\_ID} \leftrightarrow \text{DocumentStore\_ID}$$
This mapping is persisted as a JSON dictionary mapping strings to integers.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"

class VectorStore:
    """
    Gestor del índice vectorial semántico utilizando FAISS y Sentence-Transformers.
    
    Este módulo permite realizar búsquedas por significado (similitud de coseno) 
    en lugar de solo por coincidencia exacta de palabras, utilizando un modelo 
    de lenguaje (bi-encoder) para generar representaciones densas de los documentos.

    Attributes:
        data_dir (Path): Directorio de persistencia.
        model (SentenceTransformer): Modelo de lenguaje cargado.
        index (faiss.Index): Índice de búsqueda aproximada (FAISS).
        vector_to_doc (dict): Mapeo interno para recuperar doc_id desde FAISS.
    """
    
    VECTOR_FILE = "faiss_index.bin"
    MAPPING_FILE = "vector_mapping.json"
    DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    TEXT_LIMIT = 2000 # Límite de caracteres para evitar truncamiento excesivo
    
    def __init__(self, data_dir: str | Path | None = DEFAULT_DATA_DIR, model_name: str = DEFAULT_MODEL, in_memory: bool = False) -> None:
        """
        Inicializa el almacén vectorial dense.
        
        Mathematical Initialization & Setup:
        1. Dimension Allocation:
           $$d = \text{model.get\_sentence\_embedding\_dimension}() \in \mathbb{N}$$
           For our default model 'paraphrase-multilingual-MiniLM-L12-v2', $d = 384$.
        2. FAISS Metric Space Construction:
           Instantiates a flat inner product index:
           $$\mathcal{I} = \text{faiss.IndexFlatIP}(d)$$
           This represents a Euclidean vector space $\mathbb{R}^d$ under the inner product metric:
           $$\langle \mathbf{x}, \mathbf{y} \rangle = \sum_{k=1}^d x_k y_k$$
           Because our vector pipeline enforces $L_2$ normalization on all inputs, 
           the inner product $\langle \mathbf{\hat{x}}, \mathbf{\hat{y}} \rangle$ maps exactly 
           to the cosine similarity measure:
           $$\text{Sim}_{cosine}(\mathbf{x}, \mathbf{y}) = \frac{\mathbf{x} \cdot \mathbf{y}}{\|\mathbf{x}\|_2 \|\mathbf{y}\|_2}$$

        Args:
            data_dir: Carpeta de persistencia física para guardar/cargar índices.
            model_name: Identificador del modelo pre-entrenado en HuggingFace.
            in_memory: Bandera booleana para ejecutar en memoria volátil (deshabilita E/S a disco).
        """
        self.in_memory = in_memory
        self.data_dir = Path(data_dir) if data_dir else None
        
        if self.data_dir and not self.in_memory:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.index_path = self.data_dir / self.VECTOR_FILE
            self.mapping_path = self.data_dir / self.MAPPING_FILE
        else:
            self.index_path = None
            self.mapping_path = None
        
        logger.info("Cargando modelo de embeddings: %s", model_name)
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        
        # Inicializar índice FAISS para Producto Interno (IP)
        # Nota: Al normalizar los vectores a L2, el Producto Interno es equivalente 
        # a la Similitud de Coseno.
        self.index: faiss.IndexFlatIP = faiss.IndexFlatIP(self.embedding_dim)
        
        # Diccionarios de mapeo: vector_id (FAISS) <-> doc_id (DocumentStore)
        self.vector_to_doc: dict[int, int] = {}
        self.doc_to_vector: dict[int, int] = {}
        
        if not self.in_memory:
            self.load()
        
    def build_from_documents(self, documents: dict[int, dict]) -> None:
        """
        Codifica un corpus completo de documentos estructurados y construye el índice FAISS.
        
        Algorithmic Workflow & Mathematical Operations:
        1. Context Extraction and Truncation:
           For each document $d_j \in \mathcal{D}$:
           $$T_j = \text{truncate}(\text{rich\_text}(d_j), L_{limit})$$
           where $L_{limit} = 2000$ characters, limiting token overflow inside the Transformer.
        2. Neural Inference (Forward Pass):
           The sequence $T_j$ is passed to the bi-encoder transformer model:
           $$\mathbf{e}_j = \text{TransformerEncoder}(T_j) \in \mathbb{R}^{384}$$
           This creates a raw dense representation matrix $\mathbf{E} \in \mathbb{R}^{N \times 384}$.
        3. Unit Hypersphere Projection ($L_2$ Normalization):
           Each row vector $\mathbf{e}_j$ is normalized to unit length:
           $$\mathbf{\hat{e}}_j = \frac{\mathbf{e}_j}{\|\mathbf{e}_j\|_2} = \frac{\mathbf{e}_j}{\sqrt{\sum_{k=1}^d e_{j,k}^2}}$$
           This operation is executed efficiently in-place by the C++ core of FAISS via:
           $$\text{faiss.normalize\_L2}(\mathbf{E})$$
        4. Spatial Indexing Allocation:
           The normalized embedding matrix is loaded into the inner-product flat index:
           $$\mathcal{I} \leftarrow \mathcal{I} \cup \{\mathbf{\hat{e}}_1, \mathbf{\hat{e}}_2, \dots, \mathbf{\hat{e}}_N\}$$
        5. Bijective Mapping Synchronisation:
           Establishes mapping $f_{map}(i) = doc\_id_j$ for index positions $i \in [0, N-1]$.

        Args:
            documents: Diccionario llave-valor conteniendo las películas estructuradas del DocumentStore.
        """
        logger.info("Generando embeddings para %d documentos...", len(documents))
        
        doc_ids = []
        texts = []
        
        # Preparar corpus de texto para el modelo
        for doc_id, film_data in documents.items():
            # Usamos rich_text (título + sinopsis + críticas) para máxima riqueza semántica
            rich_text = film_data.get("rich_text", "")
            if not rich_text:
                continue
                
            doc_ids.append(int(doc_id))
            # Truncamos ligeramente para no exceder el límite de tokens del modelo
            texts.append(rich_text[:self.TEXT_LIMIT])
            
        if not texts:
            logger.warning("No se encontraron textos válidos para indexación vectorial.")
            return
            
        # 1. Generación de vectores (embeddings) - Este paso es intensivo en CPU/GPU
        embeddings = self.model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
        
        # 2. Normalización L2 para asegurar que el Producto Interno sea Similitud de Coseno
        faiss.normalize_L2(embeddings)
        
        # 3. Construcción del índice FAISS
        self.index = faiss.IndexFlatIP(self.embedding_dim)
        self.index.add(embeddings)
        
        # 4. Actualizar mapeos de IDs
        self.vector_to_doc = {i: doc_id for i, doc_id in enumerate(doc_ids)}
        self.doc_to_vector = {doc_id: i for i, doc_id in enumerate(doc_ids)}
        
        self.save()
        logger.info("Índice FAISS finalizado con %d vectores.", self.index.ntotal)

    def add_documents_incremental(self, new_documents: dict[int, dict]) -> bool:
        """
        Agrega de forma incremental nuevos documentos al índice FAISS existente y actualiza la persistencia.
        
        Lógica:
        1. Si ya existe un índice binario guardado en disco y cargado en memoria (self.index.ntotal > 0),
           utiliza este índice.
        2. Si no, intenta cargarlo de disco usando load().
        3. Si sigue sin existir un índice inicializado, retorna False para forzar la inicialización inicial.
        4. Genera embeddings para los nuevos documentos utilizando sentence-transformers.
        5. Normaliza los nuevos embeddings y los inyecta en el índice con index.add().
        6. Actualiza los mapeos bidireccionales y persiste todo a disco de forma transaccional.
        """
        if not new_documents:
            logger.info("No hay nuevos documentos para agregar incrementalmente.")
            return True

        # Asegurar que el índice actual está cargado.
        if not self.in_memory and self.index_path and self.index_path.exists() and self.index.ntotal == 0:
            try:
                self.load()
            except Exception as e:
                logger.warning("Fallo al precargar el índice para actualización incremental: %s", e)

        # Si el índice sigue vacío, no podemos hacer una actualización incremental
        if self.index.ntotal == 0:
            logger.info("El índice está vacío o no existe en disco. Se requiere inicialización completa.")
            return False

        try:
            new_doc_ids = []
            new_texts = []
            
            # Filtrar documentos que ya están indexados para evitar duplicados en el espacio vectorial
            for doc_id, film_data in new_documents.items():
                int_doc_id = int(doc_id)
                if int_doc_id in self.doc_to_vector:
                    logger.debug("El documento ID %d ya existe en el espacio vectorial. Omitiendo duplicado.", int_doc_id)
                    continue
                    
                rich_text = film_data.get("rich_text", "")
                if not rich_text:
                    continue
                    
                new_doc_ids.append(int_doc_id)
                new_texts.append(rich_text[:self.TEXT_LIMIT])

            if not new_texts:
                logger.info("Todos los nuevos documentos ya estaban indexados vectorialmente.")
                return True

            logger.info("[FAISS-INCREMENTAL] Generando embeddings para %d nuevos documentos...", len(new_texts))
            
            # Generar vectores de los nuevos textos
            new_embeddings = self.model.encode(new_texts, show_progress_bar=False, convert_to_numpy=True)
            
            # Normalizar a L2 (para consistencia con Cosine Similarity)
            faiss.normalize_L2(new_embeddings)
            
            # Guardar el número original de vectores para calcular correctamente los nuevos IDs vectoriales
            old_ntotal = self.index.ntotal
            
            # Añadir directamente al índice FAISS en memoria
            self.index.add(new_embeddings)
            
            # Actualizar mapeos bidireccionales
            for i, doc_id in enumerate(new_doc_ids):
                vector_id = old_ntotal + i
                self.vector_to_doc[vector_id] = doc_id
                self.doc_to_vector[doc_id] = vector_id
                
            # Guardar índice actualizado y mappings en disco
            self.save()
            logger.info("[FAISS-INCREMENTAL] ✓ Se agregaron %d vectores de forma incremental. Total en FAISS: %d", len(new_texts), self.index.ntotal)
            return True
            
        except Exception as e:
            logger.error("[FAISS-INCREMENTAL] Falló actualización incremental: %s", e)
            return False

    def build_from_texts(self, texts: list[str]) -> None:
        """
        Codifica una lista de textos planos y construye el índice FAISS en memoria.
        Diseñado para indexar dinámicamente resultados ad-hoc del buscador web (focused crawling).
        
        Mathematical Formulation:
        Let $\mathcal{T} = \{t_1, t_2, \dots, t_M\}$ be a set of dynamically crawled web snippets.
        1. Embed:
           $$\mathbf{e}_i = \text{TransformerEncoder}(t_i) \in \mathbb{R}^d$$
        2. Normalise:
           $$\mathbf{\hat{e}}_i = \frac{\mathbf{e}_i}{\|\mathbf{e}_i\|_2}$$
        3. Index:
           $$\mathcal{I}_{temp} = \text{faiss.IndexFlatIP}(d)$$
           $$\mathcal{I}_{temp}.\text{add}(\{\mathbf{\hat{e}}_1, \dots, \mathbf{\hat{e}}_M\})$$
        
        This dynamically populated temporary space allows direct vector search on live scraped data.

        Args:
            texts: Lista de segmentos de texto extraídos de páginas HTML web externas.
        """
        logger.info("Generando embeddings para %d chunks temporales...", len(texts))
        if not texts:
            logger.warning("No se proporcionaron textos para indexación temporal.")
            return
            
        embeddings = self.model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        faiss.normalize_L2(embeddings)
        
        self.index = faiss.IndexFlatIP(self.embedding_dim)
        self.index.add(embeddings)
        
        # Mapeamos el ID del vector en FAISS al índice de la lista de textos (0 a N-1)
        self.vector_to_doc = {i: i for i in range(len(texts))}
        self.doc_to_vector = {i: i for i in range(len(texts))}
        
        logger.info("Índice FAISS temporal construido con %d vectores.", self.index.ntotal)

    def search(self, query: str, top_k: int = 10) -> list[tuple[int, float]]:
        """
        Busca los documentos más cercanos semánticamente a la consulta.
        
        Mathematical Search & Retrieval Flow:
        1. Query Embedding Inference:
           $$\mathbf{e}_q = \text{TransformerEncoder}(Q) \in \mathbb{R}^d$$
        2. Query Projection to Unit Hypersphere:
           $$\mathbf{\hat{e}}_q = \frac{\mathbf{e}_q}{\|\mathbf{e}_q\|_2}$$
        3. Nearest Neighbor Matrix Multiplication:
           FAISS computes exact inner products in parallel (C++ implementation):
           $$s_j = \mathbf{\hat{e}}_q \cdot \mathbf{\hat{e}}_j = \sum_{k=1}^d \hat{e}_{q,k} \hat{e}_{j,k}$$
           Since $\|\mathbf{\hat{e}}_q\|_2 = 1$ and $\|\mathbf{\hat{e}}_j\|_2 = 1$, we have:
           $$s_j \in [-1.0, 1.0]$$
        4. Argmax Filtering:
           $$\text{Retrieval}(Q) = \operatorname{arg\,max}_{j \in [0, N-1]}^{\text{top\_k}} (s_j)$$
        5. Score Calibration / Normalization:
           To avoid negative bounds in UI layouts, we project the Cosine Score into $[0, 1]$:
           $$s_j^{norm} = \min(1.0, \max(0.0, s_j))$$

        Args:
            query: Texto de búsqueda en lenguaje natural.
            top_k: Número máximo de resultados (vecinos más cercanos) a retornar.

        Returns:
            Lista ordenada de tuplas (doc_id, score_normalizado) ordenada de mayor a menor relevancia.
        """
        if self.index.ntotal == 0:
            logger.warning("El índice vectorial está vacío. Ejecute un método build primero.")
            return []
            
        # Codificar y normalizar la consulta
        emb = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(emb)
        
        # Búsqueda en FAISS
        # D: Distancias (scores), I: Índices (IDs internos de FAISS)
        scores, I = self.index.search(emb, top_k)
        
        results = []
        for score, vector_id in zip(scores[0], I[0]):
            # FAISS devuelve -1 si no encuentra suficientes resultados
            if vector_id != -1 and vector_id in self.vector_to_doc:
                doc_id = self.vector_to_doc[vector_id]
                # Normalizamos el score al rango [0, 1]
                normalized_score = max(0.0, min(1.0, float(score)))
                results.append((doc_id, normalized_score))
                
        return results
        
    def save(self) -> None:
        r"""
        Persiste el índice binario de FAISS y el mapeo biyectivo en disco de forma transaccional.
        
        Flow:
        1. FAISS Index Serialisation:
           Serializes the C++ Index structure into a binary format at `index_path`:
           $$\mathcal{I} \xrightarrow{\text{faiss.write\_index}} \text{faiss\_index.bin}$$
        2. Bijective Map Persistency:
           Serializes $f_{map}$ into JSON notation at `mapping_path`:
           $$f_{map} \xrightarrow{\text{json.dump}} \text{vector\_mapping.json}$$
        """
        if self.in_memory or not self.index_path or not self.mapping_path:
            return
        try:
            faiss.write_index(self.index, str(self.index_path))
            with open(self.mapping_path, "w", encoding="utf-8") as f:
                json.dump(self.vector_to_doc, f)
            logger.debug("Archivos vectoriales guardados en %s", self.data_dir)
        except Exception as e:
            logger.error("Error al guardar VectorStore: %s", e)
            
    def load(self) -> None:
        r"""
        Carga el índice binario y reconstruye los mapeos bidireccionales en memoria.
        
        Algorithms:
        1. Index Deserialisation:
           $$\mathcal{I} \xleftarrow{\text{faiss.read\_index}} \text{faiss\_index.bin}$$
        2. Bi-directional Map Re-allocation:
           Reads the serialized dictionary $M_{raw}$:
           $$f_{map} = \{ \text{int}(k): \text{int}(v) \quad \forall (k, v) \in M_{raw} \}$$
           $$f_{map}^{-1} = \{ \text{int}(v): \text{int}(k) \quad \forall (k, v) \in M_{raw} \}$$
        """
        if self.in_memory or not self.index_path or not self.mapping_path:
            return
        if self.index_path.exists() and self.mapping_path.exists():
            try:
                self.index = faiss.read_index(str(self.index_path))
                with open(self.mapping_path, "r", encoding="utf-8") as f:
                    raw_mapping = json.load(f)
                    self.vector_to_doc = {int(k): int(v) for k, v in raw_mapping.items()}
                    self.doc_to_vector = {int(v): int(k) for k, v in raw_mapping.items()}
                logger.info("Índice vectorial cargado exitosamente (%d vectores).", self.index.ntotal)
            except Exception as e:
                logger.error("Fallo al cargar índice vectorial: %s", e)
