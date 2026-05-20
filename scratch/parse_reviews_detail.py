from bs4 import BeautifulSoup

with open("scratch/metacritic_page.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")

print("=== Examining children of c-reviews-container ===")
container = soup.find(class_="c-reviews-container")
if container:
    # Let's print tag types and text of direct children or search inside
    print("Found c-reviews-container!")
    
    # Check for div reviews
    # Typically, each review is a div inside the container
    review_cards = container.find_all(class_=lambda c: c and ("review" in c or "card" in c))
    print(f"Found {len(review_cards)} review cards using class search.")
    
    # Or print all div elements with substantial text inside c-reviews-container
    divs = container.find_all("div")
    print(f"Found {len(divs)} divs inside c-reviews-container.")
    
    # Let's see what is inside container
    text_elements = []
    # Let's look for elements that have review body or text
    # In modern Metacritic, maybe it's in c-siteReview_body or c-siteReviewQuote or just class like 'g-text-large' or 'c-siteReview' or similar
    # Let's list some children
    for idx, d in enumerate(container.children):
        t = d.get_text(strip=True) if hasattr(d, 'get_text') else ""
        if len(t) > 50:
            print(f"Child {idx} type={type(d)} text={t[:100]}...")
            
    print("\nLet's print elements with class containing 'review':")
    for tag in container.find_all(class_=True):
        classes = tag.get("class")
        if any("review" in c.lower() for c in classes):
            t = tag.get_text(separator=" ", strip=True)
            if 100 < len(t) < 3000:
                print(f"Tag: {tag.name} | Classes: {classes} | Text: {t[:120]}...")
else:
    print("c-reviews-container not found.")
