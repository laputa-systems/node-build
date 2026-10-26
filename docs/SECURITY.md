# Security policy

## Hardening enforced by the release gate (macOS)

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

## Hardening enforced by the release gate (Linux)

Every shipped ELF image is scanned from its own ELF header, program
headers, and dynamic section (`buildsys/elf.py`, no external tools):

- Exactly one 64-bit little-endian x86-64 image; 32-bit files rejected.
- Every executable is `ET_DYN` (PIE); `ET_EXEC` non-PIE rejected.
- Interpreter is exactly `/lib/ld-musl-x86_64.so.1`.
- Every `DT_NEEDED` entry is an allowlisted system library (musl,
  libstdc++, libgcc_s, libatomic, and their stable companions); absolute
  paths and `..` escapes rejected. No `DT_RPATH`/`DT_RUNPATH` may be present.
- `PT_GNU_RELRO` present, `DF_BIND_NOW`/`DF_1_NOW` set, `PT_GNU_STACK`
  non-executable.
- `bin/node` must be present; `bin/npm`, `bin/npx`, and `lib/node_modules`
  must be absent.
- No stagedir path leaks in the shipped bytes.

The per-target `hardening-report.json` records the image, its interpreter,
dependencies, and each check. Negative fixtures (non-PIE, wrong arch, bad
interpreter, bad dependency, RPATH present, missing RELRO/BIND_NOW,
executable stack) prove the validator fails when it should.

## Threat-model limits

- Signatures are ad-hoc on macOS: they prove integrity from packaging to
  install, not Apple notarization or a Developer ID chain. No
  hardened-runtime or notarization claim is made. The Linux binary carries
  no signature; its integrity rests on the same sealed-receipt chain below.
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
recipe (including the macOS-only `common.gypi` floor patch), and archive
digests.
