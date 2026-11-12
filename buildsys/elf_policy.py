from __future__ import annotations

EXPECTED_INTERP_X86_64 = "/lib/ld-musl-x86_64.so.1"

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
    if "/" in name or name in ("", ".", ".."):
        return False
    return name in ALLOWED_NEEDED
