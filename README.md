# node-build

Lean, PIE-hardened, relocatable Node.js distributions for Apple Silicon,
assembled from locked upstream sources.

## Product contract

- Node.js 26.12.1, `aarch64-apple-darwin`, macOS 26+ only.
- One PIE `MH_EXECUTE` binary, ad-hoc signed, exact `LC_BUILD_VERSION` floor 26.0.
- Small ICU: working `Intl` for the bundled locales, no full-ICU data.
- Node's supported crypto backend (OpenSSL vendored in the locked source).
- No npm, no npx, no Corepack in the default archive.
- V8 JIT, snapshots, CJS/ESM, workers, inspector, N-API addon loading, and
  shipped headers all work; see `docs/COMPATIBILITY.md` for the exact list.
- System-only linkage: CoreFoundation, Security, libc++, libSystem.

## Quick start

```sh
python3 build.py doctor
python3 build.py fetch --target aarch64-apple-darwin
python3 build.py build --target aarch64-apple-darwin
python3 build.py package --target aarch64-apple-darwin
python3 build.py qualify --target aarch64-apple-darwin
```

`qualify` runs the full gate and loopback smoke suite against the final
archive bytes and writes `build/<triple>/qualify/qualify-record.json`.

## Installation

```sh
tar -xzf node-26.12.1-aarch64-apple-darwin-r1.tar.gz
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

macOS 26+ on arm64. No other runtime dependency.

## Repository conventions

`buildsys/targets.py` owns the supported set; `buildsys/product.py` owns
archive and metadata naming; `buildsys/recipes.py` owns the configure recipe
and rejects banned flags. Locks verify bytes before use. `buildsys/macho.py`
adapts the `python-build` Mach-O parser (see `docs/REPRODUCE.md` for the
exact revision). Every shipped claim has a failing-when-wrong test.
