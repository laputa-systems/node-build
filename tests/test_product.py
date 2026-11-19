import hashlib
import json
import struct
import subprocess
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


class MachOPathTest(unittest.TestCase):
    def test_references_resolve_against_the_image_or_actual_executables(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp") as temp:
            outside = Path(temp).resolve()
            install = outside / "node"
            image = install / "lib" / "artifact.dylib"
            node_path = install / "bin" / "node"
            helper = install / "helpers" / "tool"
            for entry in (image, node_path, helper):
                entry.parent.mkdir(parents=True)
                entry.touch()
            self.assertEqual(macho_paths.resolve_image_path("@loader_path", image, install), image.parent)
            self.assertEqual(macho_paths.resolve_image_path("@loader_path/artifact.dylib", image, install), image)
            self.assertEqual(macho_paths.resolve_image_path("@executable_path", image, install, node_path), node_path.parent)
            self.assertIsNone(macho_paths.resolve_image_path("@executable_path", image, install))
            self.assertIsNone(macho_paths.resolve_image_path("@executable_path/program", image, install))
            self.assertEqual(
                macho_paths.rpath_directories("@executable_path", image, install, [node_path, helper]),
                [node_path.parent, helper.parent],
            )
            self.assertEqual(
                macho_paths.rpath_directories("@executable_path/resources", image, install, [node_path, helper]),
                [node_path.parent / "resources", helper.parent / "resources"],
            )
            self.assertEqual(macho_paths.rpath_directories("@loader_path/artifact.dylib", image, install, [node_path]), [image])
            self.assertEqual(macho_paths.rpath_directories("@loader_path", image, install, [node_path]), [image.parent])
            self.assertEqual(macho_paths.rpath_directories("/usr/lib", image, install, [node_path]), [])
            self.assertEqual(macho_paths.resolve_image_path(str(node_path), image, install), node_path)
            self.assertIsNone(macho_paths.resolve_image_path(str(outside / "README"), image, install))
            self.assertIsNone(macho_paths.resolve_image_path("artifact.dylib", image, install))
            self.assertFalse(macho_paths.path_inside_root(Path("bin/node"), install))

    def test_system_paths_use_the_normalized_system_spelling(self):
        self.assertTrue(macho_paths.system_load_path("/usr/lib/libSystem.B.dylib"))
        self.assertTrue(macho_paths.system_load_path("/System/Library/Frameworks/CoreFoundation.framework"))
        self.assertFalse(macho_paths.system_load_path("/usr/lib//libSystem.B.dylib"))
        self.assertFalse(macho_paths.system_load_path("/opt/fixture/lib/runtime.dylib"))
        self.assertFalse(macho_paths.system_load_path("/System/Library/"))


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
    def test_relocation_runs_the_installed_node_under_both_paths(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp") as temp:
            work = Path(temp)
            stage = work / "original"
            binary = stage / "bin" / "node"
            binary.parent.mkdir(parents=True)
            binary.write_text(
                "#!/bin/sh\n"
                '[ "$1" = "--version" ] || exit 8\n'
                '# /fixture/source/checkout\n'
                'printf "v26.12.1\\n"\n',
                encoding="utf-8",
            )
            binary.chmod(0o755)
            (stage / "default.conf").write_bytes(b"fixture settings")
            (stage / "settings.conf").symlink_to("default.conf")
            first = work / "relocated"
            second = work / "relocated with spaces"
            findings = relocate.verify_relocation(
                stage, first, second, [b"/fixture/stage"], [b"/fixture/source/checkout"],
            )
            self.assertEqual(findings, [
                relocate.RelocationFinding("no-stage-refs", True, "no stage path leaks"),
                relocate.RelocationFinding("info-source-refs", True, "1 upstream-inert config strings"),
                relocate.RelocationFinding("relocate-plain", True, "v26.12.1"),
                relocate.RelocationFinding("relocate-with spaces", True, "v26.12.1"),
            ])
            self.assertEqual((first / "bin" / "node").read_bytes(), binary.read_bytes())
            self.assertEqual((second / "bin" / "node").read_bytes(), binary.read_bytes())
            self.assertFalse((second / "settings.conf").is_symlink())
            self.assertEqual((second / "settings.conf").read_bytes(), b"fixture settings")

    def test_relocation_reports_existing_paths_and_failed_programs(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp") as temp:
            work = Path(temp)
            stage = work / "original"
            binary = stage / "bin" / "node"
            binary.parent.mkdir(parents=True)
            binary.write_text(
                "#!/bin/sh\n# /fixture/stage\n"
                'printf "fixture failure\\n" >&2\nexit 7\n',
                encoding="utf-8",
            )
            binary.chmod(0o755)
            first = work / "existing"
            first.mkdir()
            old = first / "keep"
            old.write_bytes(b"previous run")
            second = work / "fresh with spaces"
            findings = relocate.verify_relocation(stage, first, second, [b"/fixture/stage"], [])
            self.assertEqual(findings, [
                relocate.RelocationFinding("no-stage-refs", False, "stage prefixes: [b'/fixture/stage']"),
                relocate.RelocationFinding("info-source-refs", True, "none"),
                relocate.RelocationFinding("relocate-plain", False, f"refusing to overwrite existing directory: {first}"),
                relocate.RelocationFinding("relocate-with spaces", False, f"{second / 'bin' / 'node'} --version failed: fixture failure\n"),
            ])
            self.assertEqual(old.read_bytes(), b"previous run")
            self.assertEqual((second / "bin" / "node").read_bytes(), binary.read_bytes())

    def test_version_probe_uses_the_default_and_requested_deadlines(self):
        binary = Path("/fixture/path with spaces/node")
        command = [str(binary), "--version"]
        result = subprocess.CompletedProcess(command, 0, stdout="v26.12.1\n", stderr="")
        with patch.object(relocate.subprocess, "run", return_value=result) as run:
            self.assertEqual(relocate.run_version(binary), "v26.12.1")
            self.assertEqual(run.call_args.kwargs.get("timeout"), 60)
            self.assertEqual(relocate.run_version(binary, timeout=3), "v26.12.1")
            self.assertEqual(run.call_args.kwargs.get("timeout"), 3)

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


class InstalledProductTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=REPO_ROOT / ".work" / "tmp")
        self.addCleanup(temp.cleanup)
        self.install = Path(temp.name) / "node"
        self.binary = self.install / "bin" / "node"
        self.binary.parent.mkdir(parents=True)

    def test_checks_linux_release_layout_and_distinguishes_embedded_paths(self):
        headers = self.install / "include" / "node"
        headers.mkdir(parents=True)
        (headers / "node_api.h").write_bytes(b"node API")
        (headers / "node.h").write_bytes(b"node headers")
        (self.install / "LICENSE").write_bytes(b"license fixture")
        source = b"/fixture/source/node"
        stage = b"/fixture/stage/node"
        base = build_image()
        self.binary.write_bytes(base + source)
        findings = validate_product.validate_install_tree(self.install, "x86_64", "1.2.6", [stage], [source])
        self.assertEqual([finding.name for finding in findings if not finding.ok], [])
        self.assertIn(validate_product.ProductFinding("info-source-refs", True, "1 upstream-inert config strings"), findings)
        self.assertIn(validate_product.ProductFinding("no-stage-refs", True, "no stage path leaks"), findings)

        (headers / "node_api.h").unlink()
        (self.install / "LICENSE").unlink()
        (self.binary.parent / "npm").write_bytes(b"unexpected tool")
        self.binary.write_bytes(base + stage)
        findings = validate_product.validate_install_tree(self.install, "x86_64", "1.2.6", [stage], [source])
        self.assertEqual([finding for finding in findings if not finding.ok], [
            validate_product.ProductFinding("layout-LICENSE", False, "missing"),
            validate_product.ProductFinding("header-node_api.h", False, "missing"),
            validate_product.ProductFinding("absent-bin/npm", False, "must not ship"),
            validate_product.ProductFinding("no-stage-refs", False, f"stage prefixes: {[stage]}"),
        ])
        self.assertIn(validate_product.ProductFinding("info-source-refs", True, "none"), findings)

    def test_classifies_macos_architecture_platform_minimum_and_signature(self):
        self.binary.write_bytes(make_macho([build_version_command(), named_command(macho.LC_LOAD_DYLIB, "/usr/lib/libc++.1.dylib")]))
        with patch.object(macho, "signature_status", return_value=(True, "fixture signature")):
            findings = validate_product.macho_tree_checks(self.install, "arm64", "26.0")
        self.assertEqual([finding for finding in findings if not finding.ok], [])

        self.binary.write_bytes(make_macho(
            [build_version_command(platform=2, minos=25 << 16)], cputype=macho.CPU_TYPE_X86_64, flags=0,
        ))
        with patch.object(macho, "signature_status", return_value=(False, "invalid fixture signature")):
            failures = [finding for finding in validate_product.macho_tree_checks(self.install, "arm64", "26.0") if not finding.ok]
        self.assertEqual(failures, [
            validate_product.ProductFinding("macho-arch", False, "bin/node: x86_64"),
            validate_product.ProductFinding("macho-platform", False, "bin/node: ios"),
            validate_product.ProductFinding("macho-minos", False, "bin/node: expected 26.0, got 25.0"),
            validate_product.ProductFinding("macho-signatures", False, "bin/node: invalid fixture signature"),
            validate_product.ProductFinding("macho-non-pie", False, "bin/node"),
        ])

    def test_macos_runtime_search_resolves_a_sibling_library(self):
        library = self.install / "lib" / "fixture.dylib"
        library.parent.mkdir()
        library.write_bytes(make_macho([build_version_command()], filetype=macho.MH_DYLIB))
        self.binary.write_bytes(make_macho([
            build_version_command(),
            named_command(macho.LC_RPATH, "@loader_path/../lib"),
            named_command(macho.LC_LOAD_DYLIB, "@rpath/fixture.dylib"),
        ]))
        with patch.object(macho, "signature_status", return_value=(True, "fixture signature")):
            findings = validate_product.macho_tree_checks(self.install, "arm64", "26.0")
            self.assertEqual([finding for finding in findings if not finding.ok], [])
            library.unlink()
            failed = [finding for finding in validate_product.macho_tree_checks(self.install, "arm64", "26.0") if not finding.ok]
        self.assertEqual(failed, [
            validate_product.ProductFinding("macho-unresolved-deps", False, "bin/node -> @rpath/fixture.dylib"),
        ])


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
