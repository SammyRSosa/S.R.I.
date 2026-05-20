from bs4 import BeautifulSoup
import sys

# Force UTF-8 stdout if needed, but we won't print non-ascii characters
with open("scratch/metacritic_page.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")

container = soup.find(class_="c-reviews-container")
if container:
    print("Found container!")
    # Let's inspect the first review element
    # Children with index 2, 7, 12... are the review elements
    children = [c for c in container.children if hasattr(c, 'get_text') and len(c.get_text(strip=True)) > 50]
    print(f"Number of review children found: {len(children)}")
    if children:
        first = children[0]
        print(f"First child tag: {first.name}, class: {first.get('class')}")
        
        # Find all elements inside the first child to see where the review body text resides
        for idx, tag in enumerate(first.find_all(True)):
            t = tag.get_text(strip=True)
            if len(t) > 20:
                print(f"Inner Tag {idx}: {tag.name} | classes: {tag.get('class')} | text_len: {len(t)}")
else:
    print("No container found.")
