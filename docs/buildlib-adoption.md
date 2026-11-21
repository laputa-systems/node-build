# Buildlib adoption

node-build already depends on `laputa-buildlib` for lock reading, verified downloads, release
assets, hashing, and ELF/Mach-O inspection. This record covers the BLD-2 pilot: the audit of
remaining local reimplementations, the vendored interpreter bootstrap, the code that changed, and
the proof the plan's per-repository items require. Base revision:
`b0d5061bee5cff947330e1a93d5ee8cb33e4aabd`; this record describes the lane at
`48c150a8b2e8518e84cf2a2247143fc781e124b2`.

## 1. Bound the change

Entrypoints are unchanged: `make build|verify|package|repro|fetch|doctor|test|lint`, `build.py`
subcommands, compiler flags, and the release/archive formats. The controller now runs through the
vendored `bootstrap/buildlib-run`, and `buildsys/__init__.py` stopped downloading its own copy of
the wheel.

| Local implementation (base) | What it did | Replaced with |
| --- | --- | --- |
| `buildsys/__init__.py` `_wheel_pin`, `_verified`, `_pinned_wheel`, `_ensure_buildlib` | Parsed the `laputa-buildlib` entry out of `sources.lock.json`, hashed the wheel, downloaded it with `urllib` into `build/cache`, and inserted it on `sys.path` when `buildlib` was absent. | Vendored `bootstrap/buildlib-run` + `bootstrap/python.lock`, which buildlib owns: it pins interpreter and wheel, verifies every archive by size and SHA-256, and runs the wheel from `PYTHONPATH`. `buildsys/__init__.py` now fails loudly if the wheel is absent (no second downloader). |
| `buildsys/elf_policy.py` `EXPECTED_INTERP_X86_64` | Hard-coded `/lib/ld-musl-x86_64.so.1`, a value buildlib already maps per triple. | Derived from `buildlib.targets.target_for_triple(...).musl_loader`. |

Already on buildlib before this slice (no change, kept): `locks.load_sources`/`load_budgets`/
`load_bootstrap`/`fetch_input`/`verify_file` (`buildsys/node.py`, `buildsys/budgets.py`,
`buildsys/bootstrap.py`), `hashing.sha256_file` (all records), `release.create_archive`/
`archive_name`/`manifest_name`/`build_manifest`/`write_manifest`/`write_sha256sums`
(`buildsys/package.py`, `buildsys/product.py`, `buildsys/release.py`), `elf.*`/`macho.*`
(`buildsys/validate_product.py`, `buildsys/package.py`, `buildsys/reproduce.py`), and
`targets.*` (`buildsys/targets.py`).

### Interpreter path a fresh host takes (base)

The base README and docs told a newcomer to run `python3 build.py ...`. `buildsys/__init__.py`
then tried to import `buildlib`; if it was absent it fetched the wheel with `urllib` and inserted
it on `sys.path`. That path depends on the distribution providing `python3` at all: Ubuntu 24.04
ships none, and the project declares `requires-python = ">=3.15"` in both `pyproject.toml` and
buildlib's own metadata. A 3.12 interpreter happened to run the base suite here, but it is below
the declared floor and is not a supported controller host. The adoption path removes the
host-Python dependency: the shim provisions a pinned CPython 3.15 and runs the wheel on it, so a
host with no Python, no `uv`, and no `pip` still runs the documented gates.

### Audit of remaining local code (not replaced)

These have no buildlib equivalent and stay local; each was checked against buildlib 0.2.0:

- `buildsys/inputs.py` `safe_extract`: `tar.extractall(filter="data")` plus an explicit
  escape/link pre-check. buildlib has no extraction helper. Kept, with its escape/symlink tests.
- `buildsys/inputs.py` `render_json`: sorted-key, indented record writer. buildlib writes only
  manifests and checksums; it exposes no general JSON record writer, so a rewrite would not
  reduce a shared operation.
- `buildsys/budgets.py` `archive_payload_bytes`: counts compressed bytes and payload. The
  structural `locks.load_budgets` is buildlib's; the ceiling comparison, byte-limit types, and
  measured values are consumer policy and stay local.
- `buildsys/node.py` `recipe_fingerprint`: hashes the recipe dict. Not a file digest.
- `buildsys/smoke.py`, `buildsys/bench.py`, `buildsys/benchmarks.py`, `buildsys/comparison.py`:
  runtime probes and the tiered benchmark harness. Product-specific, no shared primitive.
- `buildsys/relocate.py` `scan_forbidden_refs`: substring scan of shipped bytes for stage/source
  prefixes. Policy, not ELF/Mach-O structure.

Consumer policy that stays local and validated: source-lock extension fields (the buildlib entry
is still pinned in `sources.lock.json` and cross-checked against the bootstrap lock), budget
values and their byte ceilings, `ALLOWED_NEEDED` dynamic dependencies, the recipe's required and
banned flags, product manifest fields (`archive`, `sha256`, `size`, `source`, `toolchain`,
`recipe`, `hardening`, `qualification`), and every release-layout and cleanup check. buildlib's
structural readers do not prove any of these.

## 2. Pin and exercise the installed bytes

- `sources.lock.json` pins `laputa-buildlib` 0.2.0 at
  `sha256:aaee620f0478544b1d32075b44de48e69bbcbd8b974d5f599d037494d59f4b4a`, size 25193.
- `pyproject.toml` pins `laputa-buildlib==0.2.0`; `uv.lock` records the same wheel URL and hash.
- `bootstrap/python.lock` (vendored) pins the same wheel URL and SHA-256.

Import provenance is printed by the proof below: the ordinary controller imports `buildlib` from
`…/laputa-buildlib/<wheel-sha>/buildlib.whl/buildlib/__init__.py`, not from a source tree.

### Vendored bootstrap provenance

| File | Source | Digest (SHA-256) | Local differences |
| --- | --- | --- | --- |
| `bootstrap/buildlib-run` | buildlib `30ad4a0a8b697031a008b1de3b5359fc5cf6f2fe` (`buildlib/bootstrap/buildlib-run`) | `e7f957ca6af0b151d25a9ff5bedb5deca0bfc86ba05ff3225a5405d56fa95957` | none |
| `bootstrap/python.lock` | buildlib `30ad4a0…` (`buildlib/bootstrap/python.lock`) | `cab50541ce8b2c2a6a41829f26aac19344532d239535f4d6795d80d5af933832` | none |

The files are byte-identical to buildlib 0.2.0 (`git rev-parse HEAD` = `30ad4a0`, tag `0.2.0`).
Repin both together: the wheel line must stay equal to the `sources.lock.json` entry, which
`tests/test_controller.py::test_vendored_bootstrap_pins_the_same_wheel_as_the_source_lock`
enforces. The shim's trust paths are unchanged from buildlib: python-build archives verify by
size and SHA-256 before extraction; the uv fallback's managed Python is verified by uv's upstream
metadata (a distinct trust path, recorded here rather than claimed equivalent).

## 3. Boundary tests

- `tests/test_bootstrap_shim.py` (new): runs the vendored shim against an offline fixture server.
  It proves a verified archive and wheel execute the cached Python, and that an injected wrong
  wheel digest, wrong archive size, and truncated download each fail clearly with the pinned
  interpreter never running. This replaces the three tests of the deleted local downloader.
- `tests/test_controller.py::test_buildsys_refuses_to_import_without_the_pinned_wheel`: the
  ordinary controller import fails loudly (exit 3) and names the shim when the wheel is absent,
  rather than silently downloading.
- `tests/test_controller.py::test_vendored_bootstrap_pins_the_same_wheel_as_the_source_lock`:
  package, source-lock, and bootstrap-shim identities agree.

Preserved stronger checks (unchanged): archive admission (refuses overwrite), safe extraction
(escape and symlink), cache integrity (source marker binds the extracted tree to the pinned
archive), release-layout membership/modes/symlinks, complete `SHA256SUMS`, assembly concurrency,
and the product hardening gate. No test was weakened or skipped.

## 4. Compare outcomes

No release or archive format changed. Archive bytes, manifest fields, checksums, and the
`.tar.xz` writer are unchanged (still `buildlib.release.create_archive` with the same prefix and
`SOURCE_DATE_EPOCH`). Only the interpreter provisioning and the wheel's import path changed; the
controller's observable output and error contracts are unchanged.

## 5. Prove the environment

macOS arm64 (native): `make lint` and `make test` pass except
`tests.test_controller.BootstrapTest.test_lock_matches_host`, which fails identically on the base
commit because the host Xcode is 27.2 and the lock records 27.1 (see the base/lane comparison in
the final proof). Cold capsules from a clone of the lane commit:

- `ubuntu:24.04` arm64 (native): uv fallback branch selected (musl 1.2.4 is below 1.2.5).
- `ubuntu:26.04` arm64 (native) with distro `musl`: python-build branch selected (musl 1.2.5).

Both run `scripts/setup-dev` then `make lint test`, with per-step exit codes and an empty
`git status --porcelain`.

## 6. Benefit and cost

- Duplicate code removed: `buildsys/__init__.py` lost its own lock-pin parser, wheel hasher,
  downloader, and `sys.path` bootstrap (~75 lines), replaced by four lines that refuse a missing
  wheel. `buildsys/elf_policy.py` derives the interpreter from the already-imported target map.
- Shared operations actually used after the slice: verified acquisition and wheel pinning
  (`bootstrap`), plus the pre-existing lock/hashing/release/target/ELF/Mach-O calls.
- Correctness gain: a fresh host no longer needs a distribution Python new enough to import the
  controllers; every interpreter and the wheel are SHA-256 pinned. The interpreter bootstrap and
  its trust paths are shared with other buildlib consumers instead of a second, weaker downloader.
- Cold cost (container, native arm64, cold cache, from a clone of the lane commit):

  | Capsule | interpreter branch | setup | lint | test | cold total |
  | --- | --- | --- | --- | --- | --- |
  | `ubuntu:24.04` | uv fallback (musl 1.2.4) | 9s | <1s | 4s | 29s |
  | `ubuntu:26.04` + musl | python-build (musl 1.2.5) | 8s | <1s | 5s | 30s |

  Both ran 182 tests with 1 skipped (`test_lock_matches_host` skips on a non-musl
  Linux host; it is the macOS Xcode check that fails here) and ended with an empty
  `git status --porcelain`. The times are capsule wall-clock for setup, lint, and
  test only; they are operational cost, not a performance benchmark.
- Warm cost: `sh bootstrap/buildlib-run -- -c pass` is ~0.13s once the cache is
  populated (it re-hashes the pinned wheel, no download); `make lint` is ~3.4s
  with the existing `.venv`; `build.py controller-test` is unchanged in shape.

## Repin procedure

1. Change `laputa-buildlib==X.Y.Z` in `pyproject.toml`, run `uv lock`.
2. Update the `laputa-buildlib` entry in `sources.lock.json` (URL, SHA-256, size).
3. Re-vendor `bootstrap/buildlib-run` and `bootstrap/python.lock` from the new buildlib tag and
   update the digests in the table above. The wheel line must match step 2.
4. `make setup && make lint test`, then the cold capsules.
