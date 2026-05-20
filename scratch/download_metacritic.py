from curl_cffi import requests

url = "https://www.metacritic.com/movie/oppenheimer/user-reviews/"
r = requests.Session(impersonate="chrome124").get(url)
print("Status code:", r.status_code)
print("Length of response:", len(r.text))

with open("scratch/metacritic_page.html", "w", encoding="utf-8") as f:
    f.write(r.text)
print("Written HTML to scratch/metacritic_page.html")
