from pathlib import Path
import requests
import json


BASE_URL = "https://registry.modelcontextprotocol.io/v0/servers"

def download_registry(out_path = Path("registry.json")):
    servers = []
    limit = 100
    url = f"{BASE_URL}?limit={limit}"

    response = requests.get(url)
    response.raise_for_status()
    j = response.json()
    servers.extend(j["servers"])

    while cursor := j["metadata"].get("next_cursor"):
        url = f"{BASE_URL}?limit={limit}&cursor={cursor}"
        response = requests.get(url)
        response.raise_for_status()
        j = response.json()
        servers.extend(j["servers"])

    out_path.write_text(json.dumps(servers, indent=2))

    print(f"Downloaded {url} to {out_path}")

if __name__ == "__main__":
    download_registry()
