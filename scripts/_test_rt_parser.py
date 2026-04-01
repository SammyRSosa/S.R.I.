import re
import json

with open('rt_script.txt', encoding='utf-8') as f:
    text = f.read()

# We can search for the "quote" attribute in all JSONs embedded
all_quotes = re.findall(r'"quote"\s*:\s*"(.*?)"', text)
print(f"Found {len(all_quotes)} total raw quotes")

reviews = []
for q in all_quotes:
    if len(q) > 40 and "http" not in q:
        decoded = q.encode('utf-8').decode('unicode_escape')
        # sometimes it has \\"
        decoded = decoded.replace('\\"', '"')
        if decoded not in reviews:
            reviews.append(decoded)

print(f"Found {len(reviews)} unique valid review quotes.")
for i, r in enumerate(reviews[:5]):
    print(f"[{i}] {r[:100]}")
    
# Let's also verify "critic" or "originalText" to see if there are other reviews formats
all_texts = re.findall(r'"review"\s*:\s*"(.*?)"', text)
print(f"Found {len(all_texts)} raw text reviews")
