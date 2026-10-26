from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


class MachOError(Exception):
    pass


MH_MAGIC_64 = 0xFEEDFACF
CPU_ARCH_ABI64 = 0x01000000
CPU_TYPE_ARM64 = 12 | CPU_ARCH_ABI64
CPU_TYPE_X86_64 = 7 | CPU_ARCH_ABI64

MH_OBJECT = 1
MH_EXECUTE = 2
MH_DYLIB = 6
MH_BUNDLE = 8

MH_PIE = 0x200000

LC_LOAD_DYLIB = 0x0C
LC_LOAD_WEAK_DYLIB = 0x80000018
LC_REEXPORT_DYLIB = 0x8000001F
LC_RPATH = 0x8000001C
LC_VERSION_MIN_MACOSX = 0x24
LC_BUILD_VERSION = 0x32

PLATFORM_MACOS = 1

_HEADER = struct.Struct("<8I")


def parse_version(raw: int) -> str:
    major = (raw >> 16) & 0xFFFF
    minor = (raw >> 8) & 0xFF
    patch = raw & 0xFF
    return f"{major}.{minor}.{patch}"


@dataclass(frozen=True)
class MachOInfo:
    cputype: int
    filetype: int
    pie: bool
    minos: str | None
    sdk: str | None
    dependencies: tuple[str, ...]
    rpaths: tuple[str, ...]


def _read_cstring(payload: bytes, offset: int, limit: int) -> str:
    end = payload.index(b"\x00", offset, limit)
    return payload[offset:end].decode("utf-8", errors="replace")


def inspect(path: Path) -> MachOInfo:
    data = path.read_bytes()
    if len(data) < _HEADER.size:
        raise MachOError(f"{path}: too short for a Mach-O header")
    magic, cputype, _cpusubtype, filetype, ncmds, _sizeofcmds, flags, _reserved = _HEADER.unpack_from(data, 0)
    if magic != MH_MAGIC_64:
        raise MachOError(f"{path}: not a 64-bit little-endian Mach-O (magic {magic:#x})")
    offset = _HEADER.size
    minos: str | None = None
    sdk: str | None = None
    dependencies: list[str] = []
    rpaths: list[str] = []
    for _ in range(ncmds):
        if offset + 8 > len(data):
            raise MachOError(f"{path}: load command runs past end of file")
        cmd, cmdsize = struct.unpack_from("<2I", data, offset)
        if cmdsize < 8 or offset + cmdsize > len(data):
            raise MachOError(f"{path}: corrupt load command size {cmdsize}")
        if cmd in (LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB):
            name_offset = struct.unpack_from("<I", data, offset + 8)[0]
            dependencies.append(_read_cstring(data, offset + name_offset, offset + cmdsize))
        elif cmd == LC_RPATH:
            path_offset = struct.unpack_from("<I", data, offset + 8)[0]
            rpaths.append(_read_cstring(data, offset + path_offset, offset + cmdsize))
        elif cmd == LC_BUILD_VERSION:
            platform_id, minos_raw, sdk_raw = struct.unpack_from("<3I", data, offset + 8)
            if platform_id == PLATFORM_MACOS:
                minos = parse_version(minos_raw)
                sdk = parse_version(sdk_raw)
        elif cmd == LC_VERSION_MIN_MACOSX:
            version_raw, sdk_raw = struct.unpack_from("<2I", data, offset + 8)
            if minos is None:
                minos = parse_version(version_raw)
                sdk = parse_version(sdk_raw)
        offset += cmdsize
    return MachOInfo(
        cputype=cputype,
        filetype=filetype,
        pie=bool(flags & MH_PIE),
        minos=minos,
        sdk=sdk,
        dependencies=tuple(dependencies),
        rpaths=tuple(rpaths),
    )


@dataclass(frozen=True)
class HardeningFinding:
    name: str
    ok: bool
    detail: str


def validate_executable(info: MachOInfo, minimum_os: str) -> list[HardeningFinding]:
    findings = [
        HardeningFinding(
            "thin-arm64",
            info.cputype == CPU_TYPE_ARM64,
            f"cputype {info.cputype:#x}",
        ),
        HardeningFinding(
            "execute",
            info.filetype == MH_EXECUTE,
            f"filetype {info.filetype}",
        ),
        HardeningFinding(
            "pie",
            info.pie and info.filetype == MH_EXECUTE,
            "MH_PIE set on executable" if info.pie else "MH_PIE missing",
        ),
    ]
    floor_ok = info.minos is not None and _pack_version(info.minos) >= _pack_version(minimum_os)
    findings.append(
        HardeningFinding(
            "deployment-floor",
            floor_ok,
            f"minos {info.minos} vs required {minimum_os}",
        )
    )
    bad_rpaths = [rpath for rpath in info.rpaths if rpath.startswith(("/usr/local", "/opt", "/private/tmp", "/var/folders"))]
    findings.append(
        HardeningFinding(
            "rpath",
            not bad_rpaths,
            f"unsafe rpaths: {bad_rpaths}" if bad_rpaths else f"rpaths {list(info.rpaths)}",
        )
    )
    return findings


def _pack_version(dotted: str) -> int:
    parts = [int(part) for part in dotted.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return (parts[0] << 16) | (parts[1] << 8) | parts[2]
