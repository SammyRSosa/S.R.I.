import re
from curl_cffi import requests

s = requests.Session(impersonate="chrome124")
r = s.get("https://www.rottentomatoes.com/m/oppenheimer_2023/reviews")

if r.status_code == 200:
    # Try finding emsId
    m = re.search(r'"emsId":"(.*?)"', r.text)
    m2 = re.search(r'data-ems-id="(.*?)"', r.text)
    emsId = (m and m.group(1)) or (m2 and m2.group(1))
    print("EMS ID:", emsId)
    
    if emsId:
        # Example API URLs RT sometimes uses
        apis = [
            f"https://www.rottentomatoes.com/napi/movie/{emsId}/reviews/all",
            f"https://www.rottentomatoes.com/napi/movie/{emsId}/criticsReviews/all",
            f"https://www.rottentomatoes.com/api/private/v2.0/browse?limit=20&type=movie-reviews&id={emsId}"
        ]
        for a in apis:
            print("Trying:", a)
            ra = s.get(a)
            print("Status:", ra.status_code)
            if ra.status_code == 200:
                print(ra.text[:200])

    # Another approach: find all JSONs in script tags
    print("\nScript JSONs with reviews:")
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, 'lxml')
    for script in soup.find_all('script'):
        if script.string and 'review' in script.string.lower() and len(script.string) > 200:
            print("Found script of length", len(script.string))
            if "quote" in script.string:
                print("Contains 'quote'")
                
