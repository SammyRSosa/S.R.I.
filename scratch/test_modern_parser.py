from bs4 import BeautifulSoup

with open("scratch/metacritic_page.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")

reviews = []
container = soup.find(class_="c-reviews-container")
if container:
    # Strategy 1: Find divs with class "break-words"
    for tag in container.find_all("div", class_=lambda c: c and "break-words" in c):
        text = tag.get_text(separator=" ", strip=True)
        if len(text) > 50 and text not in reviews:
            reviews.append(text)

print(f"Strategy 1: Found {len(reviews)} reviews.")
for idx, r in enumerate(reviews[:3], 1):
    print(f"[{idx}] {r[:120]}...")
