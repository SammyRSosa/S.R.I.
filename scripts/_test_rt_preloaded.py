import re
import json
from curl_cffi import requests

imdb_id = "tt15398776"
url = f"https://www.imdb.com/title/{imdb_id}/reviews"

s = requests.Session(impersonate="chrome120")
r = s.get(url)
print("IMDb Request Status:", r.status_code)

if r.status_code == 200:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(r.text, 'lxml')
    reviews = soup.select('div.text.show-more__control')
    for rev in reviews[:3]:
        print("-", rev.get_text(separator=' ', strip=True)[:100])
else:
    # Rotten Tomatoes
    print("Trying Rotten tomatoes via search...")
    rt_s = requests.Session(impersonate="chrome120")
    rt_res = rt_s.get("https://www.rottentomatoes.com/m/oppenheimer_2023/reviews?type=top_critics")
    print("RT Request Status:", rt_res.status_code)
    
    match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(.*);', rt_res.text)
    if match:
        try:
            data = json.loads(match.group(1))
            print("Found PRELOADED_STATE!")
            print("Keys:", data.keys())
        except Exception as e:
            print("JSON ERROR", str(e))
    else:
        # Check nextData
        match2 = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', rt_res.text)
        if match2:
            data = json.loads(match2.group(1))
            print("Found NEXT_DATA")
