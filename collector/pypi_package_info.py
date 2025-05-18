from tempfile import TemporaryDirectory
import subprocess
from pathlib import Path
import tomlkit

from .models import Package, Artifact, DependencyTreeNode, Packages, PackageInfo


def create_poetry_lock(tmp_dir: Path, pkg_name: str, pkg_version: str) -> Path:
    tmp_dir = Path(tmp_dir)
    pkg_name = pkg_name.replace("_", "-")

    pyproject_content = f"""
    [tool.poetry]
    name = "example-project"
    version = "0.1.0"

    [tool.poetry.dependencies]
    python = ">=3.13,<3.14"
    {pkg_name} = "{pkg_version}"

    [build-system]
    requires = ["poetry-core>=1.0.0"]
    build-backend = "poetry.core.masonry.api"
    """
    pyproject_path = tmp_dir  / "pyproject.toml"
    pyproject_path.write_text(pyproject_content)
    subprocess.run(["poetry", "lock"], cwd=tmp_dir, check=True)

    return tmp_dir / "poetry.lock"

def parse_poetry_lock(file_path: Path) -> Packages:
    lock_data = tomlkit.parse(file_path.read_text())

    packages: Packages = {}
    for pkg in lock_data.get("package", []):
        name = pkg["name"].replace("_", "-")
        packages[name] = Package(
            type="pypi",
            version=pkg["version"],
            dependencies=list(pkg.get("dependencies", {}).keys()),
            artifacts=[
                Artifact(name=entry["file"], hash=entry["hash"])
                for entry in pkg.get("files", [])
            ],
        )

    return packages

def build_dependency_tree(dependency_map: Packages, package_name: str, visited: set[str] | None=None) -> DependencyTreeNode | None:
    package_name = package_name.replace("_", "-")

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

def get_pypi_package_info(pkg_name: str, pkg_version: str, tmp_dir: Path) -> PackageInfo:
    tmp_dir.mkdir(parents=True, exist_ok=True)
    lock_file_path = create_poetry_lock(tmp_dir, pkg_name, pkg_version)
    dependencies = parse_poetry_lock(lock_file_path)
    tree = build_dependency_tree(dependencies, pkg_name)
    assert tree is not None
    return PackageInfo(
        name=pkg_name.replace("_", "-"),
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
    pkg_name = "oceanbase_mcp_server"
    pkg_version = "*"

    with TemporaryDirectory(dir=".", delete=False) as tmp_dir:
        dependency_tree = get_pypi_package_info(pkg_name, pkg_version, Path(tmp_dir))

    print(f"Dependency tree for {pkg_name}=={pkg_version}:")
    print_dependency_tree(dependency_tree)
