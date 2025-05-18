import json
from pathlib import Path

from .models import MCPRegistry, MCPServer

def sanitize_registry(path: Path) -> MCPRegistry:
    data = json.loads(path.read_text())

    servers: list[MCPServer] = []
    for entry in data:
        repo = entry.get("repository", {})
        packages = entry.get("packages", [])
        for pkg in packages:
            pkg_registry = pkg["registry_name"]
            if pkg_registry not in ("npm", "pypi"):
                continue

            servers.append(MCPServer(
                package_registry=pkg_registry,
                package_name=pkg["name"],
                repo_url=repo.get("url"),
                description=entry.get("description", "")
            ))
    registry = MCPRegistry(servers=servers)
    return registry


if __name__ == "__main__":
    registry_path = Path("registry.json")
    sanitized_registry = sanitize_registry(registry_path)
    out_path = Path("registry-clean.json")
    out_path.write_text(sanitized_registry.model_dump_json(indent=2))
    for item in sanitized_registry.servers:
        print(item)