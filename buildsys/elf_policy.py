from __future__ import annotations

from buildlib import targets

EXPECTED_INTERP_X86_64 = targets.target_for_triple("x86_64-unknown-linux-musl").musl_loader

ALLOWED_NEEDED = frozenset(
    {
        "libc.musl-x86_64.so.1",
        "libstdc++.so.6",
        "libgcc_s.so.1",
        "libatomic.so.1",
        "libm.so.6",
        "libpthread.so.0",
        "libdl.so.2",
    }
)


def allowed_dependency(name: str) -> bool:
    return name in ALLOWED_NEEDED
