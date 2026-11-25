from __future__ import annotations

from buildlib import release

PRODUCT = "node"
NODE_VERSION = "26.13.1"

INSTALL_DIRNAME = "node"

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
