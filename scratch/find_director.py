import json

with open("scratch/resolved_nuxt.json", encoding="utf-8") as f:
    data = json.load(f)

found = []
def search(obj, path=""):
    if isinstance(obj, str) and "Boots Riley" in obj:
        found.append((path, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            search(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            search(x, f"{path}[{i}]")

search(data)
print("Found director references:")
for path, val in found[:15]:
    print(f"Path: {path} => {val}")
