# node-build

Independent build system for the locked Node.js 26.12.1 source. It produces
relocatable, PIE-hardened installations for `aarch64-apple-darwin` and
`x86_64-unknown-linux-musl`. Linux arm64 stays parked.

## Commands

```text
make fetch|doctor|build|package|verify|repro TARGET=<triple>
make controller-test
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

## Invariants

The controller's only Python dependency is `laputa-buildlib`, pinned in `pyproject.toml`/`uv.lock` for
`uv run` and in `sources.lock.json` for plain `python3`: `buildsys/__init__.py` puts the verified wheel
from `build/cache` on `sys.path` (downloading it once if absent) when `buildlib` is not installed.
No floating tags or unpinned downloads in a reproducible path. Every shipped claim is proven by a
test that fails when the claim is wrong. Worktrees and scratch live under
`.work/`, never `/tmp`. Commits use Conventional Commit format with the area
as scope. Do not push unless asked.

`buildsys/targets.py` owns the supported set, layered on `buildlib.targets`. `buildsys/product.py` owns
archive and metadata naming. `buildsys/recipes.py` owns the per-target
configure recipe and rejects banned flags (`-march=native`, `-ffast-math`,
`--fully-static`, `--enable-thin-lto`). Locks verify bytes before use. Every lock file carries `schema_version` 1; `sources.lock.json` records the upstream inputs, `bootstrap.lock.json` the toolchain `doctor` checks, and `release-budgets.json` the per-target size ceilings.

## Map

- `docs/RELEASE.md` — release workflow, `release-<sha>` tag, asset layout, `dl` hook.
- `docs/SECURITY.md` — hardening gates and threat-model limits.
- `docs/REPRODUCE.md` — locked builds, reference revisions, reproduction.
- `docs/COMPATIBILITY.md` — inclusions, deliberate differences, runtime floors.
- `docs/PERFORMANCE.md` — comparison methodology and measured results.
