from __future__ import annotations

from buildlib import release

PRODUCT = "node"
NODE_VERSION = "26.12.1"

INSTALL_DIRNAME = "node"
STAGED_BINDIR = "bin"
STAGED_NODE = "bin/node"
STAGED_INCLUDEDIR = "include/node"
STAGED_LIBDIR = "lib"
LICENSE_NAME = "LICENSE"

RELEASE_DIRNAME = "release"


def archive_name(version: str, triple: str) -> str:
    return release.archive_name(PRODUCT, version, triple)


def manifest_name(version: str, triple: str) -> str:
    return release.manifest_name(PRODUCT, version, triple)


def expected_release_assets(version: str, triples: tuple[str, ...]) -> tuple[str, ...]:
    assets = [archive_name(version, triple) for triple in triples]
    assets.extend(manifest_name(version, triple) for triple in triples)
    assets.append(release.CHECKSUMS_NAME)
    return tuple(sorted(assets))
