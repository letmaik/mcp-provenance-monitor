import json
import subprocess
from tempfile import TemporaryDirectory
from pathlib import Path
import base64

from .models import Package, Artifact, DependencyTreeNode, Packages, PackageInfo

def create_npm_lock(tmp_dir: Path, pkg_name: str, pkg_version: str) -> Path:
    package_json = {
        "name": "example-project",
        "version": "1.0.0",
        "dependencies": {
            pkg_name: pkg_version
        }
    }

    package_json_path = tmp_dir / "package.json"
    with package_json_path.open("w", encoding="utf-8") as f:
        json.dump(package_json, f, indent=2)

    subprocess.run(["npm", "install", "--package-lock-only"], cwd=tmp_dir, check=True, stdout=subprocess.DEVNULL)

    return tmp_dir / "package-lock.json"

def parse_npm_lock(lockfile_path: Path) -> Packages:
    lock_data = json.loads(lockfile_path.read_text())

    packages = lock_data.get("packages", {})
    result: Packages = {}

    for path, meta in packages.items():
        if path == "":
            continue  # skip root entry

        name = path.removeprefix("node_modules/")

        # convert npm integrity format <alg>-<b64-hash> to <alg>:<hex-hash>
        npm_hash = meta["integrity"]
        if "-" in npm_hash:
            algo, b64 = npm_hash.split("-", 1)
            hex_hash = base64.b16encode(base64.b64decode(b64)).decode("ascii").lower()
            artifact_hash = f"{algo}:{hex_hash}"
        else:
            artifact_hash = npm_hash  # fallback, unknown format

        result[name] = Package(
            type="npm",
            version=meta["version"],
            dependencies=list(meta.get("dependencies", {}).keys()),
            artifacts=[
                Artifact(name=f"pkg:npm/{name}@{meta['version']}", hash=artifact_hash)
            ],
        )

    return result

def build_dependency_tree(dependency_map: Packages, package_name: str, visited: set[str] | None=None) -> DependencyTreeNode | None:
    if visited is None:
        visited = set()

    if package_name not in dependency_map:
        # not found, edge case
        return None

    if package_name in visited:
        raise RuntimeError(f"Circular dependency detected for package {package_name}")

    visited.add(package_name)

    pkg = dependency_map[package_name]
    dependencies: list[DependencyTreeNode] = []

    for dep_name in pkg.dependencies:
        subtree = build_dependency_tree(dependency_map, dep_name, visited.copy())
        if subtree is not None:
            dependencies.append(subtree)

    node = DependencyTreeNode(
        name=package_name,
        dependencies=dependencies
    )

    return node

def get_npm_package_info(pkg_name: str, pkg_version: str, tmp_dir: Path) -> PackageInfo:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    lockfile_path = create_npm_lock(tmp_dir, pkg_name, pkg_version)
    dependencies = parse_npm_lock(lockfile_path)
    tree = build_dependency_tree(dependencies, pkg_name)
    assert tree is not None
    return PackageInfo(
        name=pkg_name,
        packages=dependencies,
        tree=tree,
    )

def print_dependency_tree(dependency_tree: PackageInfo, indent=0):
    _print_dependency_tree(dependency_tree.tree, dependency_tree.packages, indent)

def _print_dependency_tree(tree: DependencyTreeNode, packages: Packages, indent=0):
    if tree is None:
        return
    prefix = " " * indent

    pkg = packages[tree.name]
    print(f"{prefix}{tree.name}=={pkg.version} ({len(pkg.artifacts)} artifacts)")

    for dep in tree.dependencies:
        _print_dependency_tree(dep, packages, indent + 2)

if __name__ == "__main__":
    # Example usage
    pkg_name = "mcp-audiense-insights"
    pkg_version = "*"

    with TemporaryDirectory(dir=".", delete=False) as tmp_dir:
        dependency_tree = get_npm_package_info(pkg_name, pkg_version, Path(tmp_dir))
    
    print(f"Dependency tree for {pkg_name} @ {pkg_version}:")
    print_dependency_tree(dependency_tree)
