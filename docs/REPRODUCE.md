# Reproduce the build

`bootstrap.lock.json` pins the build toolchain: the macOS sections pin the Apple toolchain,
the `linux_*` sections pin the Alpine musl toolchain, and `doctor` verifies the section
matching the requested target family. `sources.lock.json` pins every upstream input by
SHA-256 and size; downloaded bytes are verified before use.

Run the locked chain for either triple (`doctor` refuses a toolchain that
does not match `bootstrap.lock.json`; `fetch` verifies downloaded bytes
against `sources.lock.json` before caching; compilation uses only verified
cached inputs, no network):

```sh
python3 build.py doctor --target <triple>
python3 build.py fetch --target <triple>
python3 build.py build --target <triple>
```

## Reference revisions consulted

- Design conventions: `../python-build` at `cde895aee64148cbee11adf5ad57c2fcb1d04941`
  (`main`, 2026-10-25).
- Hardening machinery: the Mach-O parser and signature checks (now
  `buildlib.macho`) and the dependency resolution in `buildsys/macho_paths.py` follow `../python-build` at
  `5227de3f57d0f93b49b09c3559c4a2b01e9df5e`
  (`fix(hardening): enforce final binary protections`, 2026-10-25).
  Install-name edit helpers were deliberately not carried over: this product
  ships no private dylibs. The ELF parser (now `buildlib.elf`) is original to this repo — a
  dependency-free ELF64 parser implementing the same gate categories
  (PIE, arch, interpreter/dependency closure, RELRO, BIND_NOW, NX) for
  musl targets.

## Vendored-source patch (macOS only)

Node's `configure` ignores `MACOSX_DEPLOYMENT_TARGET`; the floor is
hardcoded in `common.gypi`. One exact-match patch is applied at extraction
(see `PRODUCT_PATCHES` in `buildsys/node.py`, patch level recorded in the
build receipt):

- `common.gypi`: `MACOSX_DEPLOYMENT_TARGET` `13.5` → `26.0`.

Application is idempotent, fails loudly on unexpected content, and forces
reconfiguration through the recipe fingerprint.

## Independent reproduction

```sh
python3 build.py reproduce --target <triple>
```

Builds twice from clean trees and compares raw and normalized bytes (macOS:
UUID and code-signature ranges zeroed; Linux: `NT_GNU_BUILD_ID` zeroed).
The verdict covers the `node` binary: two clean Linux rebuilds linked
bit-for-bit identical binaries (129,786,392 bytes, 2026-10-26). Archives are written by `buildlib.release.create_archive` with sorted
entries, root ownership, normalized modes, and `SOURCE_DATE_EPOCH` (0 when
unset) as every mtime, so identical install trees give identical archive
bytes; the verdict still covers only the `node` binary, and a rebuilt
archive must re-pass package + qualify. The verdict distinguishes bit-for-bit
reproducibility, content identity outside signing metadata, and genuine
divergence. Writes `build/<triple>/reproduce-record.json`. A mismatch is
reported, never hidden.
