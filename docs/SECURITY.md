# Security policy

## Hardening enforced by the release gate

Every shipped Mach-O image is scanned from its own headers and load commands:

- Exactly one arm64 slice; fat/universal images rejected.
- Every executable is `MH_EXECUTE` with `MH_PIE`.
- Exactly one version command; platform is macOS; `minos` equals the locked
  deployment target (26.0), not merely newer-or-equal.
- No `LC_RPATH`; every `LC_LOAD_DYLIB` resolves to `/usr/lib/` or
  `/System/Library/`; `@rpath`/`@loader_path`/`@executable_path` entries
  resolve inside the installed tree or the image is rejected.
- Every image passes `codesign --verify --strict`.
- `bin/node` must be present; `bin/npm`, `bin/npx`, and `lib/node_modules`
  must be absent.
- No stagedir path leaks in the shipped bytes.

The per-target `hardening-report.json` records every image, its version,
dependencies, and each check. The gate refuses a missing or failed check.
Negative fixtures (non-PIE, wrong arch, malformed headers, bad rpaths) prove
the validator fails when it should.

## Threat-model limits

- Signatures are ad-hoc: they prove integrity from packaging to install, not
  Apple notarization or a Developer ID chain. No hardened-runtime or
  notarization claim is made.
- The OpenSSL `__cstring` config block embeds an inert absolute build path
  (literal `$(BUILDTYPE)`, never resolvable). The official nodejs.org binary
  ships the identical pattern. It is reported as informational, not gated:
  it cannot influence loading, and all load paths are still gated.
- Trust anchors are the locked source hashes, the verified toolchain, and
  the sealed build receipt — not reproducible-bit-equality, which is
  measured and reported but not claimed.
- Network access exists only in acquisition (`fetch`); compilation runs
  from verified cached inputs.

## Provenance

`sources.lock.json` and `bootstrap.lock.json` pin every input with URL,
version, SHA-256, and size. The build receipt binds source, toolchain,
recipe (including the `common.gypi` floor patch), and archive digests.
