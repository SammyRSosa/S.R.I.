import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
from crawler.tmdb_client import TmdbClient

client = TmdbClient(api_key="b2119ca4292283dc53299bdf3c3998db")

# Estrategia A
films = client.discover_movies(page=1, strategy="popularity")
print(f"Estrategia A - pagina 1: {len(films)} peliculas")
for f in films[:5]:
    print(f"  {f['title']} ({f['year']}) | votes={f['vote_count']} | avg={f['vote_average']}")

# Detalles Oppenheimer
print()
details = client.get_movie_details(872585)
print("Oppenheimer details:")
print(f"  director: {details['director']}")
print(f"  cast: {details['cast'][:4]}")
print(f"  genres: {details['genres']}")
print(f"  imdb_id: {details['imdb_id']}")
print(f"  budget: {details['budget']:,}")
print(f"  revenue: {details['revenue']:,}")
print(f"  tagline: {details['tagline']}")
print(f"  overview (100c): {details['overview'][:100]}")

# Estrategia B
print()
films_b = client.discover_movies(page=1, strategy="quality")
print(f"Estrategia B - pagina 1: {len(films_b)} peliculas")
for f in films_b[:5]:
    print(f"  {f['title']} ({f['year']}) | votes={f['vote_count']} | avg={f['vote_average']}")
