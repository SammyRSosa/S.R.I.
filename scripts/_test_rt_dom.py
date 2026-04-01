from curl_cffi import requests
from bs4 import BeautifulSoup

url2 = "https://www.rottentomatoes.com/m/oppenheimer_2023/reviews?type=top_critics"
session = requests.Session(impersonate="chrome124")
resp2 = session.get(url2)
soup = BeautifulSoup(resp2.text, "lxml")

print("RT Movie Status:", resp2.status_code)
# Let's inspect review elements
for tag in soup.find_all(True):
    cls = ' '.join(tag.get('class', []))
    txt = tag.get_text(strip=True)
    if 50 < len(txt) < 300 and cls:
        print(f"<{tag.name} class='{cls}'> {txt[:50]}")
