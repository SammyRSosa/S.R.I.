import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import requests
from bs4 import BeautifulSoup

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

url = "https://html.duckduckgo.com/html/"
params = {"q": "who won oscar for best movie in 1987"}

r = requests.post(url, data=params, headers=headers)
print("Status code:", r.status_code)
if r.status_code == 200:
    soup = BeautifulSoup(r.text, "html.parser")
    results = soup.find_all("a", class_="result__url")
    print(f"Found {len(results)} results")
    for a in results[:5]:
        href = a.get("href")
        title = a.get_text().strip()
        print(f"- {title} ({href})")
else:
    print("Failed to fetch")
