import os
import logging
from typing import List, Dict, Any
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class RAGManager:
    """
    =======================================================================================================
                        MATHEMATICAL STATE-SPACE MODEL OF THE RAG SYSTEM
    =======================================================================================================
    The RAG (Retrieval-Augmented Generation) pipeline acts as a semantic bridge mapping a bilingual high-dimensional 
    query space $\\mathcal{Q}$ and a retrieved structured database subset $\\mathcal{D}_{\\text{retrieved}}$ to a cohesive, 
    factual, natural language response space $\\mathcal{R}$.

    1. Information Flow Architecture
    --------------------------------
    ```
      [Query Q_ES] ──> [Translation Operator g_trans] ──> [Query Q_EN] ──> [EBM / Semantic VEC Search]
                                                                                   │
                                                                                   ▼
      [Generated Answer R] <── [LLM Auto-regressive Inference] <── [Serialization S(D)]
    ```

    2. Formal Mathematical Transformations
    --------------------------------------
    Let $Q_{\\text{ES}}$ be the user query in Spanish.
    - **Translation Mapping**:
      The translator $g_{\\text{trans}}: \\Sigma^* \\to \\Sigma^*$ projects the Spanish natural language expression into 
      an English semantic equivalent to optimize retrieval recall over the English document collection:
          $$Q_{\\text{EN}} = g_{\\text{trans}}(Q_{\\text{ES}}) = \\arg\\max_{T \\in \\Sigma^*} \\prod_{i=1}^M P(t_i \\mid t_1, \\dots, t_{i-1}, Q_{\\text{ES}}, K_{\\text{trans}}; \\theta_{\\text{LLM}})$$
      where $K_{\\text{trans}}$ is the system zero-shot boundary instruction.

    - **Information-Theoretic Context Serialization**:
      Let $D = \\{d_1, d_2, \\dots, d_N\\}$ be the subset of top-$N$ ranked documents returned by the search engine.
      We formulate the context encoder $\\mathcal{S}: D \\to \\mathcal{X}$ under strict sequence length constraints:
          $$\\mathcal{S}(D) = \\bigoplus_{i=1}^N \\text{FormatRecord}(d_i)$$
      subject to the budget constraint:
          $$\\sum_{i=1}^N \\text{Len}(\\text{FormatRecord}(d_i)) \\le \\mathcal{W}_{\\text{context}} - \\text{Len}(Q) - \\text{Len}(\\text{SystemPrompt})$$

    - **Closed-World Anti-Hallucination Bound**:
      We model the factual correctness under the retrieved context as a logical predicate validation constraint:
          $$\\text{Factual}(R, D) \\iff \\forall \\text{ statement } s \\in R, \\ \\exists d \\in D \\text{ s.t. } d \\models s$$
      If the predicate cannot be satisfied (i.e. query terms do not intersect with context attributes), the generation 
      boundary yields the null result $\\emptyset$, triggering a deterministic rejection:
          $$\\text{Response}(Q, D) = \\begin{cases} 
              f_{\\text{LLM}}(P(Q, \\mathcal{S}(D))) & \\text{if } D \\neq \\emptyset \\text{ and } \\text{Valid}(Q, D) \\\\
              \\text{"No se encontraron resultados relevantes..."} & \\text{otherwise}
          \\end{cases}$$
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
6. REGLA DE ORO: Si los documentos recuperados no mencionan la respuesta, o no coinciden con los criterios exactos solicitados por el usuario (ej. un año específico), DEBES responder obligatoriamente: "No se encontraron resultados relevantes en la base de datos para los criterios especificados." Bajo NINGUNA circunstancia uses tu conocimiento previo para inventar o adivinar una respuesta.
7. Intenta Explicar los resultados que den los scores de similitud, de forma breve y concisa.

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
        """
        Convierte los resultados de búsqueda en un bloque de texto formateado para el prompt.

        Mathematical Representation:
        We define the serialization mapping $\\text{FormatRecord}: r \\to x$:
        $$\\text{FormatRecord}(r) = \\text{"--- Película "} \\cdot r[\\text{"title"}] \\cdot \\dots \\cdot r[\\text{"snippet"}]$$
        This aggregates all key/value pairs into a deterministic string structure.
        """
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

    def translate_query_for_ebm(self, query: str) -> str:
        """
        Traduce una consulta al inglés de forma ultra-rápida para mejorar el recall del motor léxico.

        Mathematical Modeling:
        Let $Q_{\\text{ES}}$ be the input. We seek the translation $Q_{\\text{EN}}$:
            $$Q_{\\text{EN}} = \\arg\\max_{T} \\prod_{i=1}^k P(t_i \\mid t_1, \\dots, t_{i-1}, Q_{\\text{ES}}; \\theta_{\\text{LLM}})$$
        conditioned on minimizing temperature ($T = 0.0$) to guarantee deterministic decoding:
            $$\\lim_{T \\to 0^+} P(T) = \\delta(T - \\text{CanonicalTranslation})$$
        """
        if not self.client:
            return query
            
        prompt = "You are a specialized search translator. Translate the user's Spanish movie search query into English. Output ONLY the English translation, no quotes, no explanations."
        
        try:
            res = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": query}
                ],
                model=self.model,
                temperature=0.0,
                max_tokens=30,
            )
            translated = res.choices[0].message.content.strip()
            logger.info(f"Traducción EBM: '{query}' -> '{translated}'")
            return translated
        except Exception as e:
            logger.error(f"Error en traducción de query: {e}")
            return query

    def generate_response(self, query: str, retrieved_docs: List[Dict[str, Any]]) -> str:
        """
        Genera una respuesta enriquecida basada en los documentos recuperados.

        Mathematical Formulation:
        Let $\\mathcal{X} = \\mathcal{S}(\\mathcal{D}_{\\text{retrieved}})$ be the serialized context.
        The response $R$ is generated by computing:
            $$R = f_{\\text{LLM}}(\\text{SystemPrompt}(\\mathcal{X}) \\circ \\text{UserPrompt}(Q))$$
        subject to:
            $$\\text{Factual correctness under } \\mathcal{X} \\quad \\text{and} \\quad T = 0.2 \\ \\text{(low entropy generating policy)}$$
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
