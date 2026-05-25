import json
from bs4 import BeautifulSoup
from curl_cffi.requests import Session

url = "https://www.metacritic.com/movie/i-love-boosters/"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}
s = Session(impersonate="chrome124")
s.headers.update(headers)

print("Fetching...")
resp = s.get(url, timeout=20)
if resp.status_code == 200:
    soup = BeautifulSoup(resp.text, "lxml")
    nu_data_script = soup.find("script", id="__NUXT_DATA__")
    if nu_data_script and nu_data_script.string:
        raw_list = json.loads(nu_data_script.string)
        
        # Resolver de punteros Nuxt.js
        # Un valor entero representa un índice en raw_list, excepto si estamos en el nivel básico
        # Para evitar bucles infinitos, mantenemos un conjunto de IDs visitados
        def resolve(val, visited=None):
            if visited is None:
                visited = set()
            
            if isinstance(val, int):
                if 0 <= val < len(raw_list):
                    # Evitar recursión circular
                    if val in visited:
                        return f"<Ref to {val}>"
                    visited.add(val)
                    res = resolve(raw_list[val], visited)
                    visited.remove(val)
                    return res
                return val
            elif isinstance(val, dict):
                return {k: resolve(v, visited) for k, v in val.items()}
            elif isinstance(val, list):
                # Nuxt usa wrappers tipo ['ShallowReactive', 3] o similares
                if len(val) == 2 and isinstance(val[0], str) and val[0] in ['ShallowReactive', 'Reactive', 'ShallowRef', 'Ref']:
                    return resolve(val[1], visited)
                return [resolve(x, visited) for x in val]
            return val

        resolved_root = resolve(1) # Empezar desde el index 1
        
        # Buscar en el árbol resuelto las propiedades del film
        # Guardar el árbol completo en un archivo JSON local en scratch para inspeccionar
        with open("scratch/resolved_nuxt.json", "w", encoding="utf-8") as f:
            json.dump(resolved_root, f, ensure_ascii=False, indent=2)
            
        print("Resolved Nuxt.js data saved to scratch/resolved_nuxt.json")
        
        # Buscar claves de películas
        # Generalmente, en la data resuelta hay una clave tipo "loadPage:movies:..." que contiene "components"
        if isinstance(resolved_root, dict):
            state_data = resolved_root.get("data", {})
            if isinstance(state_data, dict):
                for k, v in state_data.items():
                    if "loadPage:movies" in k:
                        print(f"\nFound movie page load key: {k}")
                        # Imprimir las llaves de este objeto
                        if isinstance(v, dict):
                            print("Keys under loadPage:", list(v.keys()))
                            # Típicamente contiene "components"
                            components = v.get("components", [])
                            print("Number of components:", len(components))
                            for idx, c in enumerate(components):
                                print(f"Component {idx}: name={c.get('name')}, type={c.get('type')}")
    else:
        print("No __NUXT_DATA__ script found.")
else:
    print("Failed status:", resp.status_code)
