import logging
from typing import List, Dict, Any
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

class WebSearchModule:
    """
    Módulo de Búsqueda Web Fallback (Corte 2).
    
    Permite ampliar la búsqueda a internet cuando la base de datos local
    no tiene suficientes resultados relevantes.
    """

    def __init__(self, max_results: int = 5):
        self.max_results = max_results

    def search_and_format(self, query: str) -> List[Dict[str, Any]]:
        """
        Realiza una búsqueda en la web y formatea los resultados para que sean
        compatibles con el motor RAG.
        """
        logger.info(f"Disparando búsqueda web fallback para: '{query}'")
        results = []
        
        try:
            with DDGS() as ddgs:
                # Limitamos la búsqueda a sitios de cine para mayor calidad si es posible,
                # o simplemente hacemos la query abierta.
                search_query = f"{query} movie film oscars"
                ddg_results = ddgs.text(search_query, max_results=self.max_results)
                
                for i, r in enumerate(ddg_results):
                    results.append({
                        "doc_id": 9000 + i, # IDs virtuales para resultados web
                        "title": r.get("title", "Resultado Web"),
                        "year": "N/A",
                        "score": 0.5, # Score base para resultados web
                        "ebm_score": 0.0,
                        "vector_score": 0.5,
                        "snippet": r.get("body", "") + f" (Fuente: {r.get('href')})",
                        "is_web_result": True
                    })
        except Exception as e:
            logger.error(f"Error en búsqueda web DuckDuckGo: {e}")
            
        return results

# Instancia global
web_searcher = WebSearchModule()
