import json
import re
from curl_cffi import requests
from bs4 import BeautifulSoup

def test_rt(movie_slug):
    url = f"https://www.rottentomatoes.com/m/{movie_slug}/reviews?type=top_critics"
    print("Fetching RT:", url)
    s = requests.Session(impersonate="chrome124")
    try:
        r = s.get(url, timeout=20)
        print("Status:", r.status_code)
        if r.status_code != 200:
            return
            
        text = r.text
        reviews = []
        
        # Method 1: Search for common review JSON structures (e.g. quote, originalText)
        quotes = re.findall(r'"quote":"(.*?)"', text)
        for q in quotes:
            # Decode unicode escapes like \u201c
            decoded = q.encode('utf-8').decode('unicode_escape')
            if len(decoded) > 50 and decoded not in reviews:
                reviews.append(decoded)
                
        # Method 2: Search for <rt-text> components that RT uses
        soup = BeautifulSoup(text, 'html.parser')
        rt_texts = soup.find_all('rt-text')
        for rt in rt_texts:
            t = rt.get_text(separator=' ', strip=True)
            if len(t) > 50 and t not in reviews and 'Rotten Tomatoes' not in t:
                reviews.append(t)
                
        # Method 3: Fallback conventional paragraphs
        paragraphs = soup.find_all('p')
        for p in paragraphs:
            t = p.get_text(separator=' ', strip=True)
            if len(t) > 50 and t not in reviews and 'Rotten Tomatoes' not in t and 'Newsletter' not in t:
                reviews.append(t)
                
        print(f"Found {len(reviews)} unique review texts.")
        for i, rev in enumerate(reviews[:5]):
            print(f"[{i}]", rev[:100].replace('\n', ' '))
            
    except Exception as e:
        print("Error:", e)

test_rt("oppenheimer_2023")
