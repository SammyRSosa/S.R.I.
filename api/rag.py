import os
import logging
from typing import List, Dict, Any
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class RAGManager:
    """
    Módulo de Generación Aumentada por Recuperación (RAG).
    
    Responsable de orquestar la comunicación con el LLM (Groq)
    y construir los prompts enriquecidos con contexto cinematográfico.
    """

    SYSTEM_PROMPT = """
Eres "Oscar Insight", un experto asistente especializado en el mundo del cine y los Premios Oscar.
Tu objetivo es responder preguntas de los usuarios basándote EXCLUSIVAMENTE en el contexto de películas proporcionado.

REGLAS DE RESPUESTA:
1. Usa el contexto para dar respuestas precisas y detalladas.
2. Si la información necesaria no está en el contexto, indícalo cortésmente y ofrece ayuda sobre lo que sí conoces.
3. Cita siempre los títulos de las películas y el año cuando menciones datos extraídos de ellas.
4. Mantén un tono profesional, apasionado por el cine y servicial.
5. Responde en el mismo idioma en el que el usuario te pregunte.

CONTEXTO DE PELÍCULAS RECUPERADAS:
{context}
"""

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.model = os.getenv("LLM_MODEL", "llama3-8b-8192")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", 0.2))
        
        if not self.api_key:
            logger.warning("GROQ_API_KEY no encontrada. El módulo RAG funcionará en modo degradado.")
            self.client = None
        else:
            try:
                self.client = Groq(api_key=self.api_key)
            except Exception as e:
                logger.error(f"Error al inicializar cliente Groq: {e}")
                self.client = None

    def _format_context(self, results: List[Dict[str, Any]]) -> str:
        """Convierte los resultados de búsqueda en un bloque de texto para el prompt."""
        context_blocks = []
        for i, res in enumerate(results, 1):
            block = (
                f"--- Película {i} ---\n"
                f"Título: {res.get('title')}\n"
                f"Año: {res.get('year')}\n"
                f"Director: {res.get('director', 'N/A')}\n"
                f"Reparto: {', '.join(res.get('cast', []))}\n"
                f"Géneros: {', '.join(res.get('genres', []))}\n"
                f"Score de Relevancia: {res.get('score')}\n"
                f"Resumen/Crítica: {res.get('snippet')}\n"
            )
            context_blocks.append(block)

        
        return "\n".join(context_blocks)

    def generate_response(self, query: str, retrieved_docs: List[Dict[str, Any]]) -> str:
        """
        Genera una respuesta enriquecida basada en los documentos recuperados.
        """
        if not self.client:
            return (
                "⚠️ Error de Configuración: No se ha configurado la API Key de Groq. "
                "Para habilitar las respuestas inteligentes, añade GROQ_API_KEY a tu archivo .env."
            )

        if not retrieved_docs:
            return "Lo siento, no encontré información relevante en mi base de datos para responder a esa pregunta."

        context_text = self._format_context(retrieved_docs)
        
        try:
            chat_completion = self.client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": self.SYSTEM_PROMPT.format(context=context_text),
                    },
                    {
                        "role": "user",
                        "content": query,
                    }
                ],
                model=self.model,
                temperature=self.temperature,
                max_tokens=1024,
            )
            return chat_completion.choices[0].message.content
        except Exception as e:
            logger.error(f"Error durante la generación RAG: {e}")
            return f"Lo siento, hubo un error técnico al procesar tu respuesta inteligente: {str(e)}"

# Instancia global para ser usada por la API
rag_manager = RAGManager()
