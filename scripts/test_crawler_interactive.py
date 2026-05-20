import sys
from pathlib import Path

# Agregar raíz del proyecto a sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from crawler.web_search import WebSearchModule

def main():
    print("=" * 60)
    print("  PROBADOR INTERACTIVO DEL NUEVO CRAWLER VECTORIAL")
    print("=" * 60)
    print("Este probador realiza búsquedas reales en DuckDuckGo, descárga")
    print("las páginas de forma concurrente, genera chunks de texto e")
    print("inicializa un índice FAISS temporal en memoria en caliente.")
    print("=" * 60)
    
    module = WebSearchModule(max_results=3)
    
    while True:
        try:
            query = input("\nIntroduce una consulta de búsqueda (o 'salir' para finalizar): ").strip()
            if not query:
                continue
            if query.lower() in ["salir", "exit", "quit"]:
                print("¡Adiós!")
                break
                
            print(f"\n🔍 Procesando consulta: '{query}'...")
            results = module.search_and_format(query)
            
            print("\n" + "=" * 50)
            print(f"🎯 RESULTADOS DEL CRAWLER VECTORIAL ({len(results)} matches)")
            print("=" * 50)
            
            for i, res in enumerate(results, 1):
                print(f"\n[{i}] {res['title']} (Puntaje Vectorial: {res['vector_score']})")
                print("-" * 50)
                # Formatear el snippet para que sea agradable de leer
                snippet = res['snippet']
                if len(snippet) > 300:
                    snippet = snippet[:300] + "..."
                print(f"📄 Fragmento:\n{snippet}")
                print("=" * 50)
                
        except KeyboardInterrupt:
            print("\n¡Búsqueda cancelada! Saliendo...")
            break
        except Exception as e:
            print(f"\n❌ Ocurrió un error en la ejecución: {e}")

if __name__ == "__main__":
    main()
