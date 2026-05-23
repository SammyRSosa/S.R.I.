# Lógica de Ranking y Posicionamiento Avanzado

El sistema *Oscar Insight Search* utiliza un algoritmo de posicionamiento que combina modelos clásicos, semánticos y señales externas de calidad.

## 1. El Motor Híbrido
La base del ranking es la suma ponderada de dos modelos de recuperación:

1.  **Extended Boolean Model (EBM):**
    - Proporciona precisión mediante concordancia exacta de términos.
    - Utiliza la **p-norma** ($p=2$) para suavizar la lógica booleana AND/OR.
    - Los pesos se basan en **TF-IDF**.
2.  **Vector Retrieval:**
    - Proporciona cobertura semántica (conceptos similares aunque no compartan palabras).
    - Utiliza **Sentence Embeddings** y búsqueda por coseno vía **FAISS**.

**Fórmula Híbrida Inicial:**
$S_{Hibrido} = (0.6 \cdot S_{EBM}) + (0.4 \cdot S_{VEC})$

## 2. Factores de Re-Ranking (Corte 3)
Para cumplir con los requisitos de posicionamiento avanzado, el score híbrido se ajusta con dos factores adicionales:

### 2.1 Popularidad (TMDB)
Premia a las películas que han tenido mayor impacto cultural.
- **Factor:** $0.1 \cdot \text{popularity\_normalized}$
- **Fuente:** Atributo `popularity` de la API de TMDB.

### 2.2 Frescura (Año de Estreno)
Premia ligeramente a las películas más recientes para mantener los resultados actualizados.
- **Factor:** $0.05 \cdot \text{freshness\_factor}$
- **Cálculo:** Basado en la cercanía del año de estreno al presente.

## 3. Fórmula Final de Posicionamiento
$Score = S_{Hibrido} + (0.1 \cdot Pop) + (0.05 \cdot Fresh)$

---

## 4. Implementación del Fallback
Cuando el sistema detecta que el **Top 1 Score** es inferior a **0.15**, se activa el módulo de búsqueda web. Esto garantiza que el usuario siempre reciba información relevante, incluso si el corpus local (1,650 docs) es insuficiente para la consulta específica.

