import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from duckduckgo_search import DDGS

with DDGS() as ddgs:
    print("Testing 'lite' backend:")
    try:
        res = list(ddgs.text("who won oscar for best movie in 1987", max_results=5, backend="lite"))
        for r in res:
            print(f"Title: {r.get('title')}\nHref: {r.get('href')}\nBody: {r.get('body')}\n")
    except Exception as e:
        print("Error 'lite':", e)

    print("\nTesting 'html' backend:")
    try:
        res = list(ddgs.text("who won oscar for best movie in 1987", max_results=5, backend="html"))
        for r in res:
            print(f"Title: {r.get('title')}\nHref: {r.get('href')}\nBody: {r.get('body')}\n")
    except Exception as e:
        print("Error 'html':", e)

    print("\nTesting 'api' backend:")
    try:
        res = list(ddgs.text("who won oscar for best movie in 1987", max_results=5, backend="api"))
        for r in res:
            print(f"Title: {r.get('title')}\nHref: {r.get('href')}\nBody: {r.get('body')}\n")
    except Exception as e:
        print("Error 'api':", e)
