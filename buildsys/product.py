from __future__ import annotations

NODE_VERSION = "26.12.1"

INSTALL_DIRNAME = "node"
STAGED_BINDIR = "bin"
STAGED_NODE = "bin/node"
STAGED_INCLUDEDIR = "include/node"
STAGED_LIBDIR = "lib"
LICENSE_NAME = "LICENSE"

LOCAL_REVISION_PREFIX = "r"


def release_title(version: str, tag: str) -> str:
    return f"node-{version}+{tag}"


def local_archive_name(version: str, triple: str, revision: int) -> str:
    return f"node-{version}-{triple}-{LOCAL_REVISION_PREFIX}{revision}.tar.gz"


def local_artifact_name() -> str:
    return "artifact.json"


def release_archive_name(version: str, tag: str, triple: str) -> str:
    return f"node-{version}+{tag}-{triple}-install_only_stripped.tar.gz"


def release_manifest_name(triple: str) -> str:
    return f"artifact-{triple}.json"


ASSEMBLY_MANIFEST_NAME = "assembly.json"
DOWNLOAD_METADATA_NAME = "download-metadata.json"
SMOKE_METADATA_NAME = "smoke-metadata.json"
CHECKSUMS_NAME = "SHA256SUMS"

RELEASE_MANIFEST_NAMES = (
    ASSEMBLY_MANIFEST_NAME,
    DOWNLOAD_METADATA_NAME,
    SMOKE_METADATA_NAME,
    CHECKSUMS_NAME,
)


def expected_release_assets(version: str, tag: str, triples: tuple[str, ...]) -> tuple[str, ...]:
    assets = [release_archive_name(version, tag, triple) for triple in triples]
    assets.extend(release_manifest_name(triple) for triple in triples)
    assets.extend(RELEASE_MANIFEST_NAMES)
    return tuple(assets)
