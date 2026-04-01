from curl_cffi import requests

url = "https://www.imdb.com/title/tt15398776/reviews?sort=helpfulnessScore&dir=desc&ratingFilter=0"
CHROME_HEADERS = {
    "User-Agent":                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                 "AppleWebKit/537.36 (KHTML, like Gecko) "
                                 "Chrome/124.0.0.0 Safari/537.36",
    "Accept":                    "text/html,application/xhtml+xml,application/xml;"
                                 "q=0.9,image/avif,image/webp,image/apng,*/*;"
                                 "q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language":           "en-US,en;q=0.9",
    "Accept-Encoding":           "gzip, deflate, br, zstd",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest":            "document",
    "Sec-Fetch-Mode":            "navigate",
    "Sec-Fetch-Site":            "none",
    "Sec-Fetch-User":            "?1",
    "sec-ch-ua":                 '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile":          "?0",
    "sec-ch-ua-platform":        '"Windows"',
}

session = requests.Session(impersonate="chrome124")
session.headers.update(CHROME_HEADERS)
resp = session.get(url)
print("Status:", resp.status_code)

from bs4 import BeautifulSoup
soup = BeautifulSoup(resp.text, "lxml")
reviews = soup.select("div.text.show-more__control")
print(f"Found {len(reviews)} reviews.")
for i, rev in enumerate(reviews[:3]):
    print(f"[{i}] {rev.get_text(separator=' ', strip=True)[:150]}...")
