# Módulo RAG (Retrieval-Augmented Generation)

Este módulo implementa la capacidad de generar respuestas enriquecidas y contextuales utilizando modelos de lenguaje de gran tamaño (LLM), integrando los resultados recuperados por el motor híbrido (EBM + Vectorial).

## 1. Arquitectura del Módulo
El sistema RAG sigue el patrón estándar de tres etapas:

1.  **Retrieval (Recuperación):** El motor híbrido busca en el corpus local de ~1,600 películas los documentos más relevantes para la consulta del usuario.
2.  **Augmentation (Aumentación):** Se extraen los metadatos y fragmentos de texto (sinopsis, críticas) de los documentos recuperados y se inyectan en un *System Prompt* cuidadosamente diseñado.
3.  **Generation (Generación):** Se envía el prompt enriquecido a un LLM (vía Groq o local) para generar una respuesta en lenguaje natural que sintetice la información.

## 2. Componentes Técnicos

### 2.1 Prompt Engineering
El sistema utiliza un prompt estructurado para guiar al modelo. El prompt define:
- **Rol:** Experto en cine y los Premios Oscar.
- **Contexto:** Información técnica de las películas recuperadas (título, año, director, sinopsis).
- **Restricciones:** No inventar información fuera del contexto, citar las películas mencionadas y mantener un tono profesional.

### 2.2 Integración con Groq / Llama 3
Para garantizar velocidad y calidad, se utiliza la API de **Groq** con el modelo **Llama 3 (8b o 70b)**. La comunicación se realiza mediante el cliente oficial de `groq`.

## 3. Flujo de Datos
1. El usuario envía una pregunta (ej: "¿Qué películas de Christopher Nolan han ganado Oscars?").
2. `api/main.py` invoca al `RAGManager`.
3. El `RAGManager` ejecuta una búsqueda híbrida y obtiene el `top_k` de películas.
4. Se construye el mensaje para el LLM:
   ```text
   Contexto:
   1. Oppenheimer (2023) - Dir: Christopher Nolan. Sinopsis: ...
   2. Inception (2010) - Dir: Christopher Nolan. Sinopsis: ...
   
   Pregunta: ¿Qué películas de Christopher Nolan han ganado Oscars?
   ```
5. El LLM responde basándose estrictamente en los datos proporcionados.

## 4. Configuración
- **Provider:** Groq (Default) / OpenAI Compatible.
- **Model:** `llama3-8b-8192`.
- **Temperatura:** 0.2 (para reducir alucinaciones).

---