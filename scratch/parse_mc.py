from bs4 import BeautifulSoup
import re

with open("scratch/metacritic_page.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "lxml")

print("Checking spans containing 'quote' or similar classes:")
for tag in soup.find_all(class_=True):
    classes = tag.get("class")
    for c in classes:
        if "review" in c.lower() or "quote" in c.lower() or "body" in c.lower():
            text = tag.get_text(strip=True)
            if len(text) > 100:
                print(f"Tag: {tag.name} | Class: {c} | Len: {len(text)} | Text: {text[:150]}...")
                break

print("\nLet's also look for script tags that contain NEXT_DATA or state data:")
for script in soup.find_all("script"):
    if script.string and "__NEXT_DATA__" in script.string:
        print("Found __NEXT_DATA__! String length:", len(script.string))
        import json
        try:
            data = json.loads(script.string)
            print("Successfully parsed NEXT_DATA.")
            # Let's write keys or save it to inspect
            with open("scratch/next_data.json", "w", encoding="utf-8") as json_f:
                json.dump(data, json_f, indent=2)
            print("Saved NEXT_DATA to scratch/next_data.json")
        except Exception as e:
            print("Failed to parse NEXT_DATA:", e)
