import logging
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

# Add parent to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from curl_cffi.requests import Session
from bs4 import BeautifulSoup

s = Session(impersonate="chrome124")
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
})

# Let's perform a search on Metacritic
query = "oppenheimer"
search_url = f"https://www.metacritic.com/search/{query}/"
print(f"Fetching search page: {search_url}")

r = s.get(search_url, timeout=20)
print(f"Status code: {r.status_code}")

if r.status_code == 200:
    soup = BeautifulSoup(r.text, 'lxml')
    print("Finding all 'a' links...")
    links = soup.find_all('a', href=True)
    print(f"Found {len(links)} links in total.")
    
    movie_links = []
    for link in links:
        href = link['href']
        # Resolve relative URLs
        absolute_url = urljoin(search_url, href)
        parsed_url = urlparse(absolute_url)
        
        # Analyze if internal
        is_internal = "metacritic.com" in parsed_url.netloc
        
        if is_internal and "/movie/" in parsed_url.path:
            movie_links.append((link.get_text(strip=True), href, absolute_url))
            
    print(f"Found {len(movie_links)} movie-related links:")
    for txt, href, abs_url in movie_links[:20]:
        print(f"Text: {txt!r} | href: {href!r} | absolute: {abs_url!r}")
else:
    print(f"Failed to fetch search page: {r.text[:500]}")
