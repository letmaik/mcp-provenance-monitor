from tempfile import TemporaryDirectory
import traceback
import subprocess
from pathlib import Path
import argparse

from .mcp_registry_downloader import download_registry
from .mcp_registry_sanitizer import sanitize_registry
from .pypi_package_info import get_pypi_package_info
from .pypi_attestations import verify_pypi_attestations_from_dist_filename_and_hash
from .npm_package_info import get_npm_package_info
from .npm_attestations import verify_npm_attestations
from .summarize import summarize_package_infos
from .models import MCPServer, PackageInfo

def process_npm_mcp_server(mcp_server: MCPServer, tmp_dir: Path) -> PackageInfo:
    mcp_pkg_name = mcp_server.package_name
    print(f"Processing MCP server: {mcp_pkg_name} from NPM")
    tmp_dir = tmp_dir / f"npm_{mcp_pkg_name.replace('/', '@')}"
    package_info = get_npm_package_info(
        mcp_pkg_name,
        "*",
        tmp_dir
    )

    # fetch attestations
    pkgs = package_info.packages
    for pkg_name, pkg in pkgs.items():
        if pkg_name == mcp_pkg_name:
            expected_repository_url = mcp_server.repo_url
        else:
            expected_repository_url = None
        for artifact_info in pkg.artifacts:
            artifact_hash = artifact_info.hash
            out = verify_npm_attestations(pkg_name, pkg.version, artifact_hash, expected_repository_url)
            print(f"Attestations for {artifact_info.name}: {out}")
            artifact_info.attestations = out

    return package_info

def process_pypi_mcp_server(mcp_server: MCPServer, tmp_dir: Path) -> PackageInfo:
    mcp_pkg_name = mcp_server.package_name
    print(f"Processing MCP server: {mcp_pkg_name} from PyPI")
    tmp_dir = tmp_dir / f"pypi_{mcp_pkg_name}"
    package_info = get_pypi_package_info(
        mcp_pkg_name,
        "*",
        tmp_dir
    )

    # fetch attestations
    pkgs = package_info.packages
    for pkg_name, pkg in pkgs.items():
        if pkg_name == mcp_pkg_name:
            expected_repository_url = mcp_server.repo_url
        else:
            expected_repository_url = None
        for artifact_info in pkg.artifacts:
            out = verify_pypi_attestations_from_dist_filename_and_hash(artifact_info.name, artifact_info.hash, expected_repository_url)
            print(f"Attestations for {artifact_info.name}: {out}")
            artifact_info.attestations = out

    return package_info

def build_dataset(tmp_dir: Path, out_dir: Path, limit: int | None=None):
    registry_path = tmp_dir / "registry.json"
    download_registry(registry_path)
    registry = sanitize_registry(registry_path)

    pkg_out_dir = out_dir / "packages"
    pkg_out_dir.mkdir(parents=True, exist_ok=True)

    for mcp_server in registry.servers:
        try:
            match mcp_server.package_registry:
                case "npm":
                    package_info = process_npm_mcp_server(mcp_server, tmp_dir)
                case "pypi":
                    package_info = process_pypi_mcp_server(mcp_server, tmp_dir)
                case _:
                    continue

            out_path = pkg_out_dir / f"{mcp_server.package_registry}_{package_info.name.replace('/', '@')}.json"
            out_path.write_text(package_info.model_dump_json(indent=1))

        except subprocess.CalledProcessError as e:
            print(f"Error processing {mcp_server.package_name}: {e}")
            continue
        except Exception as e:
            print(f"Error processing {mcp_server.package_name}: {e}")
            traceback.print_exc()
            continue

        if limit is not None:
            limit -= 1
            if limit <= 0:
                break

    summarize_package_infos(pkg_out_dir, out_dir / "summary.json")
       

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=Path("web/data"), type=Path, help="Output directory")
    parser.add_argument("--dev", action="store_true", help="Development mode (limit to 2 packages)")
    args = parser.parse_args()

    limit = 2 if args.dev else None

    with TemporaryDirectory(dir=".", delete=False) as tmp_dir:
        build_dataset(Path(tmp_dir), out_dir=args.out, limit=limit)


if __name__ == "__main__":
    main()
