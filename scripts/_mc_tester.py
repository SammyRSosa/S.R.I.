from curl_cffi import requests
from bs4 import BeautifulSoup

url = "https://www.metacritic.com/movie/oppenheimer/user-reviews/"
r = requests.Session(impersonate="chrome124").get(url)
soup = BeautifulSoup(r.text, 'lxml')

reviews = soup.select('div.c-siteReview_quote span')
print("Found quote spans:", len(reviews))

filtered = []
for rev in reviews:
    text = rev.get_text(separator=' ', strip=True)
    if 50 < len(text) < 3000 and "Expand" not in text:
        filtered.append(text)

print(f"Filtered to {len(filtered)} reviews.")
for i, f in enumerate(filtered[:5]):
    print(f"[{i}] {f[:100]}")
    
if not filtered:
    # Let's check general text areas
    for d in soup.find_all('div', class_=lambda c: c and 'review' in c.lower() and 'quote' in c.lower()):
        print("Fallback DIV:", d.get_text(strip=True)[:100])
