import re
from curl_cffi import requests

class RTScraper:
    def __init__(self):
        self.session = requests.Session(impersonate="chrome124")

    def get_reviews(self, title: str, year: int) -> list:
        slug = f"{title.lower().replace(' ', '_')}"
        if year:
            slug += f"_{year}"
        url = f"https://www.rottentomatoes.com/m/{slug}/reviews"
        print("Scraping:", url)
        r = self.session.get(url)
        if r.status_code != 200:
            print("Failed RT Request:", r.status_code)
            return []
            
        matches = re.findall(r'"quote":"(.*?)"', r.text)
        reviews = []
        for m in sorted(set(matches), key=lambda x: -len(x)):
            # filter out very short strings
            text = m.encode('raw_unicode_escape').decode('unicode_escape')
            if len(text) > 40 and "http" not in text and text not in reviews:
                reviews.append(text)
                
        return reviews[:10]

s = RTScraper()
revs = s.get_reviews("Oppenheimer", 2023)
for r in revs:
    print("-", r)
