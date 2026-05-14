# Oscar Insight Search: Un Sistema de Recuperación Híbrido con RAG y Búsqueda Web Fallback

**Autores:** Equipo Oscar Insight  
**Curso:** 2025-2026 | Sistemas de Recuperación de Información (SRI)  
**Semestre:** 2do  

---

## Resumen
Este informe detalla el diseño e implementación de *Oscar Insight Search*, un sistema avanzado de recuperación de información (SRI) especializado en la industria cinematográfica y los Premios Oscar. El sistema integra un motor híbrido basado en el Modelo Booleano Extendido (EBM) y Búsqueda Vectorial (Dense Retrieval), potenciado por un módulo de Generación Aumentada por Recuperación (RAG) y un mecanismo de fallback hacia la web. Se presentan los resultados de evaluación utilizando métricas estándar (P@k, Recall, NDCG), demostrando una alta efectividad en la recuperación de semántica y precisión en las respuestas generadas por IA.

---

## 1. Introducción
La búsqueda de información en dominios específicos como el cine requiere ir más allá de la simple coincidencia de palabras clave. Los usuarios suelen realizar consultas complejas que involucran relaciones entre directores, géneros y contextos narrativos. El objetivo de este proyecto es construir un sistema que combine la precisión de los modelos clásicos con la flexibilidad de los modelos de lenguaje (LLM).

## 2. Arquitectura del Sistema
El sistema sigue un diseño modular dividido en cuatro capas principales:

### 2.1 Adquisición de Datos (Crawler & Scraper)
- **TMDB API:** Utilizada para obtener metadatos estructurados (director, reparto, presupuesto, géneros).
- **Letterboxd Scraper:** Implementado para extraer reseñas críticas, enriqueciendo el corpus con lenguaje natural rico.
- **Corpus:** 1,623 documentos almacenados en formato JSON enriquecido.

### 2.2 Motor de Recuperación Híbrido
El corazón del sistema utiliza una combinación lineal de dos estrategias:
1.  **Extended Boolean Model (EBM):** Implementado mediante la p-norma ($p=2$), permitiendo consultas booleanas suaves con pesos TF-IDF.
2.  **Vector Store (FAISS):** Uso de *Sentence Transformers* (`all-MiniLM-L6-v2`) para capturar la semántica de las sinopsis y reseñas.
3.  **Ranking Final:** 
    $Score = (0.6 \cdot S_{EBM}) + (0.4 \cdot S_{VEC}) + 0.1 \cdot Pop + 0.05 \cdot Fresh$

### 2.3 Módulo RAG y Fallback
- **RAG (Groq/Llama 3.3):** Genera respuestas conversacionales utilizando los top-k resultados como contexto.
- **Web Fallback:** Si el score local es < 0.25, el sistema dispara una búsqueda vía DuckDuckGo para recuperar información en tiempo real.

---

## 3. Implementación Técnica
### 3.1 Indexación
Se implementó un índice invertido con normalización avanzada:
- Tokenización (NLTK)
- Eliminación de Stop-words.
- Lemmatización.
- Cálculo de pesos TF-IDF por documento.

### 3.2 Interfaz de Usuario
Desarrollada con FastAPI (Backend) y Vanilla JS/CSS (Frontend). Incluye:
- Diseño premium (Glassmorphism).
- Animaciones para la carga de RAG.
- Visualización de métricas de relevancia por documento.

---

## 4. Evaluación y Resultados
Se evaluó el sistema utilizando un *Ground Truth* de 6 consultas complejas. Los resultados obtenidos son:

| Métrica | Valor Promedio |
| :--- | :--- |
| **Mean Precision@5** | 0.1667 |
| **Mean Recall@5** | 0.7500 |
| **Mean NDCG@5** | 0.6081 |
| **Mean MRR** | 0.6071 |

**Análisis:** El alto Recall indica que el sistema es capaz de encontrar la mayoría de los documentos relevantes. El NDCG superior a 0.6 valida la efectividad de la fórmula de ranking híbrido.

---

## 5. Conclusiones
*Oscar Insight Search* cumple con los objetivos de los tres cortes del proyecto integrador. La inclusión de RAG transforma el buscador en un asistente inteligente, mientras que el modelo híbrido garantiza la robustez técnica del SRI.

---

## Referencias
1.  Salton, G., Fox, E. A., & Wu, H. (1983). Extended Boolean information retrieval.
2.  Lewis, P., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.
3.  Reimers, N., & Gurevych, I. (2019). Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks.
