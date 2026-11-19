import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from buildlib import hashing, macho, release

import build
from buildsys import package, product, recipes, targets, validate_product
from buildsys import release as release_assembler
from buildsys import reproduce as reproduce_runner
from tests.test_elf import build_image
from tests.test_product import build_version_command, make_macho

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"
TRIPLE = "aarch64-apple-darwin"


class ReleaseInputTest(unittest.TestCase):
    def setUp(self):
        tmp_root = REPO_ROOT / ".work" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        self.scratch = tempfile.TemporaryDirectory(dir=tmp_root)
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)

    def test_record_reports_missing_invalid_and_non_object_inputs(self):
        path = self.root / "record.json"
        for label in ("build receipt", "package record"):
            with self.subTest(label=label):
                with self.assertRaises(release_assembler.AssemblyError) as error:
                    release_assembler.load_record(path, label)
                self.assertEqual(str(error.exception), f"missing {label}: {path} (run package/qualify first)")
                path.write_text("{", encoding="utf-8")
                with self.assertRaises(release_assembler.AssemblyError) as error:
                    release_assembler.load_record(path, label)
                self.assertTrue(str(error.exception).startswith(f"invalid {label}: {path}: "))
                self.assertIsInstance(error.exception.__cause__, ValueError)
                path.write_text("[]", encoding="utf-8")
                with self.assertRaises(release_assembler.AssemblyError) as error:
                    release_assembler.load_record(path, label)
                self.assertEqual(str(error.exception), f"invalid {label}: {path}: expected an object")
                path.unlink()
        path.write_text('{"name": "café", "nested": {"ok": true}}', encoding="utf-8")
        self.assertEqual(release_assembler.load_record(path, "record"), {"name": "café", "nested": {"ok": True}})

    def test_record_uses_utf8_with_a_non_utf8_process_locale(self):
        path = self.root / "record.json"
        path.write_text('{"name": "café"}', encoding="utf-8")
        check_record = (
            "import locale\n"
            "import sys\n"
            "from pathlib import Path\n"
            "from buildsys.release import load_record\n"
            "assert locale.getencoding().lower() not in {'utf-8', 'utf8'}\n"
            "assert load_record(Path(sys.argv[1]), 'record') == {'name': 'caf\\u00e9'}\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", check_record, str(path)],
            cwd=REPO_ROOT,
            env=dict(os.environ, LC_ALL="C", PYTHONCOERCECLOCALE="0", PYTHONUTF8="0"),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_checkout_revision_and_cleanliness_follow_real_git_state(self):
        with self.assertRaisesRegex(release_assembler.AssemblyError, "not a git checkout"):
            release_assembler.git_revision(self.root)
        self.assertIsNone(release_assembler.clean_build_revision(self.root))
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        checkout = self.root / "checkout\nwith trailing space "
        checkout.mkdir()
        (checkout / ".gitignore").write_text("ignored\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=checkout, env=env, check=True)
        with self.assertRaisesRegex(release_assembler.AssemblyError, "^not a git checkout$"):
            release_assembler.git_revision(checkout)
        for command in (["add", "."], ["commit", "-qm", "initial"]):
            subprocess.run(["git", *command], cwd=checkout, env=env, check=True)
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=checkout, env=env,
                                  capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(release_assembler.git_revision(checkout), revision)
        self.assertEqual(release_assembler.clean_build_revision(checkout), revision)
        (checkout / "ignored").write_text("ignored")
        self.assertEqual(release_assembler.clean_build_revision(checkout), revision)
        child = checkout / "child"
        child.mkdir()
        with self.assertRaisesRegex(release_assembler.AssemblyError, "not a git checkout root"):
            release_assembler.git_revision(child)
        subprocess.run(["git", "config", "status.showUntrackedFiles", "no"], cwd=checkout, env=env, check=True)
        (child / "untracked").write_text("dirty")
        self.assertIsNone(release_assembler.clean_build_revision(checkout))
        with patch.dict(os.environ, {"PATH": str(self.root)}):
            self.assertIsNone(release_assembler.clean_build_revision(checkout))
        (checkout / ".git" / "index").write_bytes(b"incomplete Git index")
        with self.assertRaisesRegex(release_assembler.AssemblyError, "git status failed"):
            release_assembler.git_dirty(checkout)
        self.assertIsNone(release_assembler.clean_build_revision(checkout))


class PackageStageTest(unittest.TestCase):
    def setUp(self):
        tmp_root = REPO_ROOT / ".work" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        self.scratch = tempfile.TemporaryDirectory(dir=tmp_root)
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)

    def test_installer_replaces_old_tree_and_records_child_output(self):
        source = self.root / "source"
        (source / "tools").mkdir(parents=True)
        (source / "tools" / "install.py").write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "command, dest_option, dest, prefix_option, prefix = sys.argv[1:]\n"
            "assert (command, dest_option, prefix_option, prefix) == "
            "('install', '--dest-dir', '--prefix', '/node')\n"
            "mode = Path('install-mode').read_text()\n"
            "print('installer stdout: ' + mode)\n"
            "print('installer stderr: ' + mode, file=sys.stderr)\n"
            "if mode != 'missing':\n"
            "    bin_dir = Path(dest) / prefix.lstrip('/') / 'bin'\n"
            "    bin_dir.mkdir(parents=True)\n"
            "    (bin_dir / 'node').write_bytes(b'fixture node')\n"
            "if mode == 'failure':\n"
            "    sys.exit(7)\n",
            encoding="utf-8",
        )
        recipe = recipes.recipe_for_triple(TRIPLE)
        stage = self.root / "stage with spaces"
        installed = stage / "node"
        installed.mkdir(parents=True)
        old_file = installed / "previous-install"
        old_file.write_text("obsolete", encoding="utf-8")
        (stage / "stage-marker").write_text("keep", encoding="utf-8")

        spawn = subprocess.Popen
        children = []

        def start_child(*args, **kwargs):
            child = spawn(*args, **kwargs)
            children.append(child)
            return child

        for mode, message in (("complete", None), ("failure", "install failed"), ("missing", "install produced no tree")):
            with self.subTest(mode=mode), patch.object(package.subprocess, "Popen", side_effect=start_child):
                (source / "install-mode").write_text(mode, encoding="utf-8")
                if message is None:
                    self.assertEqual(package.install_to_stage(source, stage, recipe), installed)
                    self.assertEqual((installed / "bin" / "node").read_bytes(), b"fixture node")
                else:
                    with self.assertRaisesRegex(package.PackageError, message):
                        package.install_to_stage(source, stage, recipe)
                self.assertFalse(old_file.exists())
                self.assertEqual((stage / "stage-marker").read_text(encoding="utf-8"), "keep")
                output = (stage / "install.log").read_text(encoding="utf-8").splitlines()
                self.assertCountEqual(output, [f"installer stdout: {mode}", f"installer stderr: {mode}"])
                child = children.pop()
                self.assertEqual(child.returncode, 7 if mode == "failure" else 0)
                assert child.stdout is not None
                self.assertTrue(child.stdout.closed)

    def test_hardening_report_persists_native_image_findings(self):
        cases = (
            ("x86_64", "1.2.6", build_image(), "elf-hardening", True),
            ("arm64", "26.0", make_macho([build_version_command()], flags=0), "macho-non-pie", False),
        )
        for machine, target, image, finding, expected in cases:
            with self.subTest(machine=machine):
                stage = self.root / machine
                (stage / "bin").mkdir(parents=True)
                (stage / "bin" / "node").write_bytes(image)
                (stage / "LICENSE").write_text("fixture license", encoding="utf-8")
                destination = self.root / f"{machine}.json"
                with patch.object(macho, "signature_status", return_value=(False, "fixture unsigned")) as signature:
                    report = package.write_hardening_report(stage, machine, target, destination)
                self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), report)
                self.assertEqual(set(report["images"]), {"bin/node"})
                self.assertEqual(report["images"]["bin/node"]["arch"], machine)
                self.assertEqual(report["deployment_target"], target)
                checks = {check["name"]: check["ok"] for check in report["checks"]}
                self.assertIs(checks[finding], expected)
                if machine == "arm64":
                    signature.assert_called_once_with(stage.resolve() / "bin" / "node")
                    self.assertIs(checks["macho-signatures"], False)
                else:
                    signature.assert_not_called()


class PackageRecordTest(unittest.TestCase):
    def test_packaging_links_receipt_and_archive(self):
        tmp_root = REPO_ROOT / ".work" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=tmp_root) as scratch:
            root = Path(scratch)
            source = root / "source"
            source.mkdir()
            (source / "LICENSE").write_text("fixture license")
            receipt = root / "build" / TRIPLE / "build-receipt.json"
            stage = root / "fixture-install"
            (stage / "bin").mkdir(parents=True)
            (stage / "bin" / "node").write_bytes(b"fixture binary")
            with (
                patch.object(package, "install_to_stage", return_value=stage) as install,
                patch.object(package, "write_hardening_report", return_value={}),
                patch.object(validate_product, "validate_install_tree", return_value=[
                    validate_product.ProductFinding("fixture", True, ""),
                ]),
            ):
                with self.assertRaisesRegex(package.PackageError, "missing build receipt"):
                    package.package(root, TRIPLE, source)
                install.assert_not_called()
                receipt.parent.mkdir(parents=True)
                receipt.write_text('{"fixture": true}\n')
                with self.assertRaisesRegex(package.PackageError, "build receipt has no node binary digest"):
                    package.package(root, TRIPLE, source)
                install.assert_not_called()
                receipt.write_text(json.dumps({"built_node_sha256": "0" * 64}))
                with self.assertRaisesRegex(package.PackageError, "installed node does not match build receipt"):
                    package.package(root, TRIPLE, source)
                self.assertFalse((root / "dist").exists())
                self.assertFalse((receipt.parent / "package-record.json").exists())
                receipt.write_text(json.dumps({"built_node_sha256": hashing.sha256_file(stage / "bin" / "node")}))
                result = package.package(root, TRIPLE, source)
            archive = Path(result["archive"])
            record = json.loads((receipt.parent / "package-record.json").read_text())
            self.assertEqual(record["build_receipt_sha256"], hashing.sha256_file(receipt))
            self.assertEqual(record["sha256"], hashing.sha256_file(archive))


class StageTripleTest(unittest.TestCase):
    def setUp(self):
        tmp_root = REPO_ROOT / ".work" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        self.scratch = tempfile.TemporaryDirectory(dir=tmp_root)
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.archive = self.root / "input.tar.xz"
        self.archive.write_bytes(b"sealed archive bytes")
        self.staging = self.root / "staging"
        self.staging.mkdir()
        self.digest = hashing.sha256_file(self.archive)
        self.validated = {
            "archive": self.archive,
            "package_record": {"sha256": self.digest, "hardening": {"pie": "enabled"}},
            "build_receipt": {
                "source": {"name": "upstream"}, "toolchain": {"compiler": "clang"},
                "recipe": {"flags": ["release"]},
            },
            "qualify_record": {
                "product_checks": [{"name": "identity", "ok": True}],
                "smoke_passed": 2, "smoke_total": 3,
                "relocation": [{"name": "move", "ok": True}],
            },
        }

    def test_stages_archive_and_manifest_metadata(self):
        release_assembler.stage_triple(self.validated, TRIPLE, self.staging, "a" * 40, "b" * 64)
        archive_name = product.archive_name(product.NODE_VERSION, TRIPLE)
        self.assertEqual((self.staging / archive_name).read_bytes(), b"sealed archive bytes")
        manifest = json.loads((self.staging / product.manifest_name(product.NODE_VERSION, TRIPLE)).read_text())
        self.assertEqual(manifest, {
            "schema_version": 1, "product": "node", "version": product.NODE_VERSION,
            "target": TRIPLE, "source_revision": "a" * 40, "sources_lock_sha256": "b" * 64,
            "archive": archive_name, "sha256": self.digest, "size": 20,
            "source": {"name": "upstream"}, "toolchain": {"compiler": "clang"},
            "recipe": {"flags": ["release"]}, "hardening": {"pie": "enabled"},
            "qualification": {
                "product_checks": [{"name": "identity", "ok": True}],
                "smoke_passed": 2, "smoke_total": 3,
                "relocation": [{"name": "move", "ok": True}],
            },
        })

    def test_missing_optional_metadata_is_empty(self):
        self.validated["build_receipt"] = {}
        self.validated["package_record"] = {"sha256": self.digest}
        release_assembler.stage_triple(self.validated, TRIPLE, self.staging, "a" * 40, "b" * 64)
        manifest = json.loads((self.staging / product.manifest_name(product.NODE_VERSION, TRIPLE)).read_text())
        for field in ("source", "toolchain", "recipe", "hardening"):
            self.assertEqual(manifest[field], {})

    def test_rejects_changed_staged_bytes_before_writing_manifest(self):
        self.validated["package_record"] = {"sha256": "0" * 64}
        with self.assertRaises(release_assembler.AssemblyError) as error:
            release_assembler.stage_triple(self.validated, TRIPLE, self.staging, "a" * 40, "b" * 64)
        self.assertEqual(str(error.exception), f"packaged archive changed during staging: {TRIPLE}")
        self.assertEqual([path.name for path in self.staging.iterdir()], [product.archive_name(product.NODE_VERSION, TRIPLE)])

    def test_copy_error_propagates_without_manifest(self):
        self.archive.unlink()
        with self.assertRaises(FileNotFoundError) as error:
            release_assembler.stage_triple(self.validated, TRIPLE, self.staging, "a" * 40, "b" * 64)
        self.assertEqual(error.exception.filename, str(self.archive))
        self.assertEqual(list(self.staging.iterdir()), [])


class AssembleTest(unittest.TestCase):
    def setUp(self):
        tmp_root = REPO_ROOT / ".work" / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        self.work = Path(tempfile.mkdtemp(prefix="assemble-", dir=tmp_root))
        self.addCleanup(self.cleanup)
        env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1",
                   GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        (self.work / "sources.lock.json").write_text('{"schema_version": 1}\n', encoding="utf-8")
        (self.work / ".gitignore").write_text("build/\ndist/\n", encoding="utf-8")
        for command in (["init", "-q"], ["add", "."], ["commit", "-qm", "x"]):
            subprocess.run(["git", *command], cwd=self.work, env=env, check=True)
        self.revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.work, env=env,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        self.write_qualified_fixture(TRIPLE)

    def write_qualified_fixture(self, triple: str):
        archive = self.work / "dist" / triple / product.archive_name(product.NODE_VERSION, triple)
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"archive bytes")
        checks = [{"name": "c", "ok": True, "detail": ""}]
        build = self.work / "build" / triple
        (build / "qualify").mkdir(parents=True)
        receipt = build / "build-receipt.json"
        receipt.write_text(
            json.dumps({
                "sources_lock_sha256": hashing.sha256_file(self.work / "sources.lock.json"),
                "source_revision": self.revision,
            }),
            encoding="utf-8",
        )
        (build / "package-record.json").write_text(
            json.dumps({
                "product_checks": checks, "hardening": {},
                "sha256": hashing.sha256_file(archive),
                "build_receipt_sha256": hashing.sha256_file(receipt),
            }),
            encoding="utf-8",
        )
        (build / "qualify" / "qualify-record.json").write_text(
            json.dumps({
                "sha256": hashing.sha256_file(archive),
                "product_checks": checks, "smoke": checks, "relocation": checks,
                "smoke_passed": 1, "smoke_total": 1,
            }),
            encoding="utf-8",
        )

    def cleanup(self):
        import shutil

        shutil.rmtree(self.work, ignore_errors=True)

    def test_assembles_standard_assets_with_sorted_checksums(self):
        result = release_assembler.assemble_all(self.work, (TRIPLE,))
        self.assertEqual(
            tuple(result["assets"]), product.expected_release_assets(product.NODE_VERSION, (TRIPLE,))
        )
        release_dir = self.work / "dist" / product.RELEASE_DIRNAME
        manifest = json.loads(
            (release_dir / product.manifest_name(product.NODE_VERSION, TRIPLE)).read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["product"], "node")
        self.assertEqual(manifest["version"], product.NODE_VERSION)
        self.assertEqual(manifest["target"], TRIPLE)
        self.assertEqual(manifest["source_revision"], self.revision)
        self.assertEqual(
            manifest["sources_lock_sha256"],
            hashing.sha256_file(self.work / "sources.lock.json"),
        )
        lines = (release_dir / release.CHECKSUMS_NAME).read_text(encoding="utf-8").splitlines()
        names = [line.split("  ", 1)[1] for line in lines]
        self.assertEqual(names, sorted(names))
        self.assertNotIn(release.CHECKSUMS_NAME, names)
        self.assertEqual(len(names), 2)

    def test_git_probe_timeout_stops_assembly_and_leaves_build_provenance_unbound(self):
        run = subprocess.run
        for command in ("rev-parse", "status"):
            with self.subTest(command=command):
                def run_with_timeout(args, *, timed_out_command=command, **kwargs):
                    if args[:2] == ["git", timed_out_command]:
                        self.assertEqual(kwargs["timeout"], 60)
                        raise subprocess.TimeoutExpired(args, kwargs["timeout"])
                    return run(args, **kwargs)

                stderr = io.StringIO()
                with (
                    patch.object(release_assembler.subprocess, "run", side_effect=run_with_timeout),
                    patch.object(build, "REPO_ROOT", self.work),
                    contextlib.redirect_stderr(stderr),
                ):
                    self.assertEqual(build.main(["assemble", "--target", TRIPLE]), 2)
                    self.assertIsNone(release_assembler.clean_build_revision(self.work))
                self.assertIn(f"git {command} timed out", stderr.getvalue())
                self.assertFalse((self.work / "dist" / product.RELEASE_DIRNAME).exists())
                self.assertEqual(list((self.work / "build").glob("assembly-tmp*")), [])

    def test_rejects_malformed_records_before_staging(self):
        build = self.work / "build" / TRIPLE
        for relative, label in (
            ("package-record.json", "package record"),
            ("build-receipt.json", "build receipt"),
            ("qualify/qualify-record.json", "qualify record"),
        ):
            path = build / relative
            valid = path.read_bytes()
            for contents in ("[]", "{"):
                with self.subTest(label=label, contents=contents):
                    path.write_text(contents)
                    try:
                        with self.assertRaisesRegex(release_assembler.AssemblyError, f"invalid {label}"):
                            release_assembler.assemble_all(self.work, (TRIPLE,))
                        self.assertFalse((self.work / "dist" / product.RELEASE_DIRNAME).exists())
                    finally:
                        path.write_bytes(valid)

    def test_rejects_incomplete_package_checks_before_staging(self):
        path = self.work / "build" / TRIPLE / "package-record.json"
        record = json.loads(path.read_text())
        for checks in ([], None, [{"name": "c", "ok": "yes"}]):
            with self.subTest(checks=checks):
                path.write_text(json.dumps(record | {"product_checks": checks}))
                with self.assertRaisesRegex(release_assembler.AssemblyError, "package product checks are not all-ok"):
                    release_assembler.assemble_all(self.work, (TRIPLE,))
                self.assertFalse((self.work / "dist" / product.RELEASE_DIRNAME).exists())

    def test_rejects_a_package_record_from_another_archive_or_receipt(self):
        path = self.work / "build" / TRIPLE / "package-record.json"
        valid = json.loads(path.read_text())
        for field, message in (
            ("sha256", "package record does not match packaged archive"),
            ("build_receipt_sha256", "package record does not match build receipt"),
        ):
            with self.subTest(field=field):
                path.write_text(json.dumps(valid | {field: "0" * 64}))
                with self.assertRaisesRegex(release_assembler.AssemblyError, message):
                    release_assembler.assemble_all(self.work, (TRIPLE,))
                self.assertFalse((self.work / "dist" / product.RELEASE_DIRNAME).exists())
                self.assertEqual(list((self.work / "build").glob("assembly-tmp*")), [])

    def test_rejects_a_receipt_from_a_different_checkout_revision(self):
        (self.work / "controller.txt").write_text("another committed controller")
        subprocess.run(["git", "add", "controller.txt"], cwd=self.work, check=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "change controller"],
            cwd=self.work, check=True,
        )
        with self.assertRaisesRegex(release_assembler.AssemblyError, "build receipt checkout revision.*rebuild"):
            release_assembler.assemble_all(self.work, (TRIPLE,))
        self.assertFalse((self.work / "dist" / product.RELEASE_DIRNAME).exists())
        self.assertEqual(list((self.work / "build").glob("assembly-tmp*")), [])

    def test_rejects_stale_or_unbound_lock_before_creating_release(self):
        lock = self.work / "sources.lock.json"
        lock.write_text('{"schema_version": 1, "revision": "new"}\n', encoding="utf-8")
        subprocess.run(["git", "add", "sources.lock.json"], cwd=self.work, check=True)
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "change lock"],
            cwd=self.work, check=True,
        )
        receipt = self.work / "build" / TRIPLE / "build-receipt.json"
        for record in (json.loads(receipt.read_text(encoding="utf-8")), {}):
            with self.subTest(record=record):
                receipt.write_text(json.dumps(record), encoding="utf-8")
                with self.assertRaisesRegex(release_assembler.AssemblyError, "source lock.*rebuild"):
                    release_assembler.assemble_all(self.work, (TRIPLE,))
                self.assertFalse((self.work / "dist" / product.RELEASE_DIRNAME).exists())
                self.assertEqual(list((self.work / "build").glob("assembly-tmp*")), [])

    def test_rejects_incomplete_qualification_before_creating_release(self):
        path = self.work / "build" / TRIPLE / "qualify" / "qualify-record.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        destination = self.work / "dist" / product.RELEASE_DIRNAME
        cases = (
            ({"product_checks": []}, "product_checks"),
            ({"smoke": None}, "smoke"),
            ({"relocation": [{"name": "c", "ok": "yes"}]}, "relocation"),
            ({"smoke_passed": 0}, "smoke counts"),
            ({"smoke_total": True}, "smoke counts"),
        )
        for changes, diagnostic in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(release_assembler.AssemblyError, diagnostic):
                path.write_text(json.dumps(record | changes), encoding="utf-8")
                release_assembler.assemble_all(self.work, (TRIPLE,))
            self.assertFalse(destination.exists())

    def test_rejects_bad_checks_in_each_record_section(self):
        build = self.work / "build" / TRIPLE
        for relative, sections in (
            ("package-record.json", ("product_checks",)),
            ("qualify/qualify-record.json", ("product_checks", "smoke", "relocation")),
        ):
            path = build / relative
            original = path.read_text()
            record = json.loads(original)
            for section in sections:
                for checks in ([{"ok": True}, {"ok": False}], [{"ok": 1}], [None], {"ok": True}):
                    with self.subTest(record=relative, section=section, checks=checks):
                        path.write_text(json.dumps(record | {section: checks}))
                        with self.assertRaisesRegex(release_assembler.AssemblyError, "not all-ok"):
                            release_assembler.assemble_all(self.work, (TRIPLE,))
                        self.assertEqual(list((self.work / "build").glob("assembly-tmp*")), [])
                path.write_text(original)

    def test_reports_the_exact_missing_archive(self):
        archive = self.work / "dist" / TRIPLE / product.archive_name(product.NODE_VERSION, TRIPLE)
        archive.unlink()
        with self.assertRaises(release_assembler.AssemblyError) as error:
            release_assembler.assemble_all(self.work, (TRIPLE,))
        self.assertEqual(str(error.exception), f"missing packaged archive: {archive}")
        self.assertEqual(list((self.work / "build").glob("assembly-tmp*")), [])

    def test_rejects_qualification_for_different_archive(self):
        path = self.work / "build" / TRIPLE / "qualify" / "qualify-record.json"
        record = json.loads(path.read_text())
        for digest in (None, "0" * 64):
            with self.subTest(digest=digest):
                path.write_text(json.dumps(record | {"sha256": digest}))
                with self.assertRaisesRegex(release_assembler.AssemblyError, "qualify record does not match"):
                    release_assembler.assemble_all(self.work, (TRIPLE,))
                self.assertEqual(list((self.work / "build").glob("assembly-tmp*")), [])

    def test_refuses_an_archive_changed_between_validation_and_copy(self):
        archive = self.work / "dist" / TRIPLE / product.archive_name(product.NODE_VERSION, TRIPLE)
        original = archive.read_bytes()
        copyfile = release_assembler.shutil.copyfile

        def replace_then_copy(source: Path, destination: Path):
            self.assertEqual(source, archive)
            archive.write_bytes(b"replacement after qualification")
            return copyfile(source, destination)

        with (
            patch.object(release_assembler.shutil, "copyfile", side_effect=replace_then_copy),
            self.assertRaisesRegex(release_assembler.AssemblyError, "packaged archive changed during staging"),
        ):
            release_assembler.assemble_all(self.work, (TRIPLE,))
        self.assertFalse((self.work / "dist" / product.RELEASE_DIRNAME).exists())
        self.assertEqual(list((self.work / "build").glob("assembly-tmp*")), [])
        archive.write_bytes(original)
        result = release_assembler.assemble_all(self.work, (TRIPLE,))
        self.assertEqual((Path(result["release_dir"]) / archive.name).read_bytes(), original)

    def test_concurrent_assemblers_only_publish_one_complete_release(self):
        rendezvous = Barrier(2)
        write_sums = release.write_sha256sums

        def finish_staging(staging: Path):
            write_sums(staging)
            rendezvous.wait(timeout=10)

        with (
            patch.object(release, "write_sha256sums", side_effect=finish_staging),
            ThreadPoolExecutor(max_workers=2) as workers,
        ):
            attempts = [workers.submit(release_assembler.assemble_all, self.work, (TRIPLE,)) for _ in range(2)]
            failures = [attempt.exception(timeout=15) for attempt in attempts]
        self.assertEqual(failures.count(None), 1)
        refused = next(failure for failure in failures if failure is not None)
        self.assertIsInstance(refused, release_assembler.AssemblyError)
        self.assertIn("refusing to overwrite existing release directory", str(refused))
        final_dir = self.work / "dist" / product.RELEASE_DIRNAME
        release.verify_sha256sums(final_dir)
        self.assertEqual(list((self.work / "build").glob("assembly-tmp*")), [])

    def test_assembly_lists_both_targets_and_all_checksum_assets(self):
        secondary = "x86_64-unknown-linux-musl"
        self.write_qualified_fixture(secondary)
        result = release_assembler.assemble_all(self.work, (secondary, TRIPLE))
        expected_dir = self.work / "dist" / product.RELEASE_DIRNAME
        self.assertEqual(result, {
            "release_dir": str(expected_dir), "targets": [TRIPLE, secondary],
            "assets": list(product.expected_release_assets(product.NODE_VERSION, (TRIPLE, secondary))),
        })
        release.verify_sha256sums(expected_dir)
        self.assertEqual(list((self.work / "build").glob("assembly-tmp*")), [])

    def test_assembly_rejects_empty_and_unsupported_targets_before_staging(self):
        with self.assertRaisesRegex(release_assembler.AssemblyError, "^no targets to assemble$"):
            release_assembler.assemble_all(self.work, ())
        with self.assertRaises(targets.UnsupportedTargetError):
            release_assembler.assemble_all(self.work, (TRIPLE, "unsupported-target"))
        self.assertFalse((self.work / "dist" / product.RELEASE_DIRNAME).exists())
        self.assertEqual(list((self.work / "build").glob("assembly-tmp*")), [])

    def test_rename_failure_clears_staging_and_leaves_no_release(self):
        final = self.work / "dist" / product.RELEASE_DIRNAME
        error = OSError("fixture rename failed")
        with (
            patch.object(Path, "rename", side_effect=error),
            self.assertRaises(OSError) as raised,
        ):
            release_assembler.assemble_all(self.work, (TRIPLE,))
        self.assertIs(raised.exception, error)
        self.assertFalse(final.exists())
        self.assertEqual(list((self.work / "build").glob("assembly-tmp*")), [])

    def test_rename_refuses_to_replace_a_release_published_during_staging(self):
        final = self.work / "dist" / product.RELEASE_DIRNAME
        existing = final / "existing-checksums.txt"
        rename = Path.rename

        def publish_first(staging: Path, destination: Path):
            self.assertEqual(staging.parent, self.work / "build")
            self.assertTrue(staging.name.startswith("assembly-tmp-"))
            self.assertEqual(destination, final)
            final.mkdir()
            existing.write_bytes(b"existing checksums")
            return rename(staging, destination)

        with (
            patch.object(Path, "rename", autospec=True, side_effect=publish_first),
            self.assertRaisesRegex(
                release_assembler.AssemblyError,
                f"^refusing to overwrite existing release directory: {re.escape(str(final))}$",
            ),
        ):
            release_assembler.assemble_all(self.work, (TRIPLE,))
        self.assertEqual(existing.read_bytes(), b"existing checksums")
        self.assertEqual(list(final.iterdir()), [existing])
        self.assertEqual(list((self.work / "build").iterdir()), [self.work / "build" / TRIPLE])

    def test_refuses_dirty_checkout_and_existing_release(self):
        (self.work / "stray.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(release_assembler.AssemblyError, "^refusing to assemble from a dirty checkout; commit first$"):
            release_assembler.assemble_all(self.work, (TRIPLE,))
        (self.work / "stray.txt").unlink()
        release_assembler.assemble_all(self.work, (TRIPLE,))
        with self.assertRaisesRegex(release_assembler.AssemblyError, "^refusing to overwrite existing release directory:"):
            release_assembler.assemble_all(self.work, (TRIPLE,))


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_action_pins_are_full_shas(self):
        pins = re.findall(r"uses:\s*\S+@(\S+)", self.text)
        self.assertTrue(pins)
        for pin in pins:
            self.assertRegex(pin, r"^[0-9a-f]{40}$")

    def test_dispatch_only_with_preflight_before_builds(self):
        self.assertIn("on:\n  workflow_dispatch:\n", self.text)
        self.assertNotIn("inputs:", self.text)
        self.assertLess(self.text.index("  preflight:"), self.text.index("  controller-test:"))
        self.assertLess(self.text.index("  controller-test:"), self.text.index("  build:"))
        self.assertIn("needs: [preflight, controller-test]", self.text)

    def test_targets_and_release_gate_use_current_contract(self):
        self.assertIn("aarch64-apple-darwin", self.text)
        self.assertIn("x86_64-unknown-linux-musl", self.text)
        self.assertIn("xcode-27", self.text)
        self.assertNotIn("macos-14", self.text)
        self.assertIn("RELEASE_TAG: release-${{ github.sha }}", self.text)
        self.assertIn("python3 build.py assemble", self.text)
        self.assertIn("build.py published-smoke --target", self.text)
        self.assertIn("sha256sum -c SHA256SUMS", self.text)
        self.assertIn(
            '--target "$GITHUB_SHA" --prerelease --verify-tag', self.text
        )
        self.assertIn('--notes-file "$RUNNER_TEMP/release-notes.md"', self.text)
        self.assertNotIn("GH_TOKEN", self.text.split("  release:", 1)[0].split("  build:", 1)[1])

    def test_least_privilege_and_gates(self):
        self.assertIn("permissions: {}", self.text)
        self.assertIn("contents: read", self.text)
        self.assertIn("contents: write", self.text)
        self.assertIn("if-no-files-found: error", self.text)
        self.assertIn("persist-credentials: false", self.text)

    def test_assembly_inputs_travel_through_artifact(self):
        for record in (
            "build-receipt.json",
            "package-record.json",
            "qualify/qualify-record.json",
        ):
            self.assertIn(record, self.text)


class ReproduceDiffTest(unittest.TestCase):
    def test_identical_bytes_have_no_chunks(self):
        data = bytes(range(256)) * 8192
        self.assertEqual(reproduce_runner.differing_chunks(data, data), [])

    def test_locates_differing_chunks(self):
        first = bytes(6 << 20)
        second = bytearray(first)
        second[3 << 20] ^= 1
        second[(5 << 20) - 1] ^= 1
        self.assertEqual(
            reproduce_runner.differing_chunks(bytes(first), bytes(second)),
            [3 << 20, 4 << 20],
        )

    def test_size_change_reported(self):
        self.assertEqual(
            reproduce_runner.differing_chunks(b"abc", b"abcd"), [0, 3]
        )


if __name__ == "__main__":
    unittest.main()
