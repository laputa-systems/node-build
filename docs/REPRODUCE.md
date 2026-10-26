# Reproduce the build

## Locked build (macOS)

```sh
python3 build.py doctor --target aarch64-apple-darwin
python3 build.py fetch --target aarch64-apple-darwin
python3 build.py build --target aarch64-apple-darwin
```

## Locked build (Linux)

```sh
python3 build.py doctor --target x86_64-unknown-linux-musl
python3 build.py fetch --target x86_64-unknown-linux-musl
python3 build.py build --target x86_64-unknown-linux-musl
```

`doctor` refuses a toolchain that does not match `bootstrap.lock.json`.
`fetch` verifies downloaded bytes against `sources.lock.json` before caching.
Compilation uses only verified cached inputs; no network.

## Reference revisions consulted

- Design conventions: `../python-build` at `cde895aee64148cbee11adf5af57c2fcb1d04941`
  (`main`, 2026-10-25).
- Hardening machinery: `buildsys/macho.py` parser, signature checks,
  dependency resolution follow `../python-build` at
  `5227de3f57d0f93b49b09c3559c4a2b01e9df5e`
  (`fix(hardening): enforce final binary protections`, 2026-10-25).
  Install-name edit helpers were deliberately not carried over: this product
  ships no private dylibs. `buildsys/elf.py` is original to this repo — a
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
python3 build.py reproduce --target aarch64-apple-darwin
```

Builds twice from clean trees and compares raw and normalized bytes (macOS:
UUID and code-signature ranges zeroed; Linux: `NT_GNU_BUILD_ID` zeroed).
The verdict covers the `node` binary: two clean Linux rebuilds linked
bit-for-bit identical binaries (129,786,392 bytes, 2026-10-26). Tarball
bytes are not covered — header-file mtimes shift the archive by tens of
bytes between reinstalls — so a rebuilt archive gets a fresh SHA-256 and
must re-pass package + qualify. The verdict distinguishes bit-for-bit
reproducibility, content identity outside signing metadata, and genuine
divergence. Writes `build/<triple>/reproduce-record.json`. A mismatch is
reported, never hidden.
