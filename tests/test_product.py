import struct
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from buildsys import macho, relocate, validate_product
from buildsys import package as packager


def synthetic_header(cputype: int, filetype: int, pie: bool, minos: int) -> bytes:
    flags = 0x200000 if pie else 0
    header = struct.pack("<8I", 0xFEEDFACF, cputype, 0, filetype, 1, 24, flags, 0)
    command = struct.pack("<2I4I", 0x32, 24, 1, minos, 0x1B0000, 0)
    return header + command


ARM64 = 12 | 0x01000000
X86_64 = 7 | 0x01000000
OS_13_5 = (13 << 16) | (5 << 8)


class MachOTest(unittest.TestCase):
    def test_good_arm64_pie_passes(self):
        path = REPO_ROOT / ".work" / "tmp" / "good.macho"
        path.write_bytes(synthetic_header(ARM64, 2, True, OS_13_5))
        try:
            info = macho.inspect(path)
            self.assertTrue(info.pie)
            self.assertEqual(info.minos, "13.5.0")
            failed = [finding for finding in macho.validate_executable(info, "13.5") if not finding.ok]
            self.assertEqual(failed, [])
        finally:
            path.unlink(missing_ok=True)

    def test_missing_pie_fails(self):
        path = REPO_ROOT / ".work" / "tmp" / "nopie.macho"
        path.write_bytes(synthetic_header(ARM64, 2, False, OS_13_5))
        try:
            info = macho.inspect(path)
            names = [finding.name for finding in macho.validate_executable(info, "13.5") if not finding.ok]
            self.assertIn("pie", names)
        finally:
            path.unlink(missing_ok=True)

    def test_wrong_arch_fails(self):
        path = REPO_ROOT / ".work" / "tmp" / "x64.macho"
        path.write_bytes(synthetic_header(X86_64, 2, True, OS_13_5))
        try:
            info = macho.inspect(path)
            names = [finding.name for finding in macho.validate_executable(info, "13.5") if not finding.ok]
            self.assertIn("thin-arm64", names)
        finally:
            path.unlink(missing_ok=True)

    def test_garbage_rejected(self):
        path = REPO_ROOT / ".work" / "tmp" / "garbage.macho"
        path.write_bytes(b"not a mach-o file at all!!!!!!!!")
        try:
            with self.assertRaises(macho.MachOError):
                macho.inspect(path)
        finally:
            path.unlink(missing_ok=True)

    def test_old_minos_rejected(self):
        path = REPO_ROOT / ".work" / "tmp" / "old.macho"
        path.write_bytes(synthetic_header(ARM64, 2, True, (12 << 16)))
        try:
            info = macho.inspect(path)
            names = [finding.name for finding in macho.validate_executable(info, "13.5") if not finding.ok]
            self.assertIn("deployment-floor", names)
        finally:
            path.unlink(missing_ok=True)


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
