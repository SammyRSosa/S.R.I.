"""
scripts/test_search.py
Test script for the Hybrid Search API (EBM + Vectors).
"""

import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_root():
    print("Testing Root...")
    r = requests.get(f"{BASE_URL}/")
    print(r.status_code, r.json())

def test_search(query):
    print(f"\nTesting Search: '{query}'")
    payload = {
        "query": query,
        "top_k": 5,
        "p": 2.0
    }
    r = requests.post(f"{BASE_URL}/search", json=payload)
    if r.status_code == 200:
        data = r.json()
        print(f"Total results: {data['total_results']}")
        for i, res in enumerate(data['results'], 1):
            print(f"[{i}] {res['title']} ({res['year']}) - Score: {res['score']}")
            print(f"    EBM: {res['ebm_score']} | Vector: {res['vector_score']}")
            print(f"    Snippet: {res['snippet']}\n")
    else:
        print(f"Error {r.status_code}: {r.text}")

if __name__ == "__main__":
    try:
        test_root()
        test_search("Christopher Nolan masterpiece")
        test_search("funny animated movie for kids")
        test_search("Oppenheimer AND nuclear")
    except Exception as e:
        print(f"Connection error: {e}. Is the server running? (uvicorn api.main:app)")
