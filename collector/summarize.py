from pathlib import Path

from .models import PackageInfo, PackageSummary, PackageSummaries

def summarize_package_info(package_info: PackageInfo) -> PackageSummary:
    dependency_count = len(package_info.packages) - 1
    attestation_errors = [pkg_name for pkg_name, pkg in package_info.packages.items()
                          if any(a.error_code for f in pkg.artifacts for a in f.attestations)]
    has_error = package_info.name in attestation_errors
    attestation_issuers = list(set(
        a.issuer
        for f in package_info.packages[package_info.name].artifacts
        for a in f.attestations
        if a.issuer is not None
    ))
    deps_errors = [
        dep for dep in attestation_errors
        if dep != package_info.name
    ]
    return PackageSummary(
        name=package_info.name,
        version=package_info.packages[package_info.name].version,
        type=package_info.packages[package_info.name].type,
        attestation_issuers=attestation_issuers,
        deps=dependency_count,
        has_error=has_error,
        deps_errors=len(deps_errors),
    )

def summarize_package_infos(input_folder: Path, output_path: Path):
    json_files = sorted(Path(input_folder).glob("*.json"))
    summaries: list[PackageSummary] = []
    for json_file in json_files:
        print(f"Processing {json_file.name}...")
        package_info = PackageInfo.model_validate_json(json_file.read_text())
        summarized_package = summarize_package_info(package_info)
        summaries.append(summarized_package)
    out = PackageSummaries(packages=summaries)
    output_path.write_text(out.model_dump_json(indent=1))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Aggregate package info from multiple JSON files.")
    parser.add_argument("input_folder", type=Path, help="Path to the folder containing package info JSON files.")
    parser.add_argument("output_path", type=Path, help="Path to the output JSON file.")
    args = parser.parse_args()

    summarize_package_infos(args.input_folder, args.output_path)
