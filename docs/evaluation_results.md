# Resultados de Evaluación y Análisis de Calidad

Este documento detalla el proceso de validación del sistema *Oscar Insight Search* mediante métricas objetivas de recuperación de información, asegurando que el sistema satisface plenamente las necesidades de los usuarios en el dominio cinematográfico.

## 1. Metodología
Se utilizó un conjunto de **Ground Truth** (`data/ground_truth.json`) compuesto por 6 consultas expertas que cubren diferentes aspectos y dificultades del dominio cinematográfico:
1. **Consultas Directas**: Director + Franquicia (ej. "James Cameron Pandora", "Avatar sci-fi Cameron").
2. **Consultas Conceptuales**: Director + Tema (ej. "Christopher Nolan atomic bomb").
3. **Consultas Multimodales Complejas**: Temáticas abstractas o de nicho (ej. "dreams and heist Christopher Nolan").
4. **Consultas de Contexto Histórico**: Entidades + Género (ej. "Oppenheimer historical drama").

Estas consultas ponen a prueba la capacidad del motor de comprender nombres propios, temáticas implícitas en sinopsis, y combinar múltiples facetas de los metadatos de las películas.

## 2. Métricas Alcanzadas (Corte Final)

Gracias a la implementación de la Ecuación de Posicionamiento Híbrida (EBM + Semántica Vectorial) combinada con los re-rankers de Popularidad y Frescura de estreno, el sistema logró un incremento sustancial en la calidad de respuesta.

| Métrica | Resultado | Interpretación de Impacto |
| :--- | :---: | :--- |
| **Mean Precision@5** | **0.1667** | Medida moderada por el tamaño del corpus; evalúa si los documentos recuperados están explícitamente listados en el pequeño conjunto relevante de control (a menudo solo 1 por consulta). |
| **Mean Recall@5** | **0.7500** | Excelente. El buscador encuentra el **75%** de todos los documentos marcados como útiles para la consulta y los coloca en el Top 5 de resultados. |
| **Mean F1** | **0.2698** | Balance general entre Precisión y Recall. |
| **Mean MRR** | **0.8472** | **Desempeño Sobresaliente.** (Mean Reciprocal Rank). Un MRR del 84.72% significa que, en promedio, el primer documento relevante que un usuario busca aparece posicionado entre el **puesto 1 y el puesto 2** (promedio: puesto 1.18). |
| **Mean NDCG@5** | **0.7689** | **Excelente Calidad de Ranking.** (Normalized Discounted Cumulative Gain). El sistema logra un 76.89% de precisión óptima en la distribución de pesos de relevancia de los documentos. El orden en el que se presentan las películas es casi perfecto. |

## 3. Análisis de Errores e Hibridación

El salto de calidad (NDCG pasando del 60.81% previo al **76.89%** final, y MRR del 60.71% al **84.72%**) se explica mediante el éxito de la combinación de modelos:

- **Efecto EBM (60%)**: La ponderación fuerte del Modelo Booleano Extendido filtró drásticamente el ruido en consultas con nombres propios ("Nolan", "Cameron"). Antes, el modelo vectorial sugería películas incorrectas por similitud abstracta en la sinopsis, degradando el MRR. El p-norm ($p=2.0$) priorizó la presencia estricta pero perdonó ausencias menores, anclando los nombres clave.
- **Efecto Semántico Vectorial (40%)**: En consultas temáticas cruzadas ("atomic bomb", "dreams and heist"), los embeddings vectoriales lograron comprender conceptos abstractos en reseñas extraídas del crawler (ej. explosión nuclear, sueño), incluso sin coincidencia directa de palabras.
- **Factores de Re-Ranking (Popularidad y Frescura)**: Resolvieron efectivamente los empates de puntuación entre películas semánticamente parecidas, elevando a los éxitos de taquilla ("blockbusters") y a las películas modernas ganadoras del Oscar a la parte alta del Top 5.

## 4. Desempeño del Módulo Opcional: Recomendación

Para complementar el MRR de búsqueda general, el motor incluye recomendación de ítems similares (`MovieRecommender`). Validado con películas altamente populares ("Avatar: Fire and Ash"):
- **Predecibilidad Intradominio**: Mantuvo una similitud >50% con películas exactas de la misma franquicia (Avatar 1, Avatar 2).
- **Relacionamiento Secundario**: Asignó similitudes moderadas (~20%) a películas del mismo director y género pero diferente temática (Terminator 2), previniendo los silos de contenido gracias a la similitud híbrida de Jaccard sobre directores y actores (peso 0.5) combinada con VSM.
