# Release pipeline

Prereleases tagged `release-<commit sha>`, assembled from qualified archives only. The
workflow `.github/workflows/release.yml` runs only on `workflow_dispatch`. It follows the
build-repository contract in `stuff/docs/build-repos.md`.

## Assets

Each supported triple produces:

- `node-<version>-<triple>.tar.xz`, extracting to `node/`.
- `node-<version>-<triple>.manifest.json` with `schema_version` (1), `product`, `version`,
  `target`, `source_revision`, `sources_lock_sha256`, the archive name, size and SHA-256,
  and the build receipt (source, toolchain, recipe), hardening report, and qualification
  record.

`SHA256SUMS` covers every other asset, sorted by file name. Local builds write the archive to
`dist/<triple>/` with the same name; `build.py assemble` copies the archives, writes the
manifests and `SHA256SUMS` into `dist/release/`, and refuses dirty checkouts, unqualified
archives, and an existing `dist/release/`.

## Jobs

`preflight` rejects any ref other than the default branch. `controller-test` runs
`make controller-test`. `build` runs `make doctor build verify TARGET=<triple>` per target:
`aarch64-apple-darwin` on the `xcode-27` runner, and `x86_64-unknown-linux-musl` in a
digest-pinned Alpine musl container (the digest and `apk` pins follow the fleet
`musl-toolchain.toml` policy; `doctor` fails closed if the container toolchain drifts from
`bootstrap.lock.json`). Each build uploads `dist/<triple>` plus the build receipt, package
record, and qualify record, and preserves logs plus qualification evidence when it fails.

`assemble` downloads both triples, runs `build.py assemble`, checks `SHA256SUMS` with
`sha256sum -c`, and uploads `dist/release/`. `smoke` verifies the checksums again and runs
`build.py published-smoke --target <triple>` against the exact assembled bytes (Linux inside
the same Alpine container). `release` rechecks the ref, refuses an existing
`release-<sha>` tag, creates the tag at `$GITHUB_SHA` through the GitHub API, writes the
notes, and publishes:

```sh
gh release create "$RELEASE_TAG" --repo "$GITHUB_REPOSITORY" --target "$GITHUB_SHA" \
  --prerelease --verify-tag --title "$RELEASE_TAG" \
  --notes-file "$RUNNER_TEMP/release-notes.md" dist/release/*
```

## Installing

`~/usr/dl node-build` installs the latest prerelease for the host triple
(`aarch64-apple-darwin` on Apple Silicon, `x86_64-unknown-linux-musl` on Linux x86_64) into
`$XDG_DATA_HOME/node-build/<tag>`, verifying `SHA256SUMS` before extraction and symlinking the
result. The per-triple manifest carries the archive hash.
