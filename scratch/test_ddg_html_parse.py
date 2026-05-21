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
    results = []
    # In html.duckduckgo.com, each result is inside a div with class 'result' or 'web-result'
    # Let's inspect the divs
    result_divs = soup.find_all("div", class_="result")
    print(f"Found {len(result_divs)} result divs")
    for div in result_divs[:5]:
        title_a = div.find("a", class_="result__snippet")
        # Wait, the title link is usually result__a or result__url or within result__title
        title_el = div.find("a", class_="result__a")
        snippet_el = div.find("a", class_="result__snippet")
        if title_el:
            href = title_el.get("href")
            title = title_el.get_text().strip()
            snippet = snippet_el.get_text().strip() if snippet_el else ""
            print(f"Title: {title}\nHref: {href}\nSnippet: {snippet}\n")
            results.append({"title": title, "href": href, "body": snippet})
else:
    print("Failed to fetch")
