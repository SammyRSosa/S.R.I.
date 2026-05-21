import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from duckduckgo_search import DDGS

with DDGS() as ddgs:
    queries = [
        "1987 Academy Awards winner best movie",
        "Platoon 1987 Academy Awards",
        "who won oscar 1987",
        "best picture oscar 1987",
    ]
    for q in queries:
        print(f"--- QUERY: {q} ---")
        try:
            res = list(ddgs.text(q, max_results=3))
            print(f"Results: {len(res)}")
            for r in res:
                print(f"  {r.get('title')} ({r.get('href')})")
        except Exception as e:
            print("  Error:", e)
