from __future__ import annotations

import platform
from dataclasses import dataclass


class UnsupportedTargetError(Exception):
    pass


@dataclass(frozen=True)
class Target:
    triple: str
    machine: str
    family: str
    cpu_baseline_cflag: str
    deployment_target: str
    executable_format: str


DARWIN_ARM64 = Target(
    triple="aarch64-apple-darwin",
    machine="arm64",
    family="macos",
    cpu_baseline_cflag="-mcpu=apple-m1",
    deployment_target="13.5",
    executable_format="mach-o",
)

TARGETS: dict[str, Target] = {
    DARWIN_ARM64.triple: DARWIN_ARM64,
}

SUPPORTED_TRIPLES = tuple(sorted(TARGETS))

_LINUX_TRIPLES = (
    "x86_64-unknown-linux-musl",
    "aarch64-unknown-linux-musl",
)


def target_for_triple(triple: str) -> Target:
    try:
        return TARGETS[triple]
    except KeyError:
        if triple in _LINUX_TRIPLES:
            raise UnsupportedTargetError(
                f"target deferred, not implemented in this campaign: {triple} "
                "(linux targets are parked; see plan Non-goals)"
            ) from None
        raise UnsupportedTargetError(
            f"target not implemented: {triple} (supported: {SUPPORTED_TRIPLES})"
        ) from None


def native_target() -> Target:
    machine = platform.machine()
    if machine != "arm64":
        raise UnsupportedTargetError(
            f"this machine ({machine}) has no target description; "
            f"supported: {SUPPORTED_TRIPLES}"
        )
    if platform.system() != "Darwin":
        raise UnsupportedTargetError(
            f"this machine ({machine} {platform.system()}) has no target description; "
            f"supported: {SUPPORTED_TRIPLES}"
        )
    return DARWIN_ARM64
