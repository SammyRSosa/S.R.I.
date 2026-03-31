"""Debug compacto: trace del _resolve_film_url paso a paso."""
import sys, time, random, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

import cloudscraper
from bs4 import BeautifulSoup

s = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "windows", "desktop": True},
    delay=10,
)
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://letterboxd.com/",
})

# Warmup
print("--- WARMUP ---")
r = s.get("https://letterboxd.com/", timeout=20, allow_redirects=True)
print(f"Homepage: {r.status_code} | cookies: {dict(s.cookies)}")
time.sleep(random.uniform(2, 3))

# IMDb redirect
print("\n--- IMDb redirect ---")
r2 = s.get("https://letterboxd.com/imdb/tt15398776/", timeout=20, allow_redirects=True)
print(f"Status: {r2.status_code} | Final URL: {r2.url}")
print(f"'/film/' in url: {'/film/' in r2.url}")
time.sleep(random.uniform(2, 3))

if "/film/" in r2.url:
    film_url = r2.url.rstrip("/") + "/"
    reviews_url = film_url + "reviews/by/popularity/"
    print(f"\n--- Reviews: {reviews_url} ---")
    r3 = s.get(reviews_url, timeout=20, allow_redirects=True)
    print(f"Status: {r3.status_code} | Final URL: {r3.url}")
    soup = BeautifulSoup(r3.text, "lxml")
    divs = soup.find_all("div", class_=lambda c: c and "body-text" in c)
    print(f"body-text divs: {len(divs)}")
    for d in divs[:3]:
        text = d.get_text(separator=" ", strip=True)
        print(f"  [{len(text)}c] {text[:120]}")
