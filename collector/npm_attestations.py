import json
from functools import lru_cache

import requests
from sigstore.models import Bundle, InvalidBundle
import sigstore.errors
from sigstore.verify import Verifier
from sigstore.dsse import Envelope as DsseEnvelope
from pypi_attestations._impl import (
    _der_decode_utf8string,
    _FULCIO_CLAIMS_OIDS,
)
from pydantic_core import ValidationError

from .models import Attestation

class DummyPolicy:
    def __init__(self):
        pass

    def verify(self, cert) -> None:
        pass

@lru_cache(maxsize=None)
def verify_npm_attestations(package_name: str, package_version: str, dist_hash: str, expected_repository_url: str | None) -> list[Attestation]:
    dist_filename = f"pkg:npm/{package_name}@{package_version}"
    if not dist_hash.startswith("sha512:"):
        raise RuntimeError(f"Unsupported hash format: {dist_hash}")

    url = f"https://registry.npmjs.org/-/npm/v1/attestations/{package_name}@{package_version}"
    response = requests.get(url)
    if response.status_code != 200:
        return [Attestation(
            error_code="missing",
        )]
    data = response.json()

    verifier = Verifier.production()
    policy = DummyPolicy()

    out: list[Attestation] = []

    for attestation in data["attestations"]:
        if attestation["predicateType"] != "https://slsa.dev/provenance/v1":
            continue
        bundle = attestation["bundle"]
        try:
            sigstore_bundle = Bundle.from_json(json.dumps(bundle))
        except (InvalidBundle, json.JSONDecodeError) as e:
            return [Attestation(
                error_code="verification",
                error_msg=f"Invalid Sigstore bundle: {e}"
            )]

        # https://github.com/sigstore/sigstore-python/issues/1384
        # try:
        #     type_, payload = verifier.verify_dsse(sigstore_bundle, policy)
        # except sigstore.errors.VerificationError as err:
        #     raise VerificationError(str(err)) from err

        # if type_ != DsseEnvelope._TYPE:  # noqa: SLF001
        #     raise VerificationError(f"expected JSON envelope, got {type_}")
        
        # try:
        #     statement = _Statement.model_validate_json(payload)
        # except ValidationError as e:
        #     raise VerificationError(f"invalid statement: {str(e)}")
        
        certificate = sigstore_bundle.signing_certificate
        cert_claims: dict[str, str] = {}
        for extension in certificate.extensions:
            if extension.oid in _FULCIO_CLAIMS_OIDS:
                # 1.3.6.1.4.1.57264.1.8 through 1.3.6.1.4.1.57264.1.22 are formatted as DER-encoded
                # strings; the ASN.1 tag is UTF8String (0x0C) and the tag class is universal.
                value = extension.value.value
                cert_claims[extension.oid.dotted_string] = _der_decode_utf8string(value)
        
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
            # statement=statement,
        ))
    return out

if __name__ == "__main__":
    repo_url = "https://github.com/sigstore/sigstore-js"
    digest = "sha512:hexdummy"
    package = "sigstore"
    version = "3.1.0"

    attestations = verify_npm_attestations(package, version, digest, repo_url)

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