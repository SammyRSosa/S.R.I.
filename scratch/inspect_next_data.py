import json
from bs4 import BeautifulSoup
from curl_cffi.requests import Session

url = "https://www.metacritic.com/movie/i-love-boosters/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}
s = Session(impersonate="chrome124")
s.headers.update(headers)

print("Fetching URL...")
resp = s.get(url, timeout=20)
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, "lxml")
    nu_data_script = soup.find("script", id="__NUXT_DATA__")
    if nu_data_script and nu_data_script.string:
        data = json.loads(nu_data_script.string)
        print("Success loading __NUXT_DATA__!")
        print("Type of data:", type(data))
        print("Length of data list:", len(data))
        
        # Guardar una versión recortada para ver la estructura
        print("First 50 items:")
        for idx, item in enumerate(data[:50]):
            print(f"{idx}: {repr(item)[:100]}")
            
        # Buscar palabras de interés en el array
        print("\nIndexes of keywords in Nuxt data:")
        for idx, item in enumerate(data):
            if isinstance(item, str):
                if "I Love Boosters" in item:
                    print(f"Keyword 'I Love Boosters' at index {idx}: {repr(item)}")
                if "synopsis" in item.lower() or "description" in item.lower() or "summary" in item.lower():
                    print(f"Keyword '{item}' at index {idx}")
    else:
        print("No __NUXT_DATA__ script found.")
else:
    print(f"Failed to fetch. Status code: {resp.status_code}")
