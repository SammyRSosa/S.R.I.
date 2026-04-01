import re
from curl_cffi import requests
r = requests.Session(impersonate='chrome124').get('https://www.rottentomatoes.com/m/oppenheimer_2023/reviews?type=top_critics')
matches = re.findall(r'data-qa="review-quote"[^>]*>(.*?)</p>', r.text, flags=re.S|re.IGNORECASE)
print('Found exact review paragraphs:', len(matches))
for i, m in enumerate(matches[:5]):
    print(f'[{i}]', m.strip()[:100])
