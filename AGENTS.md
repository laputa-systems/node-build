# node-build

Independent build system for the locked Node.js 26.12.1 source. It produces a
relocatable, PIE-hardened `aarch64-apple-darwin` installation: lean small-ICU
default, working TLS/crypto, no npm/npx. Linux targets are deferred, never
partially implemented.

## Product targets

| Triple | Platform/compiler | Baseline and deployment |
| --- | --- | --- |
| `aarch64-apple-darwin` | Native Apple Silicon macOS; Xcode Apple clang | `-mcpu=apple-m1`; deployment target 26.0 (macOS 26+ only) |

`buildsys/targets.py` owns the supported set. Linux triples fail closed as
deferred. `buildsys/product.py` is the single source of truth for archive and
metadata naming. `buildsys/recipes.py` owns the configure recipe and rejects
banned flags (`-march=native`, `-ffast-math`, `--fully-static`,
`--enable-thin-lto`).

## Commands

```text
python3 build.py doctor
python3 build.py fetch --target aarch64-apple-darwin
python3 build.py build --target aarch64-apple-darwin
python3 build.py qualify --target aarch64-apple-darwin
python3 build.py package --target aarch64-apple-darwin
python3 build.py reproduce --target aarch64-apple-darwin
python3 build.py compare-reference --target aarch64-apple-darwin
python3 build.py controller-test
```

`doctor` and `fetch` verify the host toolchain and pinned sources.
Acquisition (`fetch`) may use the network; compilation runs from verified
cached inputs only. `build`, `qualify`, `package`, `reproduce`, and
`compare-reference` fail closed until their milestone lands them.

## Inputs and build records

`sources.lock.json` pins source and reference inputs with URL, version,
SHA-256, size, role, license, and purpose. Reference-only entries are never
build inputs. `bootstrap.lock.json` pins the Xcode/SDK/clang identity, host
requirements, CPU baseline, and deployment target. `buildsys/inputs.py`
verifies downloaded bytes against the lock before use and rejects archives
that escape the destination or contain links.

## Conventions

No third-party Python dependencies in the controller. No floating tags or
unpinned downloads in a reproducible path. Every shipped claim is proven by a
test that fails when the claim is wrong. Worktrees and scratch live under
`.work/`, never `/tmp`. Commits use Conventional Commit format with the area
as scope. Do not push unless asked.
