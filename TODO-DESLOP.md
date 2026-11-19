Prefix: DSLP
Next: 12

Deslop campaign backlog ([plan](https://github.com/laputa-systems/stuff/blob/main/docs/campaigns/deslop.md), tier A). One agent works this file with the `deslop` skill: take the lowest-numbered open ticket whose area does not start with `Needs owner ·`. After DSLP-5, work the open P1 and P2 findings, then fill in `## Report` below.

## Report

DSLP-1 base: `c63d32672583e134ed705396ef9951e437546e31`, the
first-parent of Ground squash #18. Review intent: preserve the controller's
contracts while strengthening provenance, tests and benchmark visibility.
The cumulative review through #87 found no additional demonstrated defect.

**Scorecard** (physical first-party Python lines, `build.py` and `buildsys/`
versus `tests/`): source 2,545 → 2,871; tests 981 → 3,422. The Python
escape-hatch expression in deslop's tools reference finds 7 → 7 occurrences
in source and 0 → 0 in tests. Dead-code cuts: five unused product constants
(5 lines) and the unused single-target assembly wrapper (4 lines); zero
dependencies removed. Ground's warm `make test` was 0.85 s in emulated Alpine
(74 tests); a current macOS run took 19.856 s (179 tests, one host-lock
failure). Different hosts and workload sizes make these non-comparable; no
timing gate was established. Ground coverage was not measured; the earlier
[hosted trial](https://github.com/laputa-systems/node-build/actions/runs/44297774733)
recorded 43.9% lines and 32.6% branches over 21 files, before later tests.
At #87, local branch instrumentation recorded 88.3% lines and 82.6% branches
(179 tests, the same host-lock failure); host and platform differ from the trial.

Findings filed: P1 0, P2 3 (DSLP-6, 7, 9), P3 3 (DSLP-8, 10, 11), P4 0;
fixed: P2 2 (6 and 7), P1/P3/P4 0. These counts exclude the step tickets and
unticketed fixes. No escaped regression has been established; production
escape monitoring was not performed. DSLP-9 remains **environment-blocked**:
`perf-gate-ready` reports a busy host; a quiet native host is needed. Perf gate
deferred: host busy. No overall runtime or build-time regression verdict is
claimed. #87 proved the Edit harness and missing-archive Change preflight;
the Change size workload requires a packaged archive, and Scenario/Full need
native builds. DSLP-10 and 11 retain attribution and freshness gaps.

**Mutation evidence:** the required scopes protect archive admission, digest
and receipt links, atomic publication and cleanup; package installation;
size ceilings; and smoke success/failure reporting. Their ordinary tests
exercise these behaviors, including negative inputs. Required release census
([run](https://github.com/laputa-systems/node-build/actions/runs/44428020350)):
390 identities, Linux 382 caught and macOS 373; shared survivors cover
subprocess defaults, revision trimming and diagnostic wording, while nine
macOS path-case variants were caught on Linux. Required package census
([run](https://github.com/laputa-systems/node-build/actions/runs/44436014451)):
315 identities, Linux 305 and macOS 296 caught; seven shared installer
survivors fail direct replay and three are equivalent codec spellings; nine
macOS case variants were caught on Linux. Required budgets
([run](https://github.com/laputa-systems/node-build/actions/runs/44433110100/attempts/2)):
81 identities, Linux 80 and macOS 78 caught; the shared default tar mode is
equivalent and Linux catches the two case variants. Required focused smoke
selections caught 122 architecture/suite and 35 async-readback variants;
worker-child had 62/65 caught and three equivalent encodings. Other focused
smoke survivors include equivalent defaults and case variants whose
case-sensitive replays remain incomplete. Do not count these as passed.

Advisory full smoke inventory: 683 caught, 316 missed, 0 timeouts out of 999;
remaining survivors are unclassified. Product, qualification, reproduction,
relocation and CLI module sweeps are advisory and incomplete; qualification
and reproduction case replays remain outstanding, and one CLI timeout was
unconfirmed although a focused selection caught that variant. Unviable counts
and complete per-scope timeout counts were not recorded here; see linked jobs
and Git history. No before-campaign mutation baseline is available. These are
scope outcomes, not a score: the protected behaviors and defects fixed are the
outcome. The #85 closure ran no new mutation trials (0 runner-minutes); total
historical mutation runner-minutes were not consolidated. The linked release
census jobs consumed about 5.6 combined runner-minutes (1m08s Linux, 4m26s
macOS); this is only that run, not the campaign total. Whole-change mutation
workflows #47 and #61 remain drafts.

**Steps and cost.** Ground #18 mapped boundaries; Alpine tests 0.81/0.85 s,
macOS lint 0.67/0.08 s cold/warm. Diagnose #19 reproduced the two assembly
findings in [fixtures](docs/DIAGNOSE.md). Types #20–21 fixed the boolean wheel
size and non-object configure marker; seven unsound-return findings were
resolved, while generic shapes remain DSLP-8. Tests #22–85 added boundary
fixtures and fixed release provenance, invalid budgets, process errors and
smoke false passes; [native qualification](https://github.com/laputa-systems/node-build/actions/runs/44367665068)
covered both targets at its recorded revision. Dead code #86: vulture found
17 candidates; five names removed, 12 dynamic/serialized or test uses retained.
Deptry needed `laputa-buildlib=buildlib` mapping and then found no dependency
issues. Bench #87 added tiered entrypoints and filed DSLP-9–11. Report reviewed
the cumulative diff and added no findings. Per-step total wall time and CI
minutes were not recorded; individual linked runs retain job timings.

**Method feedback and shared-file gaps.** Require exact success lines and
nonempty qualification evidence: substring checks and vacuous `all()` let
false passes slip through. Vulture flags serialized fields; deptry needs the
package/import mapping. Unused-ignore and ANN401 type probes found no qualifying
witness. The shared deslop tools report template still asks for mutant totals;
it should foreground protected behaviors and fixed defects and label required
versus advisory scopes and runner cost, matching campaign decision 4. No shared
file was changed.

## Tickets










### DSLP-9 · P2 · Cover representative runtime and build regressions

- **Area:** deslop · bench
- **Where:** buildsys/benchmarks.py; buildsys/comparison.py; docs/PERFORMANCE.md
- **Problem:** Unproven: five startup and synthetic JSON samples compare against upstream rather than an accepted prior build, and no build-time gate exists. User-visible regressions can be missed.
- **Recommendation:** Define representative completed-work runtime and native build comparisons against an accepted anchor, with variance and host validity before proposing gates.
- **Fix with:** refactor-benchmarks
- **Effort:** L

### DSLP-8 · P3 · Qualify remaining generic return and input shapes

- **Area:** deslop · types
- **Where:** buildsys/node.py; buildsys/release.py
- **Problem:** The missing-type-argument candidate has open declarations in these modules. The comparison and assembly results have checked shapes and negative witnesses. Parsed release records and the build controller need separate evidence.
- **Recommendation:** Work one producer and its consumers at a time, preserve the accepted JSON forms and add a negative witness where precise types reject an actual bad program.
- **Fix with:** typing-audit
- **Effort:** M


### DSLP-10 · P3 · Add attribution and provenance for performance runs

- **Area:** deslop · bench
- **Where:** buildsys/comparison.py; buildsys/benchmarks.py; docs/PERFORMANCE.md
- **Problem:** Comparison records omit binary identities, host pressure and process-tree resource attribution. JSON timing has millisecond resolution, and fixed reference-first order can bias results.
- **Recommendation:** Record artifact identity and host conditions, balance order, and document separate CPU sampling, memory and I/O diagnostics with their overhead.
- **Fix with:** benchmark-checklist
- **Effort:** M


### DSLP-11 · P3 · Verify benchmark input freshness and run isolation

- **Area:** deslop · bench
- **Where:** buildsys/bench.py; buildsys/comparison.py
- **Problem:** The driver warns but cannot establish archive and candidate freshness. The comparison harness reuses compare-work, and free space and leftover processes are not checked.
- **Recommendation:** Use existing receipts to verify inputs and add bounded disk and process checks without changing the comparison contract.
- **Fix with:** none
- **Effort:** M
