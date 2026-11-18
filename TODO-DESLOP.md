Prefix: DSLP
Next: 8

Deslop campaign backlog ([plan](https://github.com/laputa-systems/stuff/blob/main/docs/campaigns/deslop.md), tier A). One agent works this file with the `deslop` skill: take the lowest-numbered open ticket whose area does not start with `Needs owner ·`. After DSLP-5, work the open P1 and P2 findings, then fill in `## Report` below.

## Report

Ground (DSLP-1) passed at base `c63d32672583e134ed705396ef9951e437546e31`. The pinned Alpine environment passed all 74 tests twice with Git installed for the release fixtures. Local macOS has Xcode 27.2 and SDK 27.2, while the lock expects Xcode 27.1 and SDK 27.0. [Verification](AGENTS.md#verification) records the command costs and coverage.

Diagnose (DSLP-2) reviewed the first-party controller, artifact and provenance handoffs, docs, and sampled tests at `524ced8eda5ebbd7884d739a8cc5b58887d8ae75`. It filed DSLP-6 (P1) and DSLP-7 (P2), with [sealed fixture reproductions](docs/DIAGNOSE.md). Pinned Alpine `make test` passed 74 tests including the musl host check; native `make lint` passed. No native Node build, release, external target, mutation or performance run was attempted. The fixture results do not establish that the hosted workflow mixed artifacts or produced an empty record. Local Xcode and SDK pins remain unchanged. The other backlog `TODO.md` is absent at this revision; DSLP-3 through DSLP-5 remain open.

## Tickets

### DSLP-6 · P1 · Bind assembled provenance to the build inputs

- **Area:** release provenance
- **Where:** buildsys/node.py:179; buildsys/release.py:46; buildsys/release.py:85
- **Problem:** Assembly labels an existing qualified archive with the current checkout revision and lock hash without linking the receipt to either; a clean checkout changed after the build can produce a manifest that misidentifies the artifact's provenance. The sealed fixture in docs/DIAGNOSE.md reproduces an old receipt assembled under a new revision; the hosted workflow was not shown to mix artifacts.
- **Recommendation:** Record the build's controller revision and relevant lock identity in the receipt, bind the package and qualification to that receipt and archive, and reject mismatches during assembly. Add a fixture that changes the checkout after building and expects rejection.
- **Fix with:** durable-state
- **Effort:** M


### DSLP-3 · P2 · Types: strict profile and typing findings

- **Area:** deslop · types
- **Where:** type checker and lint configuration; Python sources
- **Problem:** The strict-profile candidates in the deslop skill's tools reference have not been measured here.
- **Recommendation:** Run the deslop Types step. Accept: clean at the adopted profile, escape hatches not increased, witnesses recorded.
- **Fix with:** deslop
- **Effort:** M

### DSLP-4 · P2 · Tests: coverage, boundary gaps, mutation

- **Area:** deslop · tests
- **Where:** test suites and CI
- **Problem:** Coverage and mutation results are unmeasured; no deslop mutation lane exists.
- **Recommendation:** Run the deslop Tests step. Accept: no undispositioned survivor in critical code, the test cost budget holds, and the lane is green where the tools are mirrored.
- **Fix with:** deslop
- **Effort:** M


### DSLP-5 · P2 · Dead code: tools and debloat

- **Area:** deslop · dead code
- **Where:** whole repository
- **Problem:** No dead-code scan has run.
- **Recommendation:** Run the deslop Dead code step. Accept: tools clean or allowlisted with reasons; walk-backs filed as Needs owner tickets.
- **Fix with:** deslop
- **Effort:** M


### DSLP-7 · P2 · Reject incomplete qualification records during assembly

- **Area:** release qualification
- **Where:** buildsys/release.py:42; buildsys/release.py:60; buildsys/qualify_runner.py:58
- **Problem:** Assembly accepts empty product, smoke, and relocation lists because all() is true for empty lists, and accepts zero smoke checks as qualified. The benign fixture in docs/DIAGNOSE.md assembles and writes a manifest with no checks. The normal qualifier has not been shown to emit such a record.
- **Recommendation:** Validate the qualification record's schema and required check coverage and counts before assembly, rejecting empty or incomplete records; exercise rejection with a sealed fixture.
- **Fix with:** durable-state
- **Effort:** M

