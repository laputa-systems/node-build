# node-build

Lean, PIE-hardened, relocatable Node.js distributions, assembled from locked
upstream sources: Apple Silicon (`aarch64-apple-darwin`) and Alpine musl
x86_64 (`x86_64-unknown-linux-musl`).

## Product contract

- Node.js 26.12.1, small ICU, no npm/npx, no Corepack in the default archive.
- macOS: arm64 only, macOS 26+, one PIE `MH_EXECUTE` binary, ad-hoc signed,
  exact `LC_BUILD_VERSION` floor 26.0.
- Linux: x86_64 musl only (Alpine), one PIE `ET_DYN` binary, musl loader
  `/lib/ld-musl-x86_64.so.1`, RELRO + `BIND_NOW` + non-executable stack.
- Node's supported crypto backend (OpenSSL vendored in the locked source).
- V8 JIT, snapshots, CJS/ESM, workers, inspector, N-API addon loading, and
  shipped headers all work; see `docs/COMPATIBILITY.md` for the exact list.
- System-only linkage: CoreFoundation, Security, libc++, libSystem on macOS;
  musl, libstdc++, libgcc_s, libatomic on Linux.

## Quick start

```sh
python3 build.py doctor --target <triple>
python3 build.py fetch --target <triple>
python3 build.py build --target <triple>
python3 build.py package --target <triple>
python3 build.py qualify --target <triple>
```

`<triple>` is `aarch64-apple-darwin` on Apple Silicon or
`x86_64-unknown-linux-musl` on Alpine x86_64.

`qualify` runs the full gate and loopback smoke suite against the final
archive bytes and writes `build/<triple>/qualify/qualify-record.json`.

## Installation

```sh
tar -xzf node-26.12.1-<triple>-r1.tar.gz
./node/bin/node --version
```

The tree relocates to any path, including paths with spaces.

## Releases

Dated prereleases (`node-26.12.1+YYYYMMDD`, `--prerelease`) are assembled
from qualified archives only: controller tests, native build + qualify,
manifest validation, clean published-byte smoke, then `gh release create`
against the recorded source revision. Assembly refuses dirty checkouts,
tag collisions, and unqualified archives. See `docs/REPRODUCE.md`.

## Runtime requirements

macOS 26+ on arm64, or Alpine (musl 1.2.6+) on x86_64. No other runtime
dependency.

## Repository conventions

`buildsys/targets.py` owns the supported set; `buildsys/product.py` owns
archive and metadata naming; `buildsys/recipes.py` owns the per-target
configure recipe and rejects banned flags. Locks verify bytes before use.
`buildsys/macho.py` adapts the `python-build` Mach-O parser (see
`docs/REPRODUCE.md` for the exact revision); `buildsys/elf.py` is the
native ELF equivalent written for this repo. Every shipped claim has a
failing-when-wrong test.
