from tempfile import TemporaryDirectory
from functools import lru_cache
from pathlib import Path
from rfc3986 import exceptions, uri_reference, validators
from packaging.utils import (
    parse_sdist_filename,
    parse_wheel_filename,
)

from pydantic import ValidationError
import requests
from pypi_attestations import Distribution, GooglePublisher, VerificationError, Provenance, GitHubPublisher, GitLabPublisher
from pypi_attestations._cli import _download_file

from .models import Attestation

# Copied from pypi_attestations package.
@lru_cache(maxsize=None)
def _get_provenance_from_pypi(filename: str) -> Provenance:
    """Use PyPI's integrity API to get a distribution's provenance."""
    # Filename is already validated when creating the Distribution object
    if filename.endswith(".tar.gz") or filename.endswith(".zip"):
        name, version = parse_sdist_filename(filename)
    else:
        name, version, _, _ = parse_wheel_filename(filename)

    provenance_url = f"https://pypi.org/integrity/{name}/{version}/{filename}/provenance"
    response = requests.get(provenance_url)
    if response.status_code == 403:
        raise RuntimeError("Access to provenance is temporarily disabled by PyPI administrators")
    elif response.status_code == 404:
        raise FileNotFoundError(f'Provenance for file "{filename}" was not found')
    elif response.status_code != 200:
        raise RuntimeError(
            f"Unexpected error while downloading provenance file from PyPI, Integrity API "
            f"returned status code: {response.status_code}"
        )

    try:
        return Provenance.model_validate_json(response.text)
    except ValidationError as validation_error:
        raise RuntimeError(f"Invalid provenance: {validation_error}")

# Copied from pypi_attestations package.
def _check_repository_identity(
    expected_repository_url: str, publisher: GitHubPublisher | GitLabPublisher
) -> None:
    """Check that a repository url matches the given publisher's identity."""
    validator = (
        validators.Validator()
        .allow_schemes("https")
        .allow_hosts("github.com", "gitlab.com")
        .require_presence_of("scheme", "host")
    )
    try:
        expected_uri = uri_reference(expected_repository_url)
        validator.validate(expected_uri)
    except exceptions.RFC3986Exception as e:
        raise RuntimeError(f"Unsupported/invalid URL: {e}")

    actual_host = "github.com" if isinstance(publisher, GitHubPublisher) else "gitlab.com"
    expected_host = expected_uri.host
    if actual_host != expected_host:
        raise RuntimeError(
            f"Verification failed: provenance was signed by a {actual_host} repository, but "
            f"expected a {expected_host} repository"
        )

    actual_repository = publisher.repository
    # '/owner/repo' -> 'owner/repo'
    expected_repository = expected_uri.path.lstrip("/")
    if actual_repository != expected_repository:
        raise RuntimeError(
            f'Verification failed: provenance was signed by repository "{actual_repository}", '
            f'expected "{expected_repository}"'
        )

def verify_pypi_attestations_from_dist_filename_and_hash(dist_filename: str, dist_hash: str, expected_repository_url: str | None) -> list[Attestation]:
    if dist_hash.startswith("sha256:"):
        dist_hash_sha256 = dist_hash[7:]
    else:
        raise RuntimeError(f"Unsupported hash format: {dist_hash}")

    dist = Distribution(name=dist_filename, digest=dist_hash_sha256)
    
    out: list[Attestation] = []

    try:
        provenance = _get_provenance_from_pypi(dist.name)
    except FileNotFoundError:
        return [Attestation(
            error_code="missing",
        )]

    try:
        for attestation_bundle in provenance.attestation_bundles:
            publisher = attestation_bundle.publisher
            if isinstance(publisher, GooglePublisher):  # pragma: no cover
                raise RuntimeError("This CLI doesn't support Google Cloud-based publisher verification")
            if expected_repository_url is not None:
                _check_repository_identity(expected_repository_url=expected_repository_url, publisher=publisher)
            policy = publisher._as_policy()  # noqa: SLF001
            # print(publisher.model_dump_json(indent=2))
            for attestation in attestation_bundle.attestations:
                attestation.verify(policy, dist)
                cert_claims = attestation.certificate_claims
                issuer = cert_claims["1.3.6.1.4.1.57264.1.8"]
                runner_env = cert_claims["1.3.6.1.4.1.57264.1.11"]
                repo_url = cert_claims["1.3.6.1.4.1.57264.1.12"]
                repo_digest = cert_claims["1.3.6.1.4.1.57264.1.13"]
                repo_ref = cert_claims["1.3.6.1.4.1.57264.1.14"]
                build_config_url = cert_claims["1.3.6.1.4.1.57264.1.18"]
                build_config_digest = cert_claims["1.3.6.1.4.1.57264.1.19"]
                build_trigger = cert_claims["1.3.6.1.4.1.57264.1.20"]
                run_url = cert_claims["1.3.6.1.4.1.57264.1.21"]
                out.append(Attestation(
                    issuer=issuer,
                    runner_env=runner_env,
                    repo_url=repo_url,
                    repo_digest=repo_digest,
                    repo_ref=repo_ref,
                    build_config_url=build_config_url,
                    build_config_digest=build_config_digest,
                    build_trigger=build_trigger,
                    run_url=run_url,
                    statement=attestation.statement,
                ))
                # print(json.dumps(attestation.certificate_claims, indent=2))
                # print(json.dumps(attestation.statement, indent=2))
    except VerificationError as verification_error:
        out.append(Attestation(
            error_code="verification",
            error_msg=str(verification_error),
        ))
    return out


def get_latest_whl_urls(package_name: str) -> tuple[str, list[str]]:
    url = f"https://pypi.org/pypi/{package_name}/json"
    response = requests.get(url)
    if response.status_code != 200:
        raise ValueError(f"Package '{package_name}' not found on PyPI.")
    
    data = response.json()
    latest_version = data["info"]["version"]
    whl_urls = [
        file_info["url"]
        for file_info in data["releases"][latest_version]
        if file_info["filename"].endswith(".whl")
    ]

    return latest_version, whl_urls

def verify_attestations_from_dist_url(pypi_url: str, expected_repository_url: str | None) -> list[Attestation]:
    validator = (
        validators.Validator()
        .allow_schemes("https")
        .allow_hosts("files.pythonhosted.org")
        .require_presence_of("scheme", "host")
    )

    try:
        pypi_url = uri_reference(pypi_url)
        validator.validate(pypi_url)
    except exceptions.RFC3986Exception as e:
        raise RuntimeError(f"Unsupported/invalid URL: {e}")


    dist_filename = pypi_url.path.split("/")[-1]
    with TemporaryDirectory() as temp_dir:
        dist_path = Path(temp_dir) / dist_filename
        _download_file(url=pypi_url.unsplit(), dest=dist_path)
        dist = Distribution.from_file(dist_path)

    out = verify_pypi_attestations_from_dist_filename_and_hash(dist.name, f"sha256:{dist.digest}", expected_repository_url)
    return out

if __name__ == "__main__":
    # Example usage:
    # repo_url = "https://github.com/letmaik/pyvirtualcam"
    repo_url = None
    package = "psygnal"
    version, wheel_urls = get_latest_whl_urls(package)
    print(f"Latest version: {version}")
    infos: dict[str, list[Attestation]] = {}
    for url in wheel_urls:
        infos[url] = verify_attestations_from_dist_url(url, repo_url)

    for url, attestations in infos.items():
        print(f"URL: {url}")
        for attestation in attestations:
            if attestation.error_code:
                print(f"Error Code: {attestation.error_code}")
                if attestation.error_msg:
                    print(f"Error Message: {attestation.error_msg}")
                continue
            print(f"Issuer: {attestation.issuer}")
            print(f"Runner Environment: {attestation.runner_env}")
            print(f"Repository URL: {attestation.repo_url}")
            print(f"Repository Digest: {attestation.repo_digest}")
            print(f"Repository Reference: {attestation.repo_ref}")
            print(f"Build Config URL: {attestation.build_config_url}")
            print(f"Build Config Digest: {attestation.build_config_digest}")
            print(f"Build Trigger: {attestation.build_trigger}")
            print(f"Run URL: {attestation.run_url}")
            # print(f"  Statement: {attestation.statement}")
            print()