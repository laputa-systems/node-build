# node-build

`make clean` removes the root build and release outputs and the Ruff cache.
It preserves installed dependencies and unrelated scratch files.

Independent build system for the locked Node.js 26.12.1 source. It produces
relocatable, PIE-hardened installations for `aarch64-apple-darwin`,
`x86_64-unknown-linux-musl`, and `aarch64-unknown-linux-musl`.

The roadmap, [docs/roadmap.md](docs/roadmap.md), holds all current and future work; its Status is the resume point.

## Commands

```text
make fetch|doctor|build|package|verify|repro TARGET=<triple>
make test
make lint
make clean
```

`build` fetches, compiles, and packages one target; `verify` qualifies the archive and checks
its size budgets. The steps are also available directly:

```text
python3 build.py doctor
python3 build.py fetch --target <triple>
python3 build.py build --target <triple>
python3 build.py qualify --target <triple>
python3 build.py package --target <triple>
python3 build.py reproduce --target <triple>
python3 build.py compare-reference --target <triple>
python3 build.py assemble
python3 build.py published-smoke --target <triple>
python3 build.py check-budgets --target <triple>
python3 build.py controller-test
```

`assemble` defaults to all supported triples and refuses dirty checkouts
and unqualified archives. Acquisition (`fetch`) may use the
network; compilation runs from verified cached inputs only.

## Verification

- `make test` calls `make controller-test`. The pinned x86_64 Alpine release environment, with Git for fixture repositories, passed all 74 tests on both runs. Under local x86_64 emulation the runs took 0.81 s and 0.85 s after provisioning.
- `make coverage` runs the controller suite with branch instrumentation across the 21 first-party Python files and writes `.work/coverage/report.json`. Use the ordinary Ubuntu controller environment or a host that satisfies the local lock check.
- The hosted Ubuntu ARM64 test job ran 76 cases and skipped the host lock check in the coverage trial, which requires musl on Linux. The pinned Alpine runs exercise that check.
- `make lint` runs Ruff and ty. It passed in 0.67 s on the first macOS ARM64 run and 0.08 s warm.
- `tests/test_controller.py` checks target selection, configure recipes, toolchain and source locks, input handling, and patch application. The macOS host probe requires the Xcode and SDK versions in `bootstrap.lock.json`.
- `tests/test_release.py` checks assembly, checksums and clean-checkout requirements for the release workflow and `dl` consumer. The workflow checks built archives and published-asset layout.
- `tests/test_product.py` and `tests/test_elf.py` cover Mach-O and ELF identity, relocation, and hardening checks. `make verify` checks the actual artifact. `tests/test_help_footer.py` covers the owned help footer.
- The full controller CLI argument and exit contract has no process-level test in `make test`. `tests/test_compare.py` exercises the result comparison logic. The native runtime comparison workload is described in [Performance](docs/PERFORMANCE.md).
- `make build verify` and `make repro` are separate native artifact checks. The sealed controller checks need neither a complete Node build nor publication.

## Invariants

The controller's only Python dependency is `laputa-buildlib`, pinned in `pyproject.toml`/`uv.lock` for
`uv run` and in `sources.lock.json` for plain `python3`: `buildsys/__init__.py` puts the verified wheel
from `build/cache` on `sys.path` (downloading it once if absent) when `buildlib` is not installed.
No floating tags or unpinned downloads in a reproducible path. Every shipped claim is proven by a
test that fails when the claim is wrong. Worktrees and scratch live under
`.work/`, never `/tmp`. Commits use Conventional Commit format with the area
as scope.

`buildsys/targets.py` owns the supported set, layered on `buildlib.targets`. `buildsys/product.py` owns
archive and metadata naming. `buildsys/recipes.py` owns the per-target
configure recipe and rejects banned flags (`-march=native`, `-ffast-math`,
`--fully-static`, `--enable-thin-lto`). Locks verify bytes before use. Every lock file carries `schema_version` 1; `sources.lock.json` records the upstream inputs, `bootstrap.lock.json` the toolchain `doctor` checks, and `release-budgets.json` the per-target size ceilings.

## Map

- `docs/RELEASE.md` — release workflow, `release-<sha>` tag, asset layout, `dl` hook.
- `docs/DIAGNOSE.md` — assembly fixture reproductions.
- `docs/SECURITY.md` — hardening gates and threat-model limits.
- `docs/REPRODUCE.md` — locked builds, reference revisions, reproduction.
- `docs/COMPATIBILITY.md` — inclusions, deliberate differences, runtime floors.
- `docs/PERFORMANCE.md` — comparison methodology and measured results.
