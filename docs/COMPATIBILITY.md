# Compatibility

## Included and working (proven by the loopback smoke suite)

V8 JIT and optimizing compilers; V8 snapshots; CJS and ESM; `node:test`;
workers; child processes; streams; filesystem and async I/O; DNS/TCP
loopback; HTTP/HTTPS/HTTP2 clients and servers; TLS with configured-trust
acceptance and untrusted-certificate rejection; WebCrypto and `node:crypto`;
zlib and brotli; `fetch`; `Intl` for the bundled small-ICU locales;
inspector over loopback; N-API addons compiled against the shipped headers;
built-in SQLite.

## Deliberate differences from upstream defaults

- **Small ICU** (`--with-intl=small-icu`; upstream default is full-icu).
  `en-US` formatting and weekday names verified; applications needing the
  full locale set must load data through Node's supported mechanisms.
- **No npm/npx/Corepack** (`--without-npm`). Use bun, pnpm, or another
  external package manager.
- **Deployment floor 26.0** (upstream supports 13.5+). Older macOS versions
  are unsupported and untested, never partially claimed.

## Runtime requirements

macOS 26+ on arm64. The macOS binary links only CoreFoundation, Security,
libc++, and libSystem. Alpine (musl 1.2.6+) on x86_64. The Linux binary is
a musl PIE executable linking only musl, libstdc++, libgcc_s, and libatomic.

## Unsupported

Intel macOS, Linux arm64, macOS below 26, glibc, static
`--fully-static` distributions, and any OpenSSL replacement backend.
