import json
import re
from curl_cffi import requests

imdb_id = "tt15398776"  # Oppenheimer
# Since RT doesn't use imdb_id, we need to search by title
title = "Oppenheimer"
year = 2023

s = requests.Session(impersonate="chrome124")

# Rotten Tomatoes uses slugs like oppenheimer_2023
slug = f"{title.lower().replace(' ', '_')}_{year}"
url = f"https://www.rottentomatoes.com/m/{slug}/reviews"
r = s.get(url)

print("RT HTML Status:", r.status_code)

match = re.search(r'<script id="score-details-json" type="application/json">(.*?)</script>', r.text, re.S)
if match:
    try:
        data = json.loads(match.group(1))
        # Find reviews in the json
        print("Got score details JSON, printing keys:", data.keys())
    except Exception as e:
        print("score-details decode err", e)

# The critics reviews might be in another block
match2 = re.search(r'data-page-state="(.*?)"', r.text)
if match2:
    import html
    state_str = html.unescape(match2.group(1))
    try:
        data = json.loads(state_str)
        print("Parsed data-page-state, keys:", data.keys())
    except Exception as e:
        pass

# The easiest way: in RT there's `<p class="review-text" data-qa="review-quote">...</p>` 
# Let's see if BeautifulSoup finds them
from bs4 import BeautifulSoup
soup = BeautifulSoup(r.text, 'lxml')
revs = soup.select('p.review-text[data-qa="review-quote"]')
print("DOM Quotes found:", len(revs))
for r in revs[:3]:
    print("-", r.text[:100])

# Wait, RT critic reviews are in `p[data-qa='review-quote']` usually
# but maybe the class is different now:
all_p = soup.find_all('p')
import textwrap
for p in all_p:
    if 50 < len(p.text) < 300:
        if "Rotten Tomatoes" not in p.text and "Newsletter" not in p.text:
            print("Candidate P:", p.text[:100].replace('\n', ' '))
