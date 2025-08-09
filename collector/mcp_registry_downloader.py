from pathlib import Path
import requests

def download_registry(out_path = Path("registry.json")):
    url = "https://raw.githubusercontent.com/modelcontextprotocol/registry/refs/heads/main/data/seed.json"

    response = requests.get(url)
    response.raise_for_status()

    out_path.write_bytes(response.content)

    print(f"Downloaded {url} to {out_path}")

if __name__ == "__main__":
    download_registry()
