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
    deployment_target="26.0",
    executable_format="mach-o",
)

LINUX_X64_MUSL = Target(
    triple="x86_64-unknown-linux-musl",
    machine="x86_64",
    family="linux",
    cpu_baseline_cflag="-march=x86-64-v2",
    deployment_target="1.2.6",
    executable_format="elf",
)

TARGETS: dict[str, Target] = {
    DARWIN_ARM64.triple: DARWIN_ARM64,
    LINUX_X64_MUSL.triple: LINUX_X64_MUSL,
}

SUPPORTED_TRIPLES = tuple(sorted(TARGETS))

_LINUX_TRIPLES = (
    "aarch64-unknown-linux-musl",
)


def target_for_triple(triple: str) -> Target:
    try:
        return TARGETS[triple]
    except KeyError:
        if triple in _LINUX_TRIPLES:
            raise UnsupportedTargetError(
                f"target deferred, not implemented in this campaign: {triple} "
                "(linux arm64 is parked; see plan Non-goals)"
            ) from None
        raise UnsupportedTargetError(
            f"target not implemented: {triple} (supported: {SUPPORTED_TRIPLES})"
        ) from None


def native_target() -> Target:
    machine = platform.machine()
    system = platform.system()
    if system == "Darwin" and machine == "arm64":
        return DARWIN_ARM64
    if system == "Linux" and machine == "x86_64":
        return LINUX_X64_MUSL
    raise UnsupportedTargetError(
        f"this machine ({machine} {system}) has no target description; "
        f"supported: {SUPPORTED_TRIPLES}"
    )
