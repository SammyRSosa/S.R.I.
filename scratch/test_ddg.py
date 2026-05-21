import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from duckduckgo_search import DDGS

with DDGS() as ddgs:
    try:
        res = list(ddgs.text("who won oscar for best film in 1987", max_results=5))
        print("Query: 'who won oscar for best film in 1987'")
        print(f"Results count: {len(res)}")
        for r in res:
            print(f"Title: {r.get('title')}\nHref: {r.get('href')}\nBody: {r.get('body')}\n")
    except Exception as e:
        print("Error: ", e)

    try:
        res2 = list(ddgs.text("who won oscar for best film in 1987 Academy Awards movie film wikipedia", max_results=5))
        print("Query: 'who won oscar for best film in 1987 Academy Awards movie film wikipedia'")
        print(f"Results count: {len(res2)}")
        for r in res2:
            print(f"Title: {r.get('title')}\nHref: {r.get('href')}\nBody: {r.get('body')}\n")
    except Exception as e:
        print("Error: ", e)
