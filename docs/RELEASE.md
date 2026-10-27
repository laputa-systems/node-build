# Release pipeline

Dated prereleases (`node-26.12.1+YYYYMMDD`, `--prerelease`) assembled from
qualified archives only. The workflow (`.github/workflows/build.yml`) is
manually dispatched with an optional `release_tag` (empty defaults to
today's UTC date) and mirrors the `python-build` prerelease shape:
`prepare` resolves and validates the tag against `GITHUB_SHA`, runs the
controller tests, then per-target build-plus-qualify jobs, `assemble`,
per-target published-byte smoke, and `publish`.

## Jobs

`prepare` (ubuntu-24.04) checks out with full history, pins every action
to a full commit SHA, validates the tag
(`.github/scripts/resolve_release.py`: YYYYMMDD shape, checkout matches
`GITHUB_SHA`, existing tag must point at the same commit), and runs
`controller-test`. `build-macos` (xcode-27) runs doctor, fetch, build,
package, qualify, and budgets for `aarch64-apple-darwin`. `build-linux`
(ubuntu-24.04) runs the same chain for `x86_64-unknown-linux-musl` inside
a digest-pinned Alpine container, since the musl toolchain cannot run on
the glibc host; `doctor` fails closed if the container toolchain drifts
from `bootstrap.lock.json`. Both build jobs upload the `dist/<triple>`
archive plus the build receipt, package record, and qualify record, and
preserve logs plus qualification evidence when they fail.

`assemble` downloads both triples, runs `build.py assemble` (all
supported triples by default, `--target` accepts a comma-separated
subset), and uploads `dist/<tag>/`. Assembly re-validates every triple:
archive present, qualify record matches archive bytes, all product, smoke,
and relocation checks green, then writes per-target artifact manifests
plus `assembly.json`, `download-metadata.json`, `smoke-metadata.json`
(each keyed by triple), and `SHA256SUMS`. It refuses dirty checkouts, tag
collisions, and existing release directories.

`smoke-macos` and `smoke-linux` verify `SHA256SUMS`, then run
`build.py published-smoke` for their triple against the exact assembled
bytes (Linux inside the same Alpine container). `publish` re-verifies the
hashes and creates the prerelease against the recorded source revision:

```sh
gh release create "$RELEASE_TAG" --target "$GITHUB_SHA" --prerelease \
  --title "node-$NODE_VERSION+$RELEASE_TAG" \
  --notes-file release-notes.md "dist/$RELEASE_TAG"/*
```

## `dl` hook

`~/usr/dl node-build` installs the latest prerelease for the host triple
(`aarch64-apple-darwin` on Apple Silicon, `x86_64-unknown-linux-musl` on
Linux x86_64) into `$XDG_DATA_HOME/node-build/<tag>`, verifying
`SHA256SUMS` before extraction and symlinking the result. The download and
smoke metadata in the release carry the per-triple archive hashes.
