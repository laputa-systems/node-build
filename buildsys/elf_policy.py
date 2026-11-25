from __future__ import annotations

from pathlib import Path

from buildlib import targets


def _linux_target(machine: str) -> targets.Target | None:
    for candidate in targets.TARGETS.values():
        if candidate.is_linux and candidate.machine == machine:
            return candidate
    return None


def expected_interpreter(machine: str) -> str | None:
    target = _linux_target(machine)
    return target.musl_loader if target is not None else None


def musl_libc(machine: str) -> str | None:
    loader = expected_interpreter(machine)
    if loader is None:
        return None
    return "libc." + Path(loader).name.removeprefix("ld-")


EXPECTED_INTERP_X86_64 = expected_interpreter("x86_64")

ALLOWED_NEEDED = frozenset(
    {
        "libc.musl-x86_64.so.1",
        "libc.musl-aarch64.so.1",
        "libstdc++.so.6",
        "libgcc_s.so.1",
        "libatomic.so.1",
        "libm.so.6",
        "libpthread.so.0",
        "libdl.so.2",
    }
)


def is_elf_machine(machine: str) -> bool:
    return _linux_target(machine) is not None


def allowed_dependency(name: str) -> bool:
    return name in ALLOWED_NEEDED
