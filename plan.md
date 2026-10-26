# node-build campaign — macOS arm64 complete, Linux x86_64 in progress

## Header

- **Status:** macOS arm64 COMPLETE 2026-10-26 (see closeout entry below);
  Linux `x86_64-unknown-linux-musl` IN PROGRESS on Alpine x86_64 host.
- **Resume:** n/a for macOS — closed. For Linux: `python3 build.py build &&
  python3 build.py package && python3 build.py qualify` with
  `--target x86_64-unknown-linux-musl`, then budgets + compare + docs + report.
- **Goal:** A functioning, tested `node-build` repository in the local tree that produces a
  lean, PIE-hardened, relocatable Node.js distribution for `aarch64-apple-darwin` from locked
  upstream Node v26.12.1 sources, with transactional release assembly and native qualification.
- **Deliverables:**
  - D1. Controller + locked sources (`build.py`, `sources.lock.json`, `bootstrap.lock.json`,
    `buildsys/`) with `doctor / fetch / build / qualify / package / reproduce /
    compare-reference / controller-test` semantics.
  - D2. One qualified macOS arm64 product: PIE `EXECUTE` `node` binary, small ICU, working
    TLS/crypto, snapshots, `Intl`, workers, inspector, native N-API addon loading, headers
    shipped, npm/npx absent.
  - D3. Mach-O hardening validator + machine-readable per-target hardening report; release gate
    rejects missing/failed checks.
  - D4. Relocatable install layout + transactional archive output + manifests
    (`artifact-*.json`, `assembly.json`, `download-metadata.json`, `smoke-metadata.json`,
    `SHA256SUMS`) under the single product-naming source of truth.
  - D5. Native runtime qualification suite (success AND failure paths, loopback only) run
    against final extracted archive bytes, including relocation into a path containing spaces.
  - D6. Manually dispatched GitHub Actions workflow: controller tests → native macOS build +
    qualify → manifest validation + assembly → clean published-byte smoke → single prerelease
    (macOS asset only for this campaign).
  - D7. `compare-reference` against the official Node darwin-arm64 binary on the same machine,
    with measured numbers logged (not gating).
  - D8. Docs: `README.md`, `AGENTS.md`, `docs/SECURITY.md`, `docs/REPRODUCE.md`,
    `docs/COMPATIBILITY.md`, `docs/PERFORMANCE.md` — concise, no duplicated or unproven claims.
- **Last accepted checkpoint:** NB-5 close (`cce5fe41…` archive qualified 17/17, budgets green, 53/53 tests, compare no-measurable-difference).
- **Provisional work:** none.
- **Current steering decision:** winddown — no new items; land the restore chain, then final closeout commit.
- **Next steering checkpoint:** on resume, before running the restore chain.

## Handoff (paused 2026-10-26)

- **Resume:** "Resume the node-build campaign in /Users/josh/d/node-build: run the restore
  chain below, then final closeout (review diff, write final report in the campaign log,
  commit)." First command (single chain, ~40 min unattended, resumable):
  `python3 build.py build --target aarch64-apple-darwin && python3 build.py package --target aarch64-apple-darwin && python3 build.py qualify --target aarch64-apple-darwin && python3 build.py check-budgets --target aarch64-apple-darwin`
  Before dispatch, re-read current instructions and perform the parent steering
  checkpoint; do not rebaseline unchanged inputs.
- **State:** branch `main`, all work committed. Last accepted: NB-3 qualified archive
  `dist/aarch64-apple-darwin/node-26.12.1-aarch64-apple-darwin-r1.tar.gz`
  (sha `29dba992…`, 17/17 smoke) — archive bytes intact on disk. No provisional commits
  awaiting proof; every commit's acceptance is recorded in the campaign log. Known red:
  none in code (53/53 controller tests green); the on-disk build tree is mid-restore
  (see parked item).
- **Direction:** NB-1…NB-5 code complete (controller, native 26.0 build, borrowed
  hardening gate + 17-check loopback smoke, dated-prerelease assembly + published-byte
  smoke, compare harness, docs). Limiting stage throughout was full-clean-build wall
  clock (~35 min, V8-dominated); accelerate ruling killed the redundant 70-min reproduce
  rerun — P6 stands satisfied by run 1's honest "not reproducible" verdict (hashes in
  the 2026-10-26 accelerate log entry). Current ruling: no re-measurement, no new
  items; land the restore, then close. Next delivery: restored build tree +
  re-qualification + final report commit. Owner requirements unchanged: macOS arm64
  only (O1), borrowed python-build hardening @ `5227de3` (O2), macOS 26+ floor (O3);
  no pushes, no releases, no `../python-build` edits (its floor change is owner's).
- **Open lanes:** none — width was 1, no lanes or worktrees ever created. One parked
  item: *restore chain* (re-extract + full build + package + qualify + budgets; the
  winddown kill interrupted the in-flight restore mid-compile and the tree is left in
  a make-resumable state). Retry condition: none needed beyond rerunning the chain —
  it is idempotent (verified fetch, fingerprinted configure, transactional package).
  No defect is parked; the kill was procedural, and the interrupted `make` failure in
  `.work/tmp/restore.log` is its expected footprint, not a product red.
- **Cleanup:** zero worktrees created or removed (`git worktree list` shows only the
  main checkout). Preserved under gitignored paths: `build/cache/node-26.12.1.tar.gz`
  (verified 127 MB source), `dist/aarch64-apple-darwin/` (accepted archive),
  `.work/tmp/` logs (build, package, qualify, reproduce run-1 verdict evidence).
  `build/src` + `build/aarch64-apple-darwin` hold a partial compile tree from the
  killed restore — kept deliberately, `make` resumes incrementally. No campaign state
  in `/tmp`, no processes remain, no cron/wakeup exists.
- **Not started:** nothing in NB-1…NB-5 remains unbuilt. After the restore chain:
  final review pass over `git log` + full `controller-test`, final report, closeout
  commit. Owner owes no decisions (Linux re-enable and python-build floor change are
  recorded future work, not blockers).
- **Verified:** reboot audit 2026-10-26 — worktree list clean (main only); `rg` finds
  no `/tmp|/var/folders|/private/tmp|$TMPDIR` paths in the doc (only the never-`/tmp`
  charter rule); `git branch` shows main only; no campaign processes remain; this doc
  leaves nothing the campaign needs untracked (build outputs stay gitignored by
  design, reproducible from locks).

## Charter (the executor runs by this)

1. Decide, log the call with evidence, keep going. Run until every deliverable is met or every
   remaining item is parked behind a hard stop with evidence, a named prerequisite, and a retry
   condition.
2. Act only within the execution grant (boundary section below). This doc does not grant missing
   permission. Park anything needing authority outside the grant; continue authorized work.
3. Hard stops (each parks the item): irreversible or outside-the-repo effects; a boundary the
   doc forbids; a loop that cannot check anything. Pushing, publishing a GitHub release, and
   creating the GitHub repository are forbidden in this campaign (no push was requested).
4. Fix egregious breakage met along the way in its own Conventional Commit when it blocks
   delivery: a command over 10 minutes with no output and no documented long-build reason; a
   regression over 2× against the baseline on the same machine; a test red on the baseline that
   blocks the item. Log anything else seen and leave it.
5. Parity before optimization. D1–D6 and their tests come first. Benchmarks (D7) are measured
   and logged, gating only a >2× regression or broken hardening/compatibility — never a
   missing speedup. A loop repair may happen earlier only when it unblocks a named deliverable,
   with a bounded exit test.
6. Keep bookkeeping minimal: reuse existing results and logs. Record revision + relevant inputs
   to qualify evidence; build no provenance platform, second register, or dashboard.
7. Size lanes and validation waves by ownership and measured capacity: initial width 1, max 2,
   provisional-work cap 2; reduce width when review/verification queues grow. Lane worktrees at
   `.work/wt/<lane>`; all scratch/state under `.work/` (incl. `TMPDIR=.work/tmp`), never `/tmp`.
   Follow the `orchestrate` worktree lifecycle; winddown keeps a worktree only if clean, named
   in the handoff, and allowed by the closeout guard.
8. Every commit is Conventional Commit (`type(scope): subject`, imperative, ≤72 chars, no
   trailing period); area/workstream is the scope; the item ID goes in the body, never the
   subject. Code comments never cite this doc. No formatters, no linters, no CI-only edits for
   unrelated work.
9. The parent (or resumed agent) reviews direction, not just completions: reconcile accepted
   results against this goal, sample accepted diffs and rejected proposals, classify
   obstructions (regression vs. newly exposed debt vs. invalid measurement vs. rule defect vs.
   environment prerequisite vs. owner-only decision), rule, and record the ruling in this doc's
   log while keeping the header/charter current. Never silently replace an owner requirement or
   waive a failed acceptance check.
10. Failing-item rule (`root-cause`): reproduce first with the smallest fast repro, test one
    hypothesis at a time with a predicted observation, fix at the origin. Time-box each item at
    3 attempts, then park with evidence, prerequisite, and retry condition. Shared environment
    blockers get one owner and are not rediscovered per item; requeue only when conditions
    change. Never retry to green, never loosen an assertion or validator to pass.
11. No vacuous proof: each acceptance check must fail if the behavior is broken (break it on
    purpose at least once for validators and naming/manifest bindings).

## Decisions

### Owner-decided (2026-10-26, recorded from the request; owner may overrule)

- O1. **Linux deferred; this campaign is macOS arm64 (`aarch64-apple-darwin`) only.** All
  Linux musl targets, Alpine/Clang-LLD container stages, ELF validators, and multi-platform
  release gates are parked (see Non-goals). The single-target prerelease in D6 supersedes the
  draft's all-three-platforms gate for this campaign; the three-target contract returns if the
  owner re-enables Linux.
- O2. **python-build hardening is finished: borrow its machinery.** Owner direction
  2026-10-26 supersedes the earlier do-not-copy rule. `buildsys/macho.py`
  adapts `../python-build/buildsys/macho.py` at `5227de3` (parser, `signature_status`,
  `find_machos`, `@rpath`/`@loader_path` resolution, system-path policy), and
  `macho_tree_checks` follows its `macho_checks` categories (whole-tree scan, fat
  rejection, exact minos match, dep/rpath resolution, per-image `--strict` signatures,
  non-PIE executables). Omitted with reason: install-name edit helpers (node ships no
  private dylibs) and reproduce-normalization helpers (no consumer yet). Node keeps its
  own supported crypto backend; no TLS replacement work.
- 2026-10-26 (accelerate ruling): bottleneck is full-clean-build wall clock (~35 min,
  V8-dominated); width 1 is correct, compilation already uses -j10. Killed the 70-min
  reproduce rerun: run 1 already satisfied P6 with an honest verdict (raw
  `d22e8091…` vs `69f7f68d…`, normalized `c1f704…` vs `3a04c7…`, both 118526136 bytes:
  not reproducible even outside signing metadata; embedded-date theory refuted —
  only vendored 2026-10-09 strings found). Chunk-localization machinery stays in the
  tree with unit tests; diagnosing the mechanism is parked until a future reproduce
  run, no extra authority needed. The rerun's wipe removed the build tree, so one
  restore build + package + qualify is running to leave the repo fully proven.
  Size evidence: official darwin-arm64 is 147 MB binary / 58.3 MB tarball vs ours
  118 MB / 44.0 MB — ours is leaner (small-ICU, no npm); neither binary carries
  `__DWARF`, so no strip step is owed and the `install_only_stripped` naming holds.
- O3. **macOS 26+ only.** Owner direction 2026-10-26: the product floor is macOS 26.0
  (host runs macOS 27). Same policy applies to python-build (outside this campaign's
  boundary — owner applies it there). Upstream Node 26 supports 13.5+, but this product
  sets a higher documented floor, matching python-build's artifact minimum.

### Prescribed (settled from the code, the evidence, or sound practice)

- P1. Reference oracle: authoritative upstream Node **v26.12.1** source + SHASUMS + official
  `darwin-arm64` binary at `https://nodejs.org/dist/v26.12.1/` (verified live 2026-10-26:
  `node-v26.12.1.tar.gz`, `node-v26.12.1-darwin-arm64.tar.gz`, headers tarballs present;
  **no** official `linux-arm64-musl` binary published — ARM64-musl support must be qualified
  independently when Linux returns). Consulted design reference: `../python-build` at
  `cde895aee64148cbee11adf5af57c2fcb1d04941` (`main`, 2026-10-25). Record this revision in
  `docs/REPRODUCE.md`. Reversal: only if the owner changes the Node version or reference.
- P2. macOS toolchain: native Apple Silicon, pinned Xcode + SDK recorded in
  `bootstrap.lock.json` (host floor and deployment minimum recorded separately, as python-build
  does). Observed host 2026-10-26: Xcode 27.1, SDK 27.0, Apple clang 21.0.0, `arm64`. Product
  floor macOS 26.0 (O3). CPU baseline `-mcpu=apple-m1`. Never `-march=native`, never
  `-ffast-math`, never disable memory-safety checks for benchmarks. Reason: portability
  and the draft's explicit bans.
- P3. Feature policy (lean but fully practical): V8 JIT/snapshots/code-cache on; CJS+ESM;
  `node:test`, workers, child processes, streams, fs/net; HTTP/HTTPS/HTTP2/TLS/WebCrypto/
  `node:crypto`; compression; N-API addon loading + shipped headers; inspector stays unless
  measured evidence with a named size benefit justifies a separate variant; built-in SQLite
  stays. **Small ICU** initially with the full-ICU difference documented; **omit npm/npx**
  via the supported `--without-npm` flag; no Corepack. Keep Node's supported crypto backend
  with exact version + provenance recorded. No Graviola/rustls/OpenSSL-replacement work.
  Any feature removal needs a specific size benefit + documented compatibility impact +
  regression coverage. Reason: draft §3 + correctness-over-megabytes priority.
- P4. Linkage: dynamic PIE executable (musl/`--fully-static` questions are Linux scope and
  parked). No Linux `-pie`-style flags applied blindly to the macOS link — proven 2026-10-26:
  Apple `clang` warns `-pie` is unused and PIE comes from default linker behavior with `PIE`
  in `otool -hv` output and `codesign --verify` passing. Inspect actual Ninja link commands;
  env-var flags prove nothing.
- P5. Hardening gate (macOS): every shipped executable is `MH_EXECUTE` + `MH_PIE`
  (flag `0x200000`, cf. `../python-build/buildsys/macho.py:106`), correct arm64 slice (thin,
  never fat/universal), correct `LC_BUILD_VERSION` platform/minos, valid load commands, no
  build-directory RPATH/RUNPATH, valid code signature after strip/package. Machine-readable
  hardening report per build; gate rejects missing/failed checks. Negative tests use synthetic
  malformed headers plus non-PIE/wrong-arch fixtures. Never weaken the validator; fix the
  build. Reason: draft §4 scoped to macOS + `reference-parity` (validator must fail on
  purpose-built-bad inputs).
- P6. Locks and sealed builds: two-layer `sources.lock.json` (Node source URL/size/SHA-256/
  provenance + licenses/roles; no invented hashes — fetch authoritative metadata and verify
  downloaded bytes) and `bootstrap.lock.json` (Xcode/SDK/LLVM/deployment floor/baselines;
  no floating tags). Network allowed only in acquisition; the compile phase runs from verified
  cached inputs without network. Build receipt binds source revision, lock hashes, toolchain
  identity, feature switches, effective flags, and archive digests. `reproduce` does two
  independent builds and reports mismatches; bit-for-bit reproducibility is never claimed
  without proof.
- P7. One product-naming implementation is the source of truth for archive names + metadata.
  Local artifact `dist/aarch64-apple-darwin/node-26.12.1-aarch64-apple-darwin-r1.tar.gz` +
  `artifact.json`; prerelease keeps the draft's dated convention (`tag 20261025 →
  title node-26.12.1+20261025`, `--prerelease`) with the macOS asset set only:
  `node-26.12.1+20261025-aarch64-apple-darwin-install_only_stripped.tar.gz`,
  `artifact-aarch64-apple-darwin.json`, `assembly.json`, `download-metadata.json`,
  `smoke-metadata.json`, `SHA256SUMS`. `artifact-*.json` binds exact archive bytes to source
  revision, toolchain, feature policy, hardening verdict, native runtime tests, archive
  SHA-256, and payload identity. Node-specific schemas; never claim uv/CPython-schema
  compatibility. Reject tag collisions, dirty checkouts, unqualified archives, mismatched refs.
  Transactional staging; re-validate hashes just before publication (publication itself is
  out of scope — see Boundary).
- P8. Qualification runs the **final extracted archive bytes** on the native host: version
  identity, arch/Mach-O linkage, CJS+ESM, local `node:test`, async fs, DNS/TCP loopback,
  HTTP+HTTPS servers/clients, invalid-cert rejection + trusted-cert acceptance, WebCrypto/
  crypto, compression, `fetch`/streams, workers/child processes, `Intl` per advertised ICU
  mode, snapshot/startup behavior, inspector connectivity, N-API addon compiled against
  shipped headers and loaded, C++ addon only if its ABI support is claimed, `node --help`
  vs. documented exclusions, npm/npx absence, relocation into two substantially different
  paths including one with spaces. Loopback fixtures only; no public-internet requirement.
  Failure paths are exercised, not just success paths.
- P9. Benchmarks (`compare-reference`, D7): same native machine, same Node version/workload/
  env/baseline/warmup; candidate vs. official darwin-arm64 binary; report change, versions,
  toolchain, CPU, flags, warmups/samples, median + spread (+ confidence where meaningful),
  startup/throughput/size, compatibility regressions. Minimum 5 runs per side alternating
  A/B/A/B; median for typical latency; count errors and verify outputs (checklist Q4/Q7 always
  answered). PIE-vs-non-PIE is an experimental comparison only — non-PIE is never published.
  No costly continuous microbenchmark jobs on the release path; keep it manually invocable.
  First release needs no production PGO. Reason: `make-it-fast` + `benchmark-checklist`.
- P10. Size budgets: `release-budgets.json` ceilings are measured from the first genuinely
  qualified macOS release with written rationales — never fabricated. Tracked in CI, not
  gating the first qualification except against absurdity (>2× vs. official binary asks for
  an explanation, not a waiver).
- P11. Closeout: delete what is dead per `dead-code-archaeology` (implementation + tests +
  config + docs + exports + flags, no tombstones), run the full suite + a final review pass
  over the diff, fix P1/P2 findings, write the final report (commit, commands, build
  outcomes, compressed sizes, hardening results, unresolved blockers; tested vs. planned
  artifacts distinguished).

### Delegated (executor decides inside the bound; smallest reversible assumption wins; log it)

- G1. Module consolidation: the draft's `buildsys/` list is a starting shape. Merge modules
  that do not merit separation (e.g. `elf.py` has no macOS consumer — omit it; keep
  `targets.py`, `product.py`, `inputs.py`, `bootstrap.py`, `recipes.py`, `node.py`,
  `macho.py`, `relocate.py`, `package.py`, `validate_product.py`, `release.py`,
  `reproduce.py`, `benchmarks.py` only where each earns its file). Bound: public CLI
  semantics in D1 stay fixed.
- G2. Cache/build/output directory layout and exact smoke-harness internals, reusing
  python-build's proven patterns (scrubbed env, timeouts, complete accounting; retries are
  bounded diagnostics). Bound: D5/D8 criteria and loopback-only rule are fixed.
- G3. Benchmark corpus size and exact workload choices. Bound: P9 methodology fixed; prefer a
  small actionable corpus (startup, JS throughput, JSON, HTTP/TLS, crypto/compression, worker
  spawn, RSS, archive size) over a framework.
- G4. Any genuinely new third-party Python dependency: allowed only with pinned version +
  hash, license recorded, and a written why-stdlib-cannot-do; default is no new dependency.
- G5. Doc filenames beyond the required six and README structure. Bound: D8 content
  requirements fixed; no duplicated or unproven claims.

## Baseline (verified 2026-10-26 at the current commits)

- Repo: `/Users/josh/d/node-build` — no commits on `main`, only untracked `plan.md` (this
  doc's predecessor). Nothing to regress against yet; the executor's first builds establish
  the baseline. Do not mistake a first-build red for a campaign regression.
- Design reference: `../python-build` `main` @ `cde895a` (clean tree), a CPython/musl
  pipeline with `buildsys/{targets,product,inputs,bootstrap,recipes,macho,elf,package,
  validate_product,reproduce,…}.py`, `Dockerfile`, `Makefile`, `build.py`,
  `.github/workflows/build.yml`. Reuse conventions, not implementation — especially nothing
  security-sensitive (O2).
- Upstream oracle: `https://nodejs.org/dist/v26.12.1/` live; `SHASUMS256.txt` lists
  `node-v26.12.1.tar.gz` (`717244a8…`), `-darwin-arm64` archives, and `-headers` tarballs.
  No `linux-arm64-musl` official binary — supports O1/P1.
- Host: macOS arm64, Xcode 27.1 / SDK 27.0 / Apple clang 21.0.0, 18 CPUs, load ~10 at
  measurement (busy host: benchmark sides must interleave and say so).
- Foundation proofs (run, not inferred):
  - F1. Host emits shippable-shaped Mach-O: `clang` → arm64 `MH_EXECUTE` with `PIE` flag,
    `codesign --verify` passes (`otool -hv` shows `NOUNDEFS DYLDLINK TWOLEVEL PIE`).
    Note: `-pie` is an unused-argument warning on Apple clang — Linux flag habits do not
    transfer (P4).
  - F2. Upstream metadata fetch works (`curl -sI` 200, ~127 MB `node-v26.12.1.tar.gz`
    advertised, SHASUMS retrieved). Full source download + hash verification belongs to NB-1,
    not to preflight.
- Loop timings (wall clock, same host): `git log/show` <1 s; SHASUMS fetch ~1–2 s; clang PIE
  smoke + `otool` + `codesign` ~2 s; `python3 build.py controller-test` in `../python-build`
  **exceeded 120 s with no output** — treat controller suites as phase/close gates, keep the
  per-item loop to the narrowest covering check, and time-box item work accordingly.

## Sequence

Phases: P0 ground → parity/completeness (D1–D6+D8) → hardening included throughout with its
own gate → optimization/polish (D7, budgets) → close (P11). One lane takes an item end to
end; linear order (each item prerequisites the previous) except NB-5 docs work which may
overlap NB-4 within the cap.

- **NB-1 — Foundation: controller, locks, toolchain checks. Prerequisites: none. Owns:
  `build.py`, `buildsys/{targets,product,inputs,bootstrap,recipes}.py`, `sources.lock.json`,
  `bootstrap.lock.json`, `Makefile`, `tests/test_controller.py`, `AGENTS.md` skeleton.**
  Fetch authoritative Node v26.12.1 metadata, verify downloaded bytes (size + SHA-256),
  write both lockfiles (no invented hashes), implement `doctor/fetch/controller-test` with
  native toolchain checks that distinguish unsupported targets from missing prerequisites.
  Size: medium (one lane, several sittings). Acceptance: `python3 build.py controller-test`
  passes; `python3 build.py fetch --target aarch64-apple-darwin` populates the cache from
  verified bytes only; `doctor` reports Xcode/SDK/baseline identity.
- **NB-2 — One real product: native macOS arm64 build. Prerequisites: NB-1. Owns:
  `buildsys/{node,recipes,bootstrap}.py`, `Dockerfile` (macOS-native path only or deleted if
  it earns nothing), build invocation, `build/` outputs (gitignored).**
  Compile pinned source natively with the recorded recipe (small ICU, `--without-npm`,
  `-mcpu=apple-m1`, upstream-compatible `-O2`/`-O3` choice recorded, no LTO/PGO promotion
  without evidence). Prove PIE/signature on the staged binary; demonstrate N-API addon
  compile+load against the staged headers. Size: large. Acceptance: staged `bin/node`
  reports correct version/arch, `otool -hv` shows `PIE`, `codesign --verify` passes,
  `Intl` works per small-ICU claim, a fixture N-API addon loads.
- **NB-3 — Package, validate, relocate, qualify. Prerequisites: NB-2. Owns:
  `buildsys/{macho,relocate,package,validate_product}.py`, install layout, `tests/test_*.py`
  for validators/relocation/smoke, `release-budgets.json` skeleton (no ceilings yet).**
  Implement pruning, safe extraction (symlink/path-escape rejection, permission-preserving),
  Mach-O validator + hardening report + gate (P5 with negative tests), relocation check (two
  paths, one with spaces; no absolute build-dir references; no fragile `/usr/local|/opt`
  symlinks), and the D5 runtime suite against final extracted bytes. Size: large.
  Acceptance: `python3 build.py qualify/package --target aarch64-apple-darwin` produces an
  archive that passes the gate and the full smoke matrix from a clean directory, including
  failure-path cases; validator tests fail on purpose-built-bad fixtures.
- **NB-4 — Release assembly + CI + published-byte smoke. Prerequisites: NB-3. Owns:
  `buildsys/{release,product}.py`, `.github/workflows/build.yml`, `.github/scripts/*`,
  manifest schemas, `dist/` layout (gitignored), `smoke-metadata.json` flow.**
  Single-source-of-truth naming; transactional staging; tag-collision/dirty/mismatched-ref
  rejection; `SHA256SUMS`; controller tests → native macOS build+qualify → manifest
  validation+assembly → clean-environment published-byte smoke (local bytes via
  `smoke-metadata.json` semantics; no network); `release-budgets.json` ceilings written from
  the measured qualified artifact with rationales. Size: medium. Acceptance:
  `python3 build.py reproduce --target aarch64-apple-darwin` reports match/mismatch honestly;
  assembled `dist/` validates byte-for-byte through the clean smoke; workflow is syntactically
  valid (JSON-parse all manifests; pin/permission checks on the workflow) with full-SHA pins, strict
  permissions, and no release credentials in build jobs.
- **NB-5 — Benchmarks, docs, close. Prerequisites: NB-4. Owns: `buildsys/{comparison,
  benchmarks}.py`, `benchmarks/`, `docs/*`, `README.md`, final report.**
  `compare-reference` vs. the official darwin-arm64 binary per P9; log numbers in
  `docs/PERFORMANCE.md` (no gating claims); write the remaining docs per D8;
  dead-code sweep (prove liveness of every survivor by caller or data need; delete the rest
  completely); full suite + final review pass; final report per P11. Size: medium.
  Acceptance: `python3 build.py compare-reference --target aarch64-apple-darwin` completes
  with a verdict + spread report; docs contain no portability/reproducibility/security claim
  beyond the recorded evidence; full test suite green.

Validation waves: each item ends on its narrowest covering check (the `Acceptance` line);
the full suite runs at NB-3 close (product behavior), NB-4 close (assembly integrity), and
NB-5 close (everything). Compatible provisional candidates may share one exact-tree wave;
isolate and bisect on failure; never claim intermediate commits were globally checked.

## Acceptance (nothing waits on a person)

- A1 (D1): `python3 build.py controller-test` green; `fetch` verifies bytes before use;
  `doctor` distinguishes unsupported target vs. missing prerequisite (exit codes + messages
  covered by tests).
- A2 (D2): staged `bin/node --version` matches `26.12.1`; `otool -hv` → arm64 `EXECUTE`
  `PIE`; `codesign --verify --verbose` passes; N-API fixture builds against shipped headers
  and loads; `Intl` smoke matches small-ICU documentation.
- A3 (D3): hardening report exists and is machine-readable; gate rejects a build with the
  report missing and with each negative fixture (non-PIE, wrong arch, malformed header,
  bad RPATH); validator unit tests fail when the validator is deliberately broken.
- A4 (D4): archive extracts to `node/{bin/node,include/node/…,lib/…,LICENSE}` with no
  npm/npx, toolchain, sources, objects, or caches; `SHA256SUMS` verifies; manifests parse
  and cross-bind (archive SHA-256 == tested bytes); re-running assembly into an occupied
  directory never silently overwrites.
- A5 (D5): full smoke matrix (P8, incl. cert-rejection and relocation-with-spaces) passes
  from the final extracted bytes in a clean directory, loopback only.
- A6 (D6): workflow + scripts present with pinned SHAs and least privilege; assembly
  validates the exact one-target set, product version, built revision, toolchain policy,
  qualification verdicts, and digests before emitting metadata; clean smoke consumes the
  assembled bytes (proves the published-byte path without publishing).
- A7 (D7): `compare-reference` emits per-experiment change/versions/toolchain/CPU/flags/
  warmups-samples/median-spread/size/compat notes with ≥5 alternating runs per side and
  error/output-correctness counts; verdict is faster/slower/no-measurable-difference/
  inconclusive with the limiter named.
- A8 (D8 + close): the six docs exist, agree with each other and with the evidence, and make
  no unproven claim; dead-code sweep has no survivor without a named caller or data need;
  final report names commit, commands, outcomes, sizes, hardening results, and blockers.

## Execution boundary

- Authorized: reading `../python-build` for conventions; network fetch of authoritative
  upstream metadata + pinned sources during acquisition only (hashes verified before use);
  native macOS builds, installs, and loopback-test servers on this host; creating/modifying
  files under `/Users/josh/d/node-build` (worktrees/state under `.work/`); running CI
  definition validation locally.
- Forbidden (park instead): creating the GitHub repository; pushing; publishing/creating
  releases; dispatching Actions; downloading anything not pinned in the locks; touching
  `../python-build` or any repo outside `/Users/josh/d/node-build`; Linux builds/containers
  (deferred — O1); weakening any validator or gate to pass; claiming a push/release occurred.
- Contract changes made by this campaign (for the owner): none to external contracts; the
  only contract defined is the new repo's own CLI + prerelease naming (D1/D6), which did not
  exist before. Linux-target support is an explicit deferred obligation, not a silent cut.

## Non-goals

- Linux targets (`x86_64`/`aarch64-unknown-linux-musl`), Alpine/musl builder images,
  Clang/LLD container stages, ELF validators, musl loader/`PT_INTERP`/RELRO/`BIND_NOW`
  specifics: parked until the owner re-enables Linux, because the owner deferred them and
  upstream publishes no `linux-arm64-musl` binary to compare against.
- npm/npx in the default archive; Corepack; `--fully-static`; `-march=native`;
  `-ffast-math`; ThinLTO-via-`--enable-thin-lto` (Windows-only flag — never assume it works
  on other platforms); production PGO without thorough qualification.
- Graviola/rustls/OpenSSL-replacement work; copying `python-build`'s RTLS backend,
  experimental Rust/CPython infra, Python benchmarks, or uv-mirror format.
- Windows, Intel macOS, and any other architecture: unsupported, never claimed.
- A benchmark framework or continuous perf jobs on the release path; exhaustive optimization
  experiments before a correct qualified baseline exists.
- Generalized compiler-distribution frameworks, second ledgers, dashboards, supervisor
  services, or provenance platforms.

## Reference

- **Oracle and parity corpus:** upstream Node v26.12.1 source + `SHASUMS256.txt` + official
  `node-v26.12.1-darwin-arm64.tar.gz` (behavioral baseline for `compare-reference`);
  `../python-build` CLI semantics (`doctor/fetch/build/qualify/package/reproduce/
  compare-reference/controller-test`) as the conventions inventory — behaviors inventoried
  from these, goldens captured from the reference binaries once, deliberate differences
  (small ICU, no npm, Node-specific manifest schemas) noted once with reasons in
  `docs/COMPATIBILITY.md`.
- **Verified code map (read 2026-10-26):** `../python-build/AGENTS.md:48` target/baseline
  table (separate host floor vs. deployment minimum — same discipline required here);
  `buildsys/macho.py:106` `MH_PIE` bit test with direct header parsing (model the approach,
  do not copy the file — O2); `build.py` `artifact.json`/manifest flow; two-layer
  `sources.lock.json` + `bootstrap.lock.json` with verified-bytes-before-use semantics;
  `.github/workflows/build.yml` manual-dispatch → build → qualify → assemble → smoke →
  publish sequence (macOS leg only for this campaign).
- **Background:** draft `plan.md` §§1–16 (this rewrite's source; its Linux, three-target,
  and full-optimization content is parked under O1/P9–P11, not dropped silently). Host
  evidence F1/F2 and loop timings in Baseline. Busy-host rule applies to all timing claims.

## Decision log and campaign log

- 2026-10-26 (linux reproduce + restore): two clean rebuilds linked
  bit-for-bit identical 129,786,392-byte binaries (raw sha `3b411237…`
  both attempts) — verdict `bit-for-bit reproducible`, stronger than the
  macOS result. Rebuilt archive from the surviving tree re-passed package
  (sha `4334c39a…`, 55,278,558 compressed / 190,965,048 payload — 88 bytes
  of tar-mtime drift vs the first archive, binary bytes identical),
  qualify 17/17, budgets, and compare (no-measurable-difference both
  probes). Budgets doc now binds the current archive bytes. Full suite
  73/73 green. Remaining: `assemble` / `published-smoke` (need a clean
  checkout; tree holds the uncommitted linux port) and the closeout commit.
  No pushes, no releases.
- 2026-10-26 (linux build+qualify green, first pass): native Alpine build
  exit 0 (`-march=x86-64-v2`, small-ICU, no-npm, no source patch — the
  `common.gypi` floor patch is macOS-only). `package` produced
  `dist/x86_64-unknown-linux-musl/node-26.12.1-x86_64-unknown-linux-musl-r1.tar.gz`
  (sha `98a089ef…`, 55,278,470 compressed / 190,965,048 payload; 129.8 MB
  `bin/node`). `qualify` green: 19 product checks (7 layout + 10 ELF gate +
  2 path-leak, 1 inert OpenSSL config string as on macOS), 17/17 loopback
  smoke, 4/4 relocation incl. spaces. Budgets set from these measures with
  ~28% headroom (71.0 MB / 243.0 MB). `compare-reference` vs system
  v26.12.1: no-measurable-difference on both probes (reproduce ran after;
  see entry above for the restore). Not run: `assemble` /
  `published-smoke` (need a clean checkout; working tree holds the
  uncommitted linux port) — parked, retry after commit.
- 2026-10-26 (linux scope opened): owner asked to finish the campaign for
  linux amd64 on the Alpine x86_64 host. Re-entry per O1 parked items:
  `x86_64-unknown-linux-musl` is now supported; linux arm64 stays parked.
  Plan: controller (targets/bootstrap/recipes/doctor) → `buildsys/elf.py`
  hardening validator + gate → native build → package + qualify against
  final bytes → budgets + compare + docs + final report. macOS code paths
  untouched in behavior (72 controller tests green incl. 16 ELF unit/gate
  tests; `elf.py` proven against the live 146 MB musl host binary:
  PIE, musl interp, 4 allowed deps, RELRO + BIND_NOW + NX).
- 2026-10-26 (closeout, final report): macOS arm64 deliverables met on `main`.
  Commands: `doctor` (toolchain pinned: Xcode 27.1, SDK 27.0, clang 21.0.0),
  `fetch` (127166097-byte source verified), `build` (native `-mcpu=apple-m1`,
  small-ICU, no-npm, `common.gypi` floor patch 13.5→26.0), `package`
  (install-tree `node/bin/node+include/node+LICENSE`, 44.0 MB tar.gz),
  `qualify` (22 product checks + 17/17 loopback smoke + 4/4 relocation, incl.
  path with spaces), `check-budgets` (44.0/179.7 MB vs 56/230 MB ceilings),
  `assemble` + `published-smoke` (contract-exact asset set, 17/17 on published
  bytes; placeholder repo removed afterwards), `compare-reference`
  (no-measurable-difference both probes vs same-version official binary),
  `reproduce` (honest "not reproducible": raw `d22e8091…` vs `69f7f68d…`,
  normalized `c1f704…` vs `3a04c7…`). Platform build outcomes: macOS arm64
  only — Linux parked per O1, three consecutive native builds all green.
  Security verification: whole-tree Mach-O gate (borrowed @ `5227de3`) green —
  1 thin arm64 image, MH_PIE, exact minos 26.0, system-only dep closure,
  `--strict` signature, no universal, stage-refs clean. Compressed 44023473,
  installed payload 179704746 bytes. Unresolved blockers: none for this scope.
  Tested vs planned: everything tested is in `tests/` (53 green); Linux
  targets, PGO promotion, and reproduce-mechanism diagnosis are parked,
  not claimed.
- 2026-10-26 (winddown): parked the in-flight restore chain (kill was procedural;
  retry is the idempotent restore chain in the Handoff). All NB-1…NB-5 work merged on
  `main`; no lanes, no worktrees, no processes. Status paused; resume via Handoff.
- 2026-10-26 (preflight): owner scope recorded (O1 macOS-only; O2 python-build flux) —
  Linux sections of the draft mapped to Non-goals + parked obligation, macOS specifics kept
  actionable in NB-1…NB-5/A1…A8. Prescribed P1–P11 from code/evidence; delegated G1–G5 with
  bounds. No owner questions outstanding.
- 2026-10-26 (preflight): sequencing fixed — 5 capability-sized items, linear, width 1
  (max 2), cap 2, attempt limit 3, waves per item + full suite at NB-3/NB-4/NB-5 close.
  Benchmarks moved to NB-5 (measured, not gating); validator negative tests kept in NB-3
  (they are parity/hardening, not optimization).
- 2026-10-26 (winddown): parked the in-flight restore chain (kill was procedural;
  retry is the idempotent restore chain in the Handoff). All NB-1…NB-5 work merged on
  `main`; no lanes, no worktrees, no processes. Status paused; resume via Handoff.
- 2026-10-26 (steering after NB-2): NB-2 accepted — native `make -j10` exit 0, staged
  `out/Release/node` is arm64 EXECUTE + PIE, codesign valid, `v26.12.1`, small-ICU `Intl`
  correct, snapshot enabled, N-API fixture answer 42, link closure is system-only.
  `python3 build.py build` driver proven incremental (38 s) with build-receipt.json.
  Ruling: proceed to NB-3 package + qualify.
- 2026-10-26 (steering: make-install hang + floor change). Root cause of the NB-3 package
  timeout: `make install` depends on `all`, and the redundant `./configure` re-run in
  `build` had invalidated the tree, so packaging retriggered a serial rebuild past the
  1200 s timeout. Fixes: `build` skips configure when the recorded recipe fingerprint
  matches; `package` invokes `tools/install.py` directly instead of `make install`.
  Owner set the floor to macOS 26+ (O3), so the 13.5 binary is superseded and NB-2 proofs
  re-run on the 26.0 binary. python-build floor change is outside the boundary (owner
  applies it there). Ruling: rebuild with 26.0, then package + qualify.
- 2026-10-26 (steering after NB-3): NB-3 accepted — borrowed whole-tree gate green on
  final bytes (22 product checks incl. exact minos 26.0, `--strict` signature, dep/rpath
  resolution; npm/npx absent; LICENSE + headers present), 17/17 loopback smoke, 4/4
  relocation (incl. path with spaces). Two prescribed narrowings, both with evidence:
  (a) OpenSSL `__cstring` config strings carry an inert absolute prefix (literal
  `$(BUILDTYPE)`, never resolvable; official nodejs.org binary ships the identical
  pattern `/Users/admin/build/ws/...`), so source-prefix hits are informational while
  stage-prefix leaks still gate; (b) LICENSE copied by packager since `install.py`
  does not install it. Ruling: commit NB-3, proceed to NB-4 assembly self-test (local
  placeholder repo; output removed afterwards, no fabricated metadata lingers).
- 2026-10-26 (steering after NB-1): NB-1 accepted — 16 controller tests green, doctor
  matches locked toolchain, fetch verified 127166097-byte source, linux/unknown targets
  fail closed with exit 2, unimplemented commands fail closed naming their milestone.
  Upstream default ICU is full-icu (verified in configure.py), so the recipe passes
  --with-intl=small-icu explicitly. Ruling: proceed to NB-2 unchanged; start the native
  build in background and write NB-3 validator modules while it compiles.

## For the owner afterwards

Read the final report (commit, commands, macOS build outcome, compressed + installed sizes,
hardening results, blockers; tested vs. planned distinguished), then `docs/SECURITY.md` and
`docs/COMPATIBILITY.md`. Cherry-pick: the whole repo is the artifact. To re-enable Linux,
say so explicitly — the parked three-target contract (§O1, Non-goals) is the re-entry list.
