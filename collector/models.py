from pydantic import BaseModel


class MCPServer(BaseModel):
    package_registry: str
    package_name: str
    repo_url: str | None = None
    description: str

class MCPRegistry(BaseModel):
    servers: list[MCPServer]

class Attestation(BaseModel):
    issuer: str | None = None
    runner_env: str | None = None
    repo_url: str | None = None
    repo_digest: str | None = None
    repo_ref: str | None = None
    build_config_url: str | None = None
    build_config_digest: str | None = None
    build_trigger: str | None = None
    run_url: str | None = None
    statement: dict | None = None
    error_code: str | None = None
    error_msg: str | None = None

class Artifact(BaseModel):
    name: str  # artifact name
    hash: str  # hash of the artifact, e.g., sha256:<hex-hash>
    attestations: list[Attestation] = []

PackageName = str

class Package(BaseModel):
    type: str  # e.g., "npm", "pypi"
    version: str
    artifacts: list[Artifact]
    dependencies: list[PackageName]

class DependencyTreeNode(BaseModel):
    name: PackageName
    dependencies: list['DependencyTreeNode'] = []

Packages = dict[PackageName, Package]

class PackageInfo(BaseModel):
    name: PackageName
    packages: Packages
    tree: DependencyTreeNode

class PackageSummary(BaseModel):
    name: PackageName
    version: str
    type: str  # e.g., "npm", "pypi"
    attestation_issuers: list[str] = []
    deps: int = 0  # number of dependencies
    has_error: bool = False
    deps_errors: int = 0  # number of dependencies with errors

class PackageSummaries(BaseModel):
    packages: list[PackageSummary] = []
