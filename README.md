# node-build

Lean, relocatable Node.js 26.12.1 distributions: Apple Silicon macOS
(`aarch64-apple-darwin`) and Alpine musl x86_64
(`x86_64-unknown-linux-musl`). Small ICU, no npm/npx, no Corepack.

## Get it

Download a dated prerelease from GitHub (`node-26.12.1+YYYYMMDD`, marked
prerelease).

## Run it

```sh
tar -xzf node-26.12.1+YYYYMMDD-<triple>-install_only_stripped.tar.gz
PATH="$PWD/node/bin:$PATH" node --version
```

The tree relocates to any path, including paths with spaces. macOS 26+
on arm64, or Alpine (musl 1.2.6+) on x86_64. No other runtime dependency.

## What's inside

`node/bin/node`, `node/include/node` headers, `node/lib`, `node/LICENSE`.
V8 JIT, snapshots, CJS/ESM, workers, inspector, N-API addons, and TLS all
work; npm, npx, and Corepack are absent. `en-US` formatting works; apps
needing the full locale set must load data through Node's supported
mechanisms. Full inclusion and platform-floor details live in
`docs/COMPATIBILITY.md`.

## Releases

Qualified archives only: native build plus loopback smoke suite, manifest
validation, clean published-byte smoke, then a prerelease against the
recorded source revision. The pipeline is defined in
`docs/RELEASE.md`.
