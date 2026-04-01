from curl_cffi import requests
from bs4 import BeautifulSoup

# Rotten Tomatoes search
url = "https://www.rottentomatoes.com/search?search=Oppenheimer"
session = requests.Session(impersonate="chrome124")
resp = session.get(url)
print("RT Search Status:", resp.status_code)

# Let's try to get movie directly if we know the slug
url2 = "https://www.rottentomatoes.com/m/oppenheimer_2023/reviews?type=top_critics"
resp2 = session.get(url2)
print("RT Movie Status:", resp2.status_code)

if resp2.status_code == 200:
    soup = BeautifulSoup(resp2.text, "lxml")
    reviews = soup.select('p[data-qa="review-quote"]')
    print(f"Found {len(reviews)} reviews.")
    for i, rev in enumerate(reviews[:3]):
        print(f"[{i}] {rev.get_text(separator=' ', strip=True)[:150]}...")
