# Reproduce the build

## Locked build

```sh
python3 build.py doctor --target aarch64-apple-darwin
python3 build.py fetch --target aarch64-apple-darwin
python3 build.py build --target aarch64-apple-darwin
```

`doctor` refuses a toolchain that does not match `bootstrap.lock.json`.
`fetch` verifies downloaded bytes against `sources.lock.json` before caching.
Compilation uses only verified cached inputs; no network.

## Reference revisions consulted

- Design conventions: `../python-build` at `cde895aee64148cbee11adf5af57c2fcb1d04941`
  (`main`, 2026-10-25).
- Hardening machinery (`buildsys/macho.py` parser, signature checks,
  dependency resolution): `../python-build` at
  `5227de3f57d0f93b49b09c3559c4a2b01e9df5e`
  (`fix(hardening): enforce final binary protections`, 2026-10-25).
  Install-name edit helpers were deliberately not carried over: this product
  ships no private dylibs.

## Vendored-source patch

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

Builds twice from clean trees and compares raw and normalized (UUID and
code-signature ranges zeroed) bytes. The verdict distinguishes bit-for-bit
reproducibility, content identity outside signing metadata, and genuine
divergence. Writes `build/<triple>/reproduce-record.json`. A mismatch is
reported, never hidden.
