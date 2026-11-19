Prefix: DSLP
Next: 9

Deslop campaign backlog ([plan](https://github.com/laputa-systems/stuff/blob/main/docs/campaigns/deslop.md), tier A). One agent works this file with the `deslop` skill: take the lowest-numbered open ticket whose area does not start with `Needs owner ·`. After DSLP-5, work the open P1 and P2 findings, then fill in `## Report` below.

## Report

Dead code (DSLP-5), discovery only at `043c8cff201b67516d048ab0e0ed2d186890c5a6`: Ruff F401/F841 passed in `make lint`. Vulture 2.16 at 60% reported 17 names in `buildsys/` and `build.py`: five unused-looking exported layout constants, `expected_release_assets` (called by controller and release tests), two dataclass `build_python` fields, and nine TypedDict fields used in returned records. The constants have only static non-use evidence and were retained. No whitelist was added. The former single-target release `assemble` wrapper was already removed by `f10806e`; `build.py` calls `assemble_all`. The release workflow invokes assembly and published smoke; `docs/RELEASE.md` identifies `dl` as an archive consumer. No removal was made and neither platform's artifact was rebuilt. Deptry 0.25.1 reported 12 findings from mapping the `laputa-buildlib` distribution to the wrong import name, `laputa_buildlib` instead of `buildlib`; with `--package-module-name-map laputa-buildlib=buildlib`, it found no dependency issues. The scan does not meet the five-entry acceptance, so DSLP-5 remains open.

Ground (DSLP-1) passed at base `c63d32672583e134ed705396ef9951e437546e31`. The pinned Alpine environment passed all 74 tests twice with Git installed for the release fixtures. Local macOS has Xcode 27.2 and SDK 27.2, while the lock expects Xcode 27.1 and SDK 27.0. [Verification](AGENTS.md#verification) records the command costs and coverage.

Diagnose (DSLP-2) reviewed the first-party controller, artifact and provenance handoffs, docs, and sampled tests at `524ced8eda5ebbd7884d739a8cc5b58887d8ae75`. It filed two P2 findings, DSLP-6 and DSLP-7, with [sealed fixture reproductions](docs/DIAGNOSE.md). Pinned Alpine `make test` passed 74 tests including the musl host check; native `make lint` passed. The fixtures exercise local assembly. Native Node builds and the hosted release workflow remain separate checks.


Types (DSLP-3) validated the pinned buildlib wheel source record at
`20884c2`. The bootstrap now checks URL, digest, and integer size before
cache or network use. The old code accepted a boolean size as equal to one
byte. A sealed fixture detected it, and the download fixture verified that
a digest mismatch leaves existing cache bytes intact. The valid cache-hit
fixture still passes. Tests passed all 76 cases in the pinned Alpine builder,
including the musl host check. Ruff and ty passed on macOS.

The strict probes fell from nine to seven unsound returns and from 33 to
32 missing type arguments. The wheel bootstrap has zero findings under
both probes. The wider rules remain unadopted while the bootstrap lock,
build record, and smoke paths still have type gaps.


The second Types slice adopts ty's `unsound-return-statement` rule. A
sealed configure-marker fixture showed that a valid JSON array caused an
attribute error, so the controller now treats a non-object marker as stale.
Toolchain version parsing returns the matched substring as a string, and
the smoke runner declares the text result produced by `subprocess.run`.

The original strict probe reported nine unsound returns. The post-wheel
baseline at `8b53815` still reports seven with the adopted rule enabled.
The final lint is clean. The missing-type-argument probe has 30 findings
left from 33, and the unused-ignore and ANN401 probes found no qualifying
witness. The 77-test pinned Alpine suite, including the musl host check,
passed. The local Xcode and Clang version probes also passed.


Tests (DSLP-4) is done under the revised mutation policy. Coverage is a
report, not a gate: [the hosted coverage run](https://github.com/laputa-systems/node-build/actions/runs/44297774733)
measured the 21 first-party Python files. The required mutation scope is the
following contract boundaries, not whole modules:

- Archive admission, digests, atomic publication and staging cleanup:
  `buildsys/release.py` `all_checks_ok`, `validate_triple`, `stage_triple`
  and `assemble_all`, plus the Git and record readers they use. The ordinary
  `tests/test_release.py` fixtures reject incomplete or stale records and
  changed archive bytes, check checksums and concurrent publication, and
  verify cleanup after failed publication. `buildsys/package.py` `package`,
  `install_to_stage` and `create_archive` are covered by release and product
  fixtures for receipt and binary digests, failed checks, deterministic
  archive layout, and refusal to overwrite published archives.
- Release budgets: `buildsys/budgets.py` `archive_payload_bytes`,
  `_byte_limit` and `check_budgets`. `ArchiveBudgetTest` checks exact ceilings,
  both exceeded limits, invalid limits and missing inputs using a real archive.
- Success and failure reporting: `buildsys/smoke.py` `run_node`, `run_suite`
  and the probe result checks, including the complete success-line and exit
  checks fixed in #84. `tests/test_smoke.py` checks matching and decorated
  markers, nonzero exits, exact TAP counts, filesystem readback, timeout and
  error reporting, and suite continuation. Inspector fixtures check malformed
  responses, deadlines and child cleanup. `tests/test_cli.py` checks controller
  results and error streams.

The prior results and survivor dispositions are grouped by behavior:

- Release admission and publication: the matched native release census at
  `46c82f2` accounted for 390 identities. Linux caught 382 and macOS 373.
  Five shared survivors preserve subprocess defaults or revision trimming;
  two change incidental diagnostic text. The omitted UTF-8 encoding was caught
  by the C-locale fixture. Nine macOS path-case variants were caught on a
  case-sensitive host. [Release census](https://github.com/laputa-systems/node-build/actions/runs/44428020350)
- Package publication and cleanup: the post-fix native census at `f04ca44`
  accounted for 315 identities. Linux caught 305 and macOS 296. Seven of the
  ten shared installer survivors fail the nested-stage or C-locale fixture
  when replayed directly; three spell the same UTF-8 codec differently.
  Nine macOS path-case variants were caught on Linux. Private temporary-name
  prefixes have no consumer contract and need no assertion.
  [Package census](https://github.com/laputa-systems/node-build/actions/runs/44436014451)
- Budgets: the native jobs accounted for 81 identities. Linux caught 80 and
  macOS 78. The shared survivor omits the equivalent default tar read mode;
  Linux catches the two macOS path-case variants.
  [Budget results](https://github.com/laputa-systems/node-build/actions/runs/44433110100/attempts/2)
- Smoke reporting: the focused architecture and suite selection caught all
  122 matched variants; the two process-wrapper survivors use equivalent
  falsey subprocess defaults. The async readback selection caught all 35.
  The worker-child native selection caught 62 of 65; the other three select
  equivalent UTF-8 encodings for its ASCII script. The version, help, addon
  and exclusion selection had seven survivors from case changes, equivalent
  Darwin defaults or falsey subprocess defaults. The node-test selection's
  one survivor changes fixture path case on macOS. The exclusion selection's
  three path-case variants likewise require a case-sensitive replay; its two
  other variants use equivalent falsey `follow_symlinks` values. These
  case-sensitive replays are incomplete, not passes. Incidental diagnostic
  wording does not warrant a new test.

The full smoke inventory at base `468d0761` caught 683 of 999 identities
after #84, with 316 survivors and no timeouts. That module sweep includes
native script effects beyond the reporting boundaries above; its remaining
survivors are unclassified advisory work, not a passed required scope. The
broader product inspection, qualification, reproduction, relocation and CLI
module sweeps are also advisory and incomplete. Qualification and reproduction
still have macOS path-case survivors awaiting a case-sensitive replay. The
broader CLI run had one unconfirmed timeout, although a focused selection caught
the same variant. No whole-change mutation lane is required by this closure;
the draft workflows in #47 and #61 remain drafts. No new mutation trial was run
for this closure: aggregate runner cost was 0 minutes. Historical results use
mutmut 3.8.1 and pytest 9.2.0; their linked jobs retain platform and result data.

Release provenance (DSLP-6) closed after sealed fixtures established the
checkout, source lock, binary, receipt and archive digest links. They also
check that a changed archive cannot be published between validation and copy.
[Native artifact qualification](https://github.com/laputa-systems/node-build/actions/runs/44367665068)
separately built and verified both supported targets. It is not a substitute
for the controller fixtures or a new artifact qualification at this revision.


## Tickets




### DSLP-5 · P2 · Dead code: tools and debloat

- **Area:** deslop · dead code
- **Where:** whole repository
- **Problem:** No dead-code scan has run.
- **Recommendation:** Run the deslop Dead code step. Accept: tools clean or allowlisted with reasons; walk-backs filed as Needs owner tickets.
- **Fix with:** deslop
- **Effort:** M






### DSLP-8 · P3 · Qualify remaining generic return and input shapes

- **Area:** deslop · types
- **Where:** buildsys/node.py; buildsys/release.py
- **Problem:** The missing-type-argument candidate has open declarations in these modules. The comparison and assembly results have checked shapes and negative witnesses. Parsed release records and the build controller need separate evidence.
- **Recommendation:** Work one producer and its consumers at a time, preserve the accepted JSON forms and add a negative witness where precise types reject an actual bad program.
- **Fix with:** typing-audit
- **Effort:** M
