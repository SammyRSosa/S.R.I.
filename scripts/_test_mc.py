import re
from curl_cffi import requests
from bs4 import BeautifulSoup

url = "https://www.metacritic.com/movie/oppenheimer/user-reviews/"
s = requests.Session(impersonate="chrome124")
r = s.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"})

print("Metacritic Request Status:", r.status_code)
if r.status_code == 200:
    soup = BeautifulSoup(r.text, 'lxml')
    reviews = []
    
    # In Metacritic, reviews are usually inside divs with class 'review_body' or 'c-siteReview'
    for tag in soup.find_all('div'):
        cls = ' '.join(tag.get('class', []))
        if 'c-siteReview_quote' in cls or 'review_body' in cls or 'c-siteReview' in cls:
            text = tag.get_text(separator=' ', strip=True)
            if len(text) > 50:
                reviews.append(text)
                
    # Also let's just print top 10 long divs to inspect classes
    all_divs = []
    for d in soup.find_all('div'):
        txt = d.get_text(separator=' ', strip=True)
        if 100 < len(txt) < 500:
            all_divs.append((d.get('class', []), txt[:100]))
            
    print(f"Found {len(reviews)} reviews with typical classes.")
    print("Sample typical classes texts:")
    for text in reviews[:2]: print('-', text[:100])
    
    print("\nSample top long divs:")
    for cls, txt in all_divs[:5]:
        print(cls, txt)
        
