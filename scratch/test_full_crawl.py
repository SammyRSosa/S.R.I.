import logging
import sys
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import Optional

# Add parent to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from curl_cffi.requests import Session
from bs4 import BeautifulSoup

def slugify(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_ = nfkd.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9\s-]", "", ascii_.lower())
    return re.sub(r"\s+", "-", slug.strip())

def is_movie_match(url_path: str, link_text: str, target_title: str, target_year: Optional[int]) -> bool:
    target_slug = slugify(target_title)
    path_parts = [p for p in url_path.split('/') if p]
    if not path_parts or path_parts[0] != "movie":
        return False
    
    url_slug = path_parts[1] if len(path_parts) > 1 else ""
    if not url_slug:
        return False
        
    # Standard clean slugs
    if url_slug == target_slug:
        return True
        
    # Substring matching
    if target_slug in url_slug or url_slug in target_slug:
        if target_year:
            if str(target_year) in url_slug or str(target_year) in link_text:
                return True
        return True
        
    return False

s = Session(impersonate="chrome124")
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
})

# Let's perform a search on Metacritic for Oppenheimer (2023)
target_title = "Oppenheimer"
target_year = 2023

search_query = slugify(target_title)
search_url = f"https://www.metacritic.com/search/{search_query}/"
print(f"1. Seed URL: {search_url}")

r = s.get(search_url, timeout=20)
if r.status_code != 200:
    print(f"Failed to fetch search page: {r.status_code}")
    sys.exit(1)

soup = BeautifulSoup(r.text, 'lxml')
links = soup.find_all('a', href=True)

movie_url = None
for link in links:
    href = link['href']
    abs_url = urljoin(search_url, href)
    parsed = urlparse(abs_url)
    
    # Domain Analysis (Carlos's check)
    is_internal = "metacritic.com" in parsed.netloc
    if not is_internal:
        continue # choosing not to exit the domain
        
    # Path Analysis
    if is_movie_match(parsed.path, link.get_text(strip=True), target_title, target_year):
        movie_url = abs_url
        print(f"2. Found movie details page URL: {movie_url}")
        break

if not movie_url:
    print("Failed to find movie page in search results.")
    # Fallback to direct candidate slug
    movie_url = f"https://www.metacritic.com/movie/{slugify(target_title)}/"
    print(f"Fallback to direct slug: {movie_url}")

# Fetch movie details page
print(f"3. Fetching movie details page: {movie_url}")
r_details = s.get(movie_url, timeout=20)
if r_details.status_code != 200:
    print(f"Failed to fetch movie details page: {r_details.status_code}")
    sys.exit(1)

soup_details = BeautifulSoup(r_details.text, 'lxml')
details_links = soup_details.find_all('a', href=True)

user_reviews_url = None
for link in details_links:
    href = link['href']
    abs_url = urljoin(movie_url, href)
    parsed = urlparse(abs_url)
    
    # Domain Analysis
    is_internal = "metacritic.com" in parsed.netloc
    if not is_internal:
        continue
        
    # Check for user-reviews
    if "/user-reviews/" in parsed.path or parsed.path.endswith("/user-reviews"):
        user_reviews_url = abs_url
        print(f"4. Found User Reviews URL: {user_reviews_url}")
        break

if not user_reviews_url:
    print("User reviews URL not found in movie details page.")
    # Fallback to direct construction relative to the movie URL
    user_reviews_url = urljoin(movie_url, "user-reviews/")
    print(f"Fallback: {user_reviews_url}")

# Fetch user reviews
print(f"5. Fetching user reviews: {user_reviews_url}")
r_reviews = s.get(user_reviews_url, timeout=20)
if r_reviews.status_code == 200:
    print("Successfully fetched user reviews page!")
    # Parse reviews
    soup_rev = BeautifulSoup(r_reviews.text, 'lxml')
    reviews = []
    for tag in soup_rev.find_all("span"):
        text = tag.get_text(separator=" ", strip=True)
        if 100 < len(text) < 3000 and "Expand" not in text and "metacritic" not in text.lower():
            reviews.append(text)
    print(f"Scraped {len(reviews)} reviews.")
    for i, rev in enumerate(reviews[:3], 1):
        print(f"  [{i}] {rev[:100]}...")
else:
    print(f"Failed to fetch user reviews page: {r_reviews.status_code}")
