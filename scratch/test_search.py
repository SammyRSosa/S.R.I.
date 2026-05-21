import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import requests

queries = [
    "who won oscar for best film in 1987",
    "who won oscar for best movie in 2016",
    "who won the Oscar for best picture in 2023",
    "best romantic comedy 2005",
]

for q in queries:
    print(f"\n{'='*60}")
    print(f"QUERY: {q}")
    print('='*60)
    r = requests.post('http://127.0.0.1:8000/search', json={'query': q, 'top_k': 5})
    d = r.json()
    print(f"Total: {d['total_results']} | Web: {d['was_web_search']}")
    for x in d['results']:
        tag = "[WEB]" if x['is_web_result'] else "[LOCAL]"
        print(f"  {tag} {x['title']} ({x['year']}) EBM:{x['ebm_score']:.3f} VEC:{x['vector_score']:.3f} Final:{x['score']:.3f}")
