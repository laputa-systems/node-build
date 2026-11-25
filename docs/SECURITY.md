# Security policy

## Hardening enforced by the release gate (macOS)

Every shipped Mach-O image is scanned from its own headers and load commands
(`buildlib.macho`, categories in `buildsys/validate_product.py`):

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
dependencies, and each check. Negative fixtures (non-PIE, wrong arch,
malformed headers, bad rpaths) prove the validator fails when it should.

## Hardening enforced by the release gate (Linux)

Every shipped ELF image is scanned from its own ELF header, program
headers, and dynamic section (`buildlib.elf`, no external tools):

- Exactly one 64-bit little-endian image of the target architecture
  (x86-64 or AArch64); 32-bit files and wrong-arch images rejected.
- Every executable is `ET_DYN` (PIE); `ET_EXEC` non-PIE rejected.
- Interpreter is exactly the target's musl loader
  (`/lib/ld-musl-x86_64.so.1` or `/lib/ld-musl-aarch64.so.1`).
- Every `DT_NEEDED` entry is in the allowlist
  (`ALLOWED_NEEDED` in `buildsys/elf_policy.py`); absolute paths and `..`
  escapes rejected. `bin/node` may need only the matching
  `libc.musl-<arch>.so.1`. No `DT_RPATH`/`DT_RUNPATH` may be present.
- `buildlib.elf.hardening_violations` is empty: `PT_GNU_RELRO` present,
  `DF_BIND_NOW`/`DF_1_NOW` set, `PT_GNU_STACK` non-executable, and no
  writable-and-executable `PT_LOAD` segment.
- Same presence/absence and path-leak rules as macOS above.

Negative fixtures (non-PIE, wrong arch, bad interpreter, bad dependency,
RPATH present, missing RELRO/BIND_NOW, executable stack) prove the
validator fails when it should.

## Threat-model limits

- Signatures are ad-hoc on macOS: they prove integrity from packaging to
  install, not Apple notarization or a Developer ID chain. No
  hardened-runtime or notarization claim is made. The Linux binary carries
  no signature; checksums detect byte changes, but do not authenticate an artifact.
- The OpenSSL `__cstring` config block embeds an inert absolute build path
  (literal `$(BUILDTYPE)`, never resolvable). The official nodejs.org binary
  ships the identical pattern. It is reported as informational, not gated:
  it cannot influence loading, and all load paths are still gated.
- Assembly checks the build receipt against the checkout revision and source lock,
  and checks the package and qualification records against the archive. The
  reproducibility command measures bit equality in two rebuilds.
- Network access exists only in acquisition (`fetch`) and the interpreter
  bootstrap (`bootstrap/buildlib-run` fetching its pinned CPython/uv archives and
  the `laputa-buildlib` wheel, each verified by size and SHA-256 before use);
  compilation runs from verified cached inputs.
