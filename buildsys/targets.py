from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from buildlib import targets as shared

UnsupportedTargetError = shared.UnsupportedTargetError


@dataclass(frozen=True, kw_only=True)
class Target(shared.Target):
    cpu_baseline_cflag: str
    deployment_target: str


def _extend(triple: str, *, cpu_baseline_cflag: str, deployment_target: str) -> Target:
    base = shared.TARGETS[triple]
    return Target(
        **{field.name: getattr(base, field.name) for field in dataclasses.fields(base)},
        cpu_baseline_cflag=cpu_baseline_cflag,
        deployment_target=deployment_target,
    )


DARWIN_ARM64 = _extend(
    "aarch64-apple-darwin", cpu_baseline_cflag="-mcpu=apple-m1", deployment_target="26.0"
)

LINUX_X64_MUSL = _extend(
    "x86_64-unknown-linux-musl", cpu_baseline_cflag="-march=x86-64-v2", deployment_target="1.2.6"
)

TARGETS: dict[str, Target] = {
    DARWIN_ARM64.triple: DARWIN_ARM64,
    LINUX_X64_MUSL.triple: LINUX_X64_MUSL,
}

SUPPORTED_TRIPLES = tuple(sorted(TARGETS))

_PARKED_TRIPLES = ("aarch64-unknown-linux-musl",)


def target_for_triple(triple: str) -> Target:
    try:
        return TARGETS[triple]
    except KeyError:
        if triple in _PARKED_TRIPLES:
            raise UnsupportedTargetError(
                f"target deferred, not implemented in this campaign: {triple} "
                "(linux arm64 is parked; see plan Non-goals)"
            ) from None
        raise UnsupportedTargetError(
            f"target not implemented: {triple} (supported: {SUPPORTED_TRIPLES})"
        ) from None


def native_target() -> Target:
    return target_for_triple(shared.native_target().triple)
