import json
from curl_cffi import requests

imdb_id = "tt15398776"
url = "https://caching.graphql.imdb.com/"
query = {
    "query": "query Reviews($titleId: ID!) { title(id: $titleId) { reviews(first: 10) { edges { node { text { originalText } } } } } }",
    "variables": {"titleId": imdb_id}
}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Content-Type": "application/json"
}

try:
    s = requests.Session(impersonate="chrome124")
    r = s.post(url, json=query, headers=headers)
    print("GraphQL Status:", r.status_code)
    try:
        data = r.json()
        reviews = data.get("data", {}).get("title", {}).get("reviews", {}).get("edges", [])
        print(f"Found {len(reviews)} reviews via GraphQL")
        for rev in reviews[:2]:
            text = rev.get("node", {}).get("text", {}).get("originalText", "")
            print("-", text[:100].replace("\n", " "))
    except Exception as e:
        print("Error parsing json:", str(e))
        print(r.text[:500])
except Exception as e:
    print("Exception:", str(e))
