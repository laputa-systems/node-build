import hashlib
import json
import struct
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from buildlib import macho

from buildsys import (
    macho_paths,
    node,
    product,
    qualify_runner,
    relocate,
    reproduce,
    smoke,
    validate_product,
)
from buildsys import package as packager
from tests.test_elf import build_image


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
        self.assertTrue(macho_paths.system_load_path("/usr/lib/libc++.1.dylib"))
        self.assertTrue(macho_paths.system_load_path("/System/Library/Frameworks/CoreFoundation.framework"))
        self.assertFalse(macho_paths.system_load_path("/opt/local/lib/libx.dylib"))
        self.assertFalse(macho_paths.system_load_path("/usr/lib/"))


class QualificationReceiptTest(unittest.TestCase):
    triple = "aarch64-apple-darwin"

    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.archive = (
            self.root / "dist" / self.triple
            / product.archive_name(product.NODE_VERSION, self.triple)
        )
        self.archive.parent.mkdir(parents=True)
        self.work = self.root / "build" / self.triple / "qualify"
        self.receipt = self.work / "qualify-record.json"

    def write_archive(self, *, with_binary: bool):
        source = self.root / "fixture"
        source.mkdir()
        if with_binary:
            binary = source / "bin" / "node"
            binary.parent.mkdir()
            binary.write_bytes(b"node fixture")
        with tarfile.open(self.archive, "w:xz") as bundle:
            bundle.add(source, arcname="node")

    def test_missing_archive_and_missing_binary_leave_no_receipt(self):
        with self.assertRaisesRegex(qualify_runner.QualifyError, "no packaged archive"):
            qualify_runner.qualify(self.root, self.triple)
        self.assertFalse(self.work.exists())
        self.write_archive(with_binary=False)
        with self.assertRaisesRegex(qualify_runner.QualifyError, "archive has no bin/node"):
            qualify_runner.qualify(self.root, self.triple)
        self.assertFalse(self.receipt.exists())

    def test_qualification_persists_check_results_and_clears_the_previous_extraction(self):
        self.write_archive(with_binary=True)
        self.work.mkdir(parents=True)
        old_file = self.work / "old"
        old_file.write_text("previous run", encoding="utf-8")
        extracted = self.work / "extracted" / "node"
        content = validate_product.ProductFinding("native image", True, "arm64")
        compiler = smoke.SmokeFinding("compile addon", True, "compiled")
        network = smoke.SmokeFinding("loopback", False, "failed")
        moved = relocate.RelocationFinding("run after move", True, "executed")
        with (
            patch.object(validate_product, "validate_install_tree", return_value=[content]) as validate,
            patch.object(smoke, "run_suite", return_value=[compiler, network]) as run_smoke,
            patch.object(relocate, "verify_relocation", return_value=[moved]) as move,
        ):
            with self.assertRaisesRegex(qualify_runner.QualifyError, "qualification failed: loopback"):
                qualify_runner.qualify(self.root, self.triple)
            self.assertFalse(old_file.exists())
            self.assertEqual((extracted / "bin" / "node").read_bytes(), b"node fixture")
            self.assertTrue((self.work / "smoke-work").is_dir())
            stage = str(self.root / "build" / self.triple / "stage").encode()
            source = str(self.root / "build" / "src" / f"node-v{product.NODE_VERSION}").encode()
            validate.assert_called_once_with(extracted, "arm64", "26.0", [stage], [source])
            run_smoke.assert_called_once_with(
                extracted / "bin" / "node", extracted, extracted / "include" / "node",
                self.work / "smoke-work", self.root / "tests" / "fixtures", self.triple,
            )
            move.assert_called_once_with(
                extracted, self.work / "reloc-a", self.work / "reloc b with spaces", [stage], [source],
            )
            failed = json.loads(self.receipt.read_text(encoding="utf-8"))
            self.assertEqual(failed, {
                "archive": str(self.archive),
                "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest(),
                "product_checks": [{"name": "native image", "ok": True, "detail": "arm64"}],
                "smoke": [
                    {"name": "compile addon", "ok": True, "detail": "compiled"},
                    {"name": "loopback", "ok": False, "detail": "failed"},
                ],
                "relocation": [{"name": "run after move", "ok": True, "detail": "executed"}],
                "smoke_passed": 1,
                "smoke_total": 2,
            })
            validate.return_value = [validate_product.ProductFinding("native image", False, "wrong platform")]
            move.return_value = [relocate.RelocationFinding("run after move", False, "missing binary")]
            with self.assertRaisesRegex(qualify_runner.QualifyError, r"qualification failed: native image, loopback, run after move$"):
                qualify_runner.qualify(self.root, self.triple)
            validate.return_value = [content]
            run_smoke.return_value = [compiler]
            move.return_value = [moved]
            result = qualify_runner.qualify(self.root, self.triple)
            self.assertEqual(result, json.loads(self.receipt.read_text(encoding="utf-8")))
            self.assertEqual(result["smoke_total"], 1)
            self.assertEqual(result["smoke_passed"], 1)


class ReproduceReceiptTest(unittest.TestCase):
    def check_reproduction(self, triple, images, normalized, verdict, offsets, *, previous=True):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp") as temp:
            root = Path(temp)
            work = root / "build" / triple
            source = root / "build" / "src"
            retained = root / "build" / "reproduce-keep"
            unrelated = root / "build" / "other-target"
            if previous:
                for directory in (work, source, retained, unrelated):
                    directory.mkdir(parents=True, exist_ok=True)
                    (directory / "old").write_bytes(b"previous")
            remaining = iter(images)

            def build_fresh(repo, target, jobs):
                self.assertEqual((repo, target, jobs), (root, triple, 3))
                self.assertFalse(work.exists())
                self.assertFalse(source.exists())
                source.mkdir()
                work.mkdir()
                output = work / "node"
                output.write_bytes(next(remaining))
                return output

            with patch.object(node, "build", side_effect=build_fresh) as builder:
                result = reproduce.reproduce(root, triple, 3)
            self.assertEqual(builder.call_count, 2)
            if previous:
                self.assertEqual((unrelated / "old").read_bytes(), b"previous")
            self.assertIn("build", {path.name for path in root.iterdir()})
            self.assertIn("reproduce-keep", {path.name for path in retained.parent.iterdir()})
            self.assertIn("reproduce-record.json", {path.name for path in work.iterdir()})
            self.assertEqual(sorted(path.name for path in retained.iterdir()), ["attempt-1-node", "attempt-2-node"])
            self.assertEqual((retained / "attempt-1-node").read_bytes(), images[0])
            self.assertEqual((retained / "attempt-2-node").read_bytes(), images[1])
            self.assertEqual(result, {
                "triple": triple,
                "attempts": [
                    {
                        "attempt": index,
                        "raw_sha256": hashlib.sha256(raw).hexdigest(),
                        "normalized_sha256": hashlib.sha256(clean).hexdigest(),
                        "size": len(raw),
                    }
                    for index, (raw, clean) in enumerate(zip(images, normalized, strict=True), 1)
                ],
                "raw_match": images[0] == images[1],
                "normalized_match": normalized[0] == normalized[1],
                "differing_chunk_offsets": offsets,
                "verdict": verdict,
            })
            self.assertEqual(json.loads((work / "reproduce-record.json").read_text(encoding="utf-8")), result)

    def test_persists_exact_normalized_and_divergent_macho_results(self):
        first = make_macho([struct.pack("<II16s", macho.LC_UUID, 24, bytes(range(16)))])
        relink = make_macho([struct.pack("<II16s", macho.LC_UUID, 24, bytes(reversed(range(16))))])
        clean = make_macho([struct.pack("<II16s", macho.LC_UUID, 24, bytes(16))])
        triple = "aarch64-apple-darwin"
        cases = (
            (first, clean, "bit-for-bit reproducible", []),
            (relink, clean, "content identical outside Mach-O signing metadata (UUID and ad-hoc signature regenerate per link)", []),
            (relink + b"changed", clean + b"changed", "content differs beyond signing metadata; not reproducible", [0, len(clean)]),
        )
        for second, clean_second, verdict, offsets in cases:
            with self.subTest(verdict=verdict):
                self.check_reproduction(triple, (first, second), (clean, clean_second), verdict, offsets)

    def test_reports_elf_build_id_only_changes(self):
        first = build_image()
        self.assertEqual(first[-20:], bytes([171]) * 20)
        second = first[:-20] + bytes(range(20))
        clean = first[:-20] + bytes(20)
        self.check_reproduction(
            "x86_64-unknown-linux-musl", (first, second), (clean, clean),
            "content identical outside ELF build-ID (NT_GNU_BUILD_ID regenerates per link)", [], previous=False,
        )


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

    def test_archive_is_deterministic_under_node_prefix(self):
        import os
        import shutil
        import tarfile
        import time

        root = REPO_ROOT / ".work" / "tmp" / "det-root"
        (root / "bin").mkdir(parents=True, exist_ok=True)
        (root / "bin" / "node").write_bytes(b"binary")
        (root / "bin" / "node").chmod(0o755)
        (root / "LICENSE").write_text("license", encoding="utf-8")
        first = REPO_ROOT / ".work" / "tmp" / "det-first.tar.xz"
        second = REPO_ROOT / ".work" / "tmp" / "det-second.tar.xz"
        try:
            packager.create_archive(root, first)
            os.utime(root / "LICENSE", (time.time() + 3600, time.time() + 3600))
            packager.create_archive(root, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first) as tar:
                names = [member.name for member in tar.getmembers()]
            self.assertEqual(names, ["node", "node/LICENSE", "node/bin", "node/bin/node"])
        finally:
            shutil.rmtree(root, ignore_errors=True)
            first.unlink(missing_ok=True)
            second.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
