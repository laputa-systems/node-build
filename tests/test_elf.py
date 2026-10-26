import struct
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from buildsys import elf, validate_product

BASE = 0x400000


def build_image(
    *,
    etype: int = elf.ET_DYN,
    machine: int = elf.EM_X86_64,
    interp: str | None = elf.EXPECTED_INTERP_X86_64,
    needed: tuple[str, ...] = ("libc.musl-x86_64.so.1",),
    rpath: str | None = None,
    relro: bool = True,
    bind_now: bool = True,
    stack_flags: int = elf.PF_R | elf.PF_W,
) -> bytes:
    strings: list[str] = list(needed)
    if rpath is not None:
        strings.append(rpath)
    strtab = b"".join(part.encode() + b"\x00" for part in strings)
    offsets: dict[str, int] = {}
    cursor = 0
    for part in strings:
        offsets[part] = cursor
        cursor += len(part.encode()) + 1

    phnum = 6
    header_size = 64 + 56 * phnum
    interp_blob = (interp.encode() + b"\x00") if interp is not None else b""
    dynamic_count = len(needed) + (1 if rpath is not None else 0) + 4
    if not bind_now:
        dynamic_count -= 1
    dynamic_offset = header_size + len(interp_blob)
    dynamic_va = BASE + dynamic_offset
    strtab_offset = dynamic_offset + 16 * dynamic_count
    strtab_va = BASE + strtab_offset
    note_offset = strtab_offset + len(strtab)
    note_blob = struct.pack("<III", 4, 20, 3) + b"GNU\x00" + b"\xab" * 20
    total = note_offset + len(note_blob)

    dynamic: list[tuple[int, int]] = [
        (elf.DT_NEEDED, offsets[part]) for part in needed
    ]
    if rpath is not None:
        dynamic.append((elf.DT_RPATH, offsets[rpath]))
    dynamic.append((elf.DT_STRTAB, strtab_va))
    dynamic.append((elf.DT_STRSZ, len(strtab)))
    if bind_now:
        dynamic.append((elf.DT_FLAGS, elf.DF_BIND_NOW))
    dynamic.append((elf.DT_NULL, 0))
    dynamic_blob = b"".join(struct.pack("<qQ", tag, val) for tag, val in dynamic)

    blobs = interp_blob + dynamic_blob + strtab + note_blob
    assert header_size + len(blobs) == total

    ehdr = (
        b"\x7fELF"
        + bytes((2, 1, 1, 0))
        + b"\x00" * 8
        + struct.pack(
            "<HHIQQQIHHHHHH",
            etype, machine, 1, 0x401000, 64, 0, 0, 64, 56, phnum, 0, 0, 0,
        )
    )

    def phdr(ptype: int, flags: int, offset: int, vaddr: int, filesz: int) -> bytes:
        return struct.pack("<IIQQQQQQ", ptype, flags, offset, vaddr, vaddr, filesz, filesz, 0x1000)

    phdrs = b"".join(
        [
            phdr(elf.PT_LOAD, elf.PF_R | elf.PF_W, 0, BASE, total),
            phdr(
                elf.PT_INTERP, elf.PF_R,
                header_size, BASE + header_size, len(interp_blob),
            ),
            phdr(elf.PT_DYNAMIC, elf.PF_R | elf.PF_W, dynamic_offset, dynamic_va, len(dynamic_blob)),
            phdr(elf.PT_NOTE, elf.PF_R, note_offset, BASE + note_offset, len(note_blob)),
            phdr(elf.PT_GNU_RELRO if relro else elf.PT_NULL, elf.PF_R, 0, BASE, 64),
            phdr(elf.PT_GNU_STACK, stack_flags, 0, 0, 0),
        ]
    )
    return ehdr + phdrs + blobs


def write_tree(**kwargs) -> Path:
    root = REPO_ROOT / ".work" / "tmp" / "elf-tree"
    node = root / "bin" / "node"
    node.parent.mkdir(parents=True, exist_ok=True)
    node.write_bytes(build_image(**kwargs))
    return root


class ELFParserTest(unittest.TestCase):
    def tearDown(self):
        import shutil

        shutil.rmtree(REPO_ROOT / ".work" / "tmp" / "elf-tree", ignore_errors=True)
        (REPO_ROOT / ".work" / "tmp" / "elf-probe").unlink(missing_ok=True)

    def probe(self, **kwargs) -> Path:
        path = REPO_ROOT / ".work" / "tmp" / "elf-probe"
        path.write_bytes(build_image(**kwargs))
        return path

    def test_reads_pie_header(self):
        header = elf.read_header(self.probe())
        self.assertTrue(header.pie)
        self.assertTrue(header.is_64)
        self.assertEqual(header.arch, "x86_64")
        self.assertEqual(header.kind, "pie-executable")

    def test_rejects_garbage(self):
        path = REPO_ROOT / ".work" / "tmp" / "elf-probe"
        path.write_bytes(b"not an elf file at all!!!!!!!!!!!!!!")
        with self.assertRaises(elf.ELFError):
            elf.read_header(path)

    def test_rejects_32bit(self):
        raw = bytearray(build_image())
        raw[4] = 1
        path = REPO_ROOT / ".work" / "tmp" / "elf-probe"
        path.write_bytes(bytes(raw))
        with self.assertRaises(elf.ELFError):
            elf.read_header(path)

    def test_interpreter_and_dependencies(self):
        path = self.probe()
        self.assertEqual(elf.interpreter(path), elf.EXPECTED_INTERP_X86_64)
        self.assertEqual(elf.dependencies(path), ["libc.musl-x86_64.so.1"])
        self.assertEqual(elf.rpaths(path), [])

    def test_inspect_report_shape(self):
        report = elf.inspect(self.probe())
        self.assertEqual(
            (report["arch"], report["kind"], report["pie"]),
            ("x86_64", "pie-executable", True),
        )
        self.assertTrue(report["relro"])
        self.assertTrue(report["bind_now"])
        self.assertTrue(report["stack_nx"])

    def test_allowed_dependency(self):
        self.assertTrue(elf.allowed_dependency("libc.musl-x86_64.so.1"))
        self.assertTrue(elf.allowed_dependency("libstdc++.so.6"))
        self.assertFalse(elf.allowed_dependency("/opt/evil/libfoo.so"))
        self.assertFalse(elf.allowed_dependency("../escape.so"))

    def test_build_id_normalization_zeroes_desc(self):
        path = self.probe()
        ranges = elf.build_id_ranges(path)
        self.assertEqual(len(ranges), 1)
        normalized = elf.normalized_bytes(path)
        self.assertEqual(len(normalized), path.stat().st_size)
        offset, size = ranges[0]
        self.assertEqual(normalized[offset:offset + size], b"\x00" * size)
        self.assertNotEqual(normalized, path.read_bytes())


class ELFGateTest(unittest.TestCase):
    def tearDown(self):
        import shutil

        shutil.rmtree(REPO_ROOT / ".work" / "tmp" / "elf-tree", ignore_errors=True)

    def check_names(self, **kwargs) -> dict[str, bool]:
        root = write_tree(**kwargs)
        findings = validate_product.elf_tree_checks(root, "x86_64")
        return {finding.name: finding.ok for finding in findings}

    def test_good_tree_passes(self):
        results = self.check_names()
        self.assertTrue(all(results.values()), results)

    def test_non_pie_fails(self):
        self.assertFalse(self.check_names(etype=elf.ET_EXEC)["elf-pie"])

    def test_wrong_arch_fails(self):
        self.assertFalse(
            self.check_names(machine=elf.EM_AARCH64)["elf-arch"]
        )

    def test_bad_interpreter_fails(self):
        self.assertFalse(
            self.check_names(interp="/lib/ld-linux-x86-64.so.2")["elf-interp"]
        )

    def test_bad_dependency_fails(self):
        self.assertFalse(
            self.check_names(needed=("/opt/evil/libfoo.so",))["elf-deps"]
        )

    def test_rpath_fails(self):
        self.assertFalse(
            self.check_names(rpath="/build/stage/lib")["elf-rpaths"]
        )

    def test_missing_relro_fails(self):
        self.assertFalse(self.check_names(relro=False)["elf-relro"])

    def test_missing_bind_now_fails(self):
        self.assertFalse(self.check_names(bind_now=False)["elf-bind-now"])

    def test_executable_stack_fails(self):
        self.assertFalse(
            self.check_names(
                stack_flags=elf.PF_R | elf.PF_W | elf.PF_X
            )["elf-stack-nx"]
        )


if __name__ == "__main__":
    unittest.main()
