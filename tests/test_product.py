import struct
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from buildsys import macho, relocate, validate_product
from buildsys import package as packager


def build_version_command(platform: int = 1, minos: int = 26 << 16,
                         sdk: int = 27 << 16) -> bytes:
    return struct.pack("<2I4I", 0x32, 24, platform, minos, sdk, 0)


def named_command(cmd: int, name: str) -> bytes:
    encoded = name.encode() + b"\x00"
    size = 12 + len(encoded)
    padding = b"\x00" * (-size % 8)
    return struct.pack("<3I", cmd, size + len(padding), 12) + encoded + padding


def make_macho(commands, *, cputype: int = macho.CPU_TYPE_ARM64,
               filetype: int = macho.MH_EXECUTE, flags: int = macho.MH_PIE) -> bytes:
    body = b"".join(commands)
    header = struct.pack(
        "<IiiIIIII", 0xFEEDFACF, cputype, 3, filetype, len(commands), len(body), flags, 0
    )
    return header + body


def write_temp(data: bytes) -> Path:
    path = REPO_ROOT / ".work" / "tmp" / "macho-probe"
    path.write_bytes(data)
    return path


class MachOTest(unittest.TestCase):
    def tearDown(self):
        (REPO_ROOT / ".work" / "tmp" / "macho-probe").unlink(missing_ok=True)

    def test_reads_pie_flag(self):
        info = macho.read_header(write_temp(make_macho([build_version_command()])))
        self.assertTrue(info.pie)
        self.assertTrue(info.is_64)
        self.assertEqual(info.arch, "arm64")
        self.assertEqual(info.kind, "execute")

    def test_reads_non_pie_flag(self):
        info = macho.read_header(write_temp(make_macho([build_version_command()], flags=0)))
        self.assertFalse(info.pie)

    def test_distinguishes_x86_64(self):
        info = macho.read_header(
            write_temp(make_macho([build_version_command()], cputype=macho.CPU_TYPE_X86_64))
        )
        self.assertEqual(info.arch, "x86_64")

    def test_rejects_fat(self):
        path = write_temp(b"\xca\xfe\xba\xbe" + b"\x00" * 28)
        with self.assertRaises(macho.MachOError):
            macho.read_header(path)

    def test_rejects_garbage(self):
        with self.assertRaises(macho.MachOError):
            macho.read_header(write_temp(b"not a mach-o file at all!!!!!!!!"))

    def test_rejects_truncated_commands(self):
        header = struct.pack("<IiiIIIII", 0xFEEDFACF, macho.CPU_TYPE_ARM64, 3, 2, 1, 24, 0x200000, 0)
        with self.assertRaises(macho.MachOError):
            macho.load_commands(write_temp(header + b"\x32\x00"))

    def test_build_version_floor(self):
        version = macho.build_version(write_temp(make_macho([build_version_command()])))
        assert version is not None
        self.assertEqual(version.minos, "26.0")
        self.assertEqual(version.platform_name, "macos")

    def test_missing_build_version_is_none(self):
        self.assertIsNone(macho.build_version(write_temp(make_macho([]))))

    def test_dependencies_and_rpaths(self):
        image = make_macho([
            named_command(0x0C, "/usr/lib/libc++.1.dylib"),
            named_command(0x8000001C, "@loader_path/../lib"),
        ])
        path = write_temp(image)
        self.assertEqual(macho.dependencies(path), ["/usr/lib/libc++.1.dylib"])
        self.assertEqual(macho.rpaths(path), ["@loader_path/../lib"])

    def test_string_offset_outside_command_rejected(self):
        bad = struct.pack("<3I", 0x0C, 12, 9999)
        with self.assertRaises(macho.MachOError):
            macho.dependencies(write_temp(make_macho([bad])))

    def test_inspect_report_shape(self):
        report = macho.inspect(write_temp(make_macho([build_version_command()])))
        self.assertEqual(
            (report["arch"], report["kind"], report["pie"], report["minos"]),
            ("arm64", "execute", True, "26.0"),
        )

    def test_system_load_path(self):
        self.assertTrue(macho.system_load_path("/usr/lib/libc++.1.dylib"))
        self.assertTrue(macho.system_load_path("/System/Library/Frameworks/CoreFoundation.framework"))
        self.assertFalse(macho.system_load_path("/opt/local/lib/libx.dylib"))
        self.assertFalse(macho.system_load_path("/usr/lib/"))


class RelocateTest(unittest.TestCase):
    def test_forbidden_ref_detected(self):
        binary = REPO_ROOT / ".work" / "tmp" / "blob.bin"
        binary.write_bytes(b"\x00built in /some/build/dir\x00")
        try:
            hits = relocate.scan_forbidden_refs(binary, [b"/some/build/dir", b"/other"])
            self.assertEqual(hits, [b"/some/build/dir"])
        finally:
            binary.unlink(missing_ok=True)

    def test_copy_refuses_overwrite(self):
        source = REPO_ROOT / ".work" / "tmp" / "copy-src"
        source.mkdir(parents=True, exist_ok=True)
        try:
            with self.assertRaises(FileExistsError):
                relocate.copy_tree(source, REPO_ROOT / ".work" / "tmp")
        finally:
            source.rmdir()


class GateTest(unittest.TestCase):
    def test_gate_rejects_failure(self):
        findings = [validate_product.ProductFinding("x", False, "bad")]
        with self.assertRaises(validate_product.GateError):
            validate_product.gate(findings)

    def test_gate_accepts_all_ok(self):
        findings = [validate_product.ProductFinding("x", True, "good")]
        validate_product.gate(findings)

    def test_prune_removes_excluded_payload(self):
        root = REPO_ROOT / ".work" / "tmp" / "prune-root"
        (root / "bin").mkdir(parents=True, exist_ok=True)
        (root / "bin" / "npm").write_text("x", encoding="utf-8")
        (root / "share" / "man").mkdir(parents=True, exist_ok=True)
        try:
            removed = packager.prune_to_contract(root)
            self.assertIn("bin/npm", removed)
            self.assertIn("share", removed)
            self.assertFalse((root / "bin" / "npm").exists())
        finally:
            import shutil

            shutil.rmtree(root, ignore_errors=True)

    def test_archive_refuses_overwrite(self):
        root = REPO_ROOT / ".work" / "tmp" / "arch-root"
        root.mkdir(parents=True, exist_ok=True)
        archive = REPO_ROOT / ".work" / "tmp" / "existing.tar.gz"
        archive.write_bytes(b"x")
        try:
            with self.assertRaises(packager.PackageError):
                packager.create_archive(root, archive)
        finally:
            archive.unlink(missing_ok=True)
            root.rmdir()


if __name__ == "__main__":
    unittest.main()
