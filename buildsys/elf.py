from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

ET_NONE, ET_REL, ET_EXEC, ET_DYN = 0, 1, 2, 3
EM_X86_64, EM_AARCH64 = 62, 183
MACHINE_NAMES = {EM_X86_64: "x86_64", EM_AARCH64: "aarch64"}

PT_NULL, PT_LOAD, PT_DYNAMIC, PT_INTERP, PT_NOTE = 0, 1, 2, 3, 4
PT_GNU_EH_FRAME, PT_GNU_STACK, PT_GNU_RELRO = 0x6474E550, 0x6474E551, 0x6474E552

DT_NULL, DT_NEEDED, DT_STRTAB, DT_STRSZ = 0, 1, 5, 10
DT_RPATH, DT_RUNPATH, DT_FLAGS = 15, 29, 30
DT_FLAGS_1 = 0x6FFFFFFB
DF_BIND_NOW, DF_1_NOW = 0x8, 0x1

PF_X, PF_W, PF_R = 0x1, 0x2, 0x4

NT_GNU_BUILD_ID = 3

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


class ELFError(Exception):
    pass


@dataclass(frozen=True)
class ELFHeader:
    path: Path
    elf_class: int
    etype: int
    machine: int
    phoff: int
    phnum: int

    @property
    def arch(self) -> str:
        return MACHINE_NAMES.get(self.machine, f"machine-{self.machine}")

    @property
    def kind(self) -> str:
        if self.etype == ET_DYN:
            return "pie-executable"
        if self.etype == ET_EXEC:
            return "executable"
        if self.etype == ET_REL:
            return "relocatable"
        return f"type-{self.etype}"

    @property
    def pie(self) -> bool:
        return self.etype == ET_DYN

    @property
    def is_64(self) -> bool:
        return self.elf_class == 2


@dataclass(frozen=True)
class ProgramHeader:
    ptype: int
    flags: int
    offset: int
    vaddr: int
    filesz: int
    memsz: int


def is_elf(path: Path) -> bool:
    try:
        with Path(path).open("rb") as handle:
            return handle.read(4) == b"\x7fELF"
    except OSError:
        return False


def _read_header(path: Path) -> tuple[ELFHeader, list[ProgramHeader]]:
    raw = Path(path).read_bytes()
    if len(raw) < 64 or raw[:4] != b"\x7fELF":
        raise ELFError(f"{path}: not an ELF file")
    elf_class, data, version = raw[4], raw[5], raw[6]
    if elf_class != 2:
        raise ELFError(f"{path}: only 64-bit ELF is supported (class {elf_class})")
    if data != 1:
        raise ELFError(f"{path}: only little-endian ELF is supported")
    if version != 1:
        raise ELFError(f"{path}: bad ELF version {version}")
    (etype, machine, _ever, _entry, phoff, _shoff, _flags, _ehsize,
     phentsize, phnum, _shentsize, _shnum, _shstrndx) = struct.unpack_from(
        "<HHIQQQIHHHHHH", raw, 16
    )
    if phentsize != 56:
        raise ELFError(f"{path}: unexpected program header size {phentsize}")
    headers: list[ProgramHeader] = []
    for index in range(phnum):
        offset = phoff + index * phentsize
        if offset + 56 > len(raw):
            raise ELFError(f"{path}: truncated program headers")
        (ptype, flags, poff, vaddr, _paddr, filesz, memsz, _align) = struct.unpack_from(
            "<IIQQQQQQ", raw, offset
        )
        headers.append(ProgramHeader(ptype, flags, poff, vaddr, filesz, memsz))
    return (
        ELFHeader(Path(path), elf_class, etype, machine, phoff, phnum),
        headers,
    )


def read_header(path: Path) -> ELFHeader:
    header, _ = _read_header(path)
    return header


def program_headers(path: Path) -> list[ProgramHeader]:
    _, headers = _read_header(path)
    return headers


def _segment_bytes(path: Path, header: ProgramHeader) -> bytes:
    with Path(path).open("rb") as handle:
        handle.seek(header.offset)
        return handle.read(header.filesz)


def interpreter(path: Path) -> str | None:
    for header in program_headers(path):
        if header.ptype == PT_INTERP:
            data = _segment_bytes(path, header)
            return data.split(b"\x00")[0].decode("utf-8", "replace")
    return None


def _map_va(headers: list[ProgramHeader], addr: int, size: int) -> tuple[int, int] | None:
    for header in headers:
        if header.ptype != PT_LOAD:
            continue
        if header.vaddr <= addr and addr + size <= header.vaddr + header.filesz:
            return header.offset + (addr - header.vaddr), size
    return None


def _dynamic_entries(path: Path) -> tuple[list[tuple[int, int]], bytes]:
    raw = Path(path).read_bytes()
    _, headers = _read_header(path)
    dynamic = next((h for h in headers if h.ptype == PT_DYNAMIC), None)
    if dynamic is None:
        return [], b""
    entries: list[tuple[int, int]] = []
    blob = raw[dynamic.offset:dynamic.offset + dynamic.filesz]
    for offset in range(0, len(blob) - 15, 16):
        tag, val = struct.unpack_from("<qQ", blob, offset)
        entries.append((tag, val))
        if tag == DT_NULL:
            break
    strtab = next((v for t, v in entries if t == DT_STRTAB), 0)
    strsz = next((v for t, v in entries if t == DT_STRSZ), 0)
    if not strtab or not strsz:
        return entries, b""
    mapped = _map_va(headers, strtab, strsz)
    if mapped is None:
        raise ELFError(f"{path}: STRTAB {strtab:#x} is not mapped by any LOAD segment")
    return entries, raw[mapped[0]:mapped[0] + strsz]


def _dyn_string(table: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(table):
        raise ELFError(f"dynamic string offset {offset} outside strtab")
    end = table.find(b"\x00", offset)
    raw = table[offset:] if end == -1 else table[offset:end]
    return raw.decode("utf-8", "replace")


def dependencies(path: Path) -> list[str]:
    entries, table = _dynamic_entries(path)
    return [_dyn_string(table, val) for tag, val in entries if tag == DT_NEEDED]


def rpaths(path: Path) -> list[str]:
    entries, table = _dynamic_entries(path)
    return [
        _dyn_string(table, val)
        for tag, val in entries
        if tag in (DT_RPATH, DT_RUNPATH)
    ]


def has_relro(path: Path) -> bool:
    return any(h.ptype == PT_GNU_RELRO for h in program_headers(path))


def stack_nx(path: Path) -> bool:
    for header in program_headers(path):
        if header.ptype == PT_GNU_STACK:
            return not bool(header.flags & PF_X)
    return False


def has_bind_now(path: Path) -> bool:
    entries, _ = _dynamic_entries(path)
    for tag, val in entries:
        if tag == DT_FLAGS and val & DF_BIND_NOW:
            return True
        if tag == DT_FLAGS_1 and val & DF_1_NOW:
            return True
    return False


def inspect(path: Path) -> dict:
    header = read_header(path)
    return {
        "arch": header.arch,
        "kind": header.kind,
        "is_64": header.is_64,
        "pie": header.pie,
        "interpreter": interpreter(path),
        "dependencies": dependencies(path),
        "rpaths": rpaths(path),
        "relro": has_relro(path),
        "bind_now": has_bind_now(path),
        "stack_nx": stack_nx(path),
    }


def build_id_ranges(path: Path) -> list[tuple[int, int]]:
    raw = Path(path).read_bytes()
    _, headers = _read_header(path)
    ranges: list[tuple[int, int]] = []
    for header in headers:
        if header.ptype != PT_NOTE:
            continue
        blob = raw[header.offset:header.offset + header.filesz]
        cursor = 0
        while cursor + 12 <= len(blob):
            namesz, descsz, note_type = struct.unpack_from("<III", blob, cursor)
            name_start = cursor + 12
            name_end = name_start + ((namesz + 3) & ~3)
            desc_start = name_end
            desc_end = desc_start + ((descsz + 3) & ~3)
            if desc_end > len(blob):
                break
            name = blob[name_start:name_start + namesz]
            if note_type == NT_GNU_BUILD_ID and name.rstrip(b"\x00") == b"GNU":
                ranges.append((header.offset + desc_start, descsz))
            cursor = desc_end
    return ranges


def normalized_bytes(path: Path) -> bytes:
    raw = bytearray(Path(path).read_bytes())
    for offset, size in build_id_ranges(Path(path)):
        if 0 <= offset < len(raw):
            end = min(offset + size, len(raw))
            raw[offset:end] = b"\x00" * (end - offset)
    return bytes(raw)


def find_elifs(root: Path) -> list[Path]:
    return sorted(
        path
        for path in Path(root).rglob("*")
        if path.is_file() and not path.is_symlink() and is_elf(path)
    )


def allowed_dependency(name: str) -> bool:
    if "/" in name or name in ("", ".", ".."):
        return False
    return name in ALLOWED_NEEDED
