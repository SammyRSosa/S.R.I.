import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from database.store import DocumentStore
from indexer.inverted_index import InvertedIndex
from indexer.ebm import ExtendedBooleanModel
from indexer.recommender import MovieRecommender

def main():
    store = DocumentStore()
    idx = InvertedIndex()
    
    print(f"Cargando {len(store.documents)} documentos...")
    for doc_id, data in store.documents.items():
        idx.add_film(doc_id, data)
        
    ebm = ExtendedBooleanModel(store, idx, p=2.0)
    recommender = MovieRecommender(store, ebm)
    
    # Buscar una película conocida para probar
    test_id = None
    for doc_id, film in store.documents.items():
        title = film.get("title", "")
        if "Oppenheimer" in title or "Inception" in title or "Avatar" in title:
            test_id = doc_id
            print(f"\nPelícula semilla encontrada: ID {doc_id} -> {title} ({film.get('year')})")
            print(f"Director: {film.get('director') or film.get('metadata', {}).get('director')}")
            print(f"Géneros: {film.get('genres') or film.get('metadata', {}).get('genres')}")
            break
            
    if test_id is None:
        # Fallback al primer doc_id disponible
        test_id = list(store.documents.keys())[0]
        film = store.documents[test_id]
        print(f"\nPelícula semilla fallback: ID {test_id} -> {film.get('title')} ({film.get('year')})")
        
    print("\nGenerando recomendaciones...")
    recs = recommender.recommend(test_id, top_k=5)
    
    print("\nRecomendaciones encontradas:")
    for i, rec in enumerate(recs, 1):
        print(f"{i}. ID {rec['doc_id']}: {rec['title']} ({rec['year']})")
        print(f"   Similitud: {rec['similarity']:.4f} (VSM: {rec['cosine_similarity']:.4f} | Meta: {rec['metadata_similarity']:.4f})")
        print(f"   Director: {rec['director']} | Géneros: {', '.join(rec['genres'])}")

if __name__ == "__main__":
    main()
