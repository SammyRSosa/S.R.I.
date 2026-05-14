# Resultados de Evaluación y Análisis de Calidad

Este documento detalla el proceso de validación del sistema *Oscar Insight Search* mediante métricas objetivas de recuperación.

## 1. Metodología
Se utilizó un conjunto de **Ground Truth** compuesto por consultas que cubren diferentes aspectos del dominio:
- Consultas por Director/Actor.
- Consultas temáticas (ej: "atomic bomb").
- Consultas multimodales (ej: "dreams and heist").

## 2. Métricas Alcanzadas (v0.3.5)

| Métrica | Resultado | Interpretación |
| :--- | :--- | :--- |
| **P@5** | 0.1667 | Baja debido a que el Ground Truth tiene pocos docs relevantes definidos por consulta. |
| **Recall@5** | **0.7500** | El sistema encuentra la gran mayoría de lo que el usuario busca. |
| **NDCG@5** | **0.6081** | Calidad de ranking alta. Los relevantes aparecen arriba. |
| **MRR** | **0.6071** | El primer resultado relevante suele ser el 1ro o 2do. |

## 3. Análisis de Errores
- **Falsos Negativos:** En consultas muy cortas (ej: "Nolan"), el modelo vectorial a veces introduce ruido de películas con sinopsis similares pero de otros directores.
- **Efecto EBM:** El Modelo Booleano Extendido ayuda a filtrar drásticamente cuando se usan nombres propios, mejorando el MRR.

## 4. Comparativa de Modelos
Durante las pruebas, se observó que:
1.  **Solo EBM:** Alto MRR pero bajo Recall (no entiende "cine nuclear" como "atomic bomb").
2.  **Solo Vectores:** Alto Recall pero ruido en los primeros lugares (P@1 baja).
3.  **Híbrido (0.6/0.4):** Equilibrio óptimo entre precisión y cobertura semántica.
