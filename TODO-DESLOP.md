Prefix: DSLP
Next: 9

Deslop campaign backlog ([plan](https://github.com/laputa-systems/stuff/blob/main/docs/campaigns/deslop.md), tier A). One agent works this file with the `deslop` skill: take the lowest-numbered open ticket whose area does not start with `Needs owner ·`. After DSLP-5, work the open P1 and P2 findings, then fill in `## Report` below.

## Report

Ground (DSLP-1) passed at base `c63d32672583e134ed705396ef9951e437546e31`. The pinned Alpine environment passed all 74 tests twice with Git installed for the release fixtures. Local macOS has Xcode 27.2 and SDK 27.2, while the lock expects Xcode 27.1 and SDK 27.0. [Verification](AGENTS.md#verification) records the command costs and coverage.

Diagnose (DSLP-2) reviewed the first-party controller, artifact and provenance handoffs, docs, and sampled tests at `524ced8eda5ebbd7884d739a8cc5b58887d8ae75`. It filed two P2 findings, DSLP-6 and DSLP-7, with [sealed fixture reproductions](docs/DIAGNOSE.md). Pinned Alpine `make test` passed 74 tests including the musl host check; native `make lint` passed. The fixtures exercise local assembly. Native Node builds and the hosted release workflow remain separate checks. DSLP-3 through DSLP-5 remain open.


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


Tests (DSLP-4) added `make coverage` for the ordinary controller suite.
On hosted Ubuntu ARM64, coverage.py 7.17.3 measured all 21 tracked
Python files, with 629 of 1,432 statements and 148 of 454 branches.
The run reported 77 tests, including the expected glibc skip of the native
musl host check. All 77 passed separately in pinned Alpine at the Types
checkpoint. [Coverage run](https://github.com/laputa-systems/node-build/actions/runs/44297774733)

The covered layers include pure parsing, locks and recipes, sealed controller
fixtures, release assembly and artifact validation. Native builds and
published artifact smoke have separate entry points. Direct CLI coverage
and the mutation checks remain open.

The assembly record slice at `79fb67417304aa304efcf9705fd18dae28e8b62b`
used mutmut 3.8.1 and pytest 9.2.0 on macOS arm64, Python 3.15.2, on a
case-insensitive filesystem. Two independent copies selected every mutant in
`all_checks_ok` (10) and `validate_triple` (123); their identity sets matched
exactly. Baseline: 123 killed, 10 survived. With the record fixtures in
`tests/test_release.py`: 124 killed, 9 survived. Both had zero no-tests,
timeouts, suspicious, skipped, type-check kills, interrupted, unviable, or
uncompleted selected mutants. Mutant 87 in `validate_triple`, which removes
the qualification digest comparison, changed from survived to killed.
The mutation execution rates were 2.06 and 1.75 per second, respectively;
both complete runs exited 0 under the 120-second cap. These are not a release
gate or a whole-controller result.

The nine remaining `validate_triple` survivors are open: 11, 23, 25, 33,
35, 76, 78, and 80 change path case, which this filesystem does not distinguish
but Linux does; 13 drops the missing-archive diagnostic. Other release and
producer boundaries remain open. A hand-injected change from `is True` to
`== True` in `all_checks_ok` made the new package-record subtest with
`{"ok": 1}` fail because assembly did not reject it. The unmodified release
suite passed 19 tests and `make lint` passed.

To reproduce from the base and a checkout containing these tests, with an empty
`.work/tmp` and an installed Python 3.15:

```sh
mkdir -p .work/tmp/baseline .work/tmp/candidate
uv venv --python 3.15 .work/venv
uv pip install --python .work/venv/bin/python --index-url https://pypi.17166969.xyz/simple 'mutmut==3.8.1' 'pytest==9.2.0' 'laputa-buildlib==0.1.0'
git archive 79fb67417304aa304efcf9705fd18dae28e8b62b | tar -x -C .work/tmp/baseline
git archive 79fb67417304aa304efcf9705fd18dae28e8b62b | tar -x -C .work/tmp/candidate
cp tests/test_release.py .work/tmp/candidate/tests/test_release.py
for d in .work/tmp/baseline .work/tmp/candidate; do
  printf '\n[tool.mutmut]\nsource_paths = ["buildsys/"]\nonly_mutate = ["buildsys/release.py"]\npytest_add_cli_args_test_selection = ["tests/test_release.py"]\nalso_copy = [".github/"]\n' >> "$d/pyproject.toml"
done
for d in baseline candidate; do
  (cd ".work/tmp/$d" && mkdir -p .work/tmp && TMPDIR="$PWD/.work/tmp" timeout 120 cpu-guard --cores 2 -- ../../venv/bin/mutmut run --max-children 1 'buildsys.release.x_all_checks_ok__mutmut_*' 'buildsys.release.x_validate_triple__mutmut_*')
done
```

Compare the selected keys and values in each `mutants/buildsys/release.py.meta`
`exit_code_by_key` map; the progress denominator also includes unselected
mutants in the file and is not the selected count. The precise fault control
can be repeated in a third copy by replacing `entry.get("ok") is True` with
`entry.get("ok") == True` and running `python -m pytest -q
tests/test_release.py::AssembleTest::test_rejects_bad_checks_in_each_record_section`.


Release assembly now requires nonempty product, smoke, and relocation
checks with explicit successful results. Smoke counts must match the
recorded smoke entries. The sealed fixture exercises five incomplete
records, including an empty list that created a release on the baseline.
The candidate rejects them before creating the output directory. All 78
tests passed in pinned Alpine, including the native musl host check.


Release provenance (DSLP-6) closed after sealed checks exercised the
checkout, build, package and assembly boundaries.
The source-lock slice records the pre-build digest, rejects a lock changed during
the build, and rejects stale or unbound receipts before assembly stages assets.
A sealed pair of same-version tarballs also proves that the build rejects a
previously extracted tree after its archive pin changes. The package record additionally links the
build receipt to the archive digest; assembly rejects a mismatched receipt or
archive before staging. A clean checkout revision is now checked before and
after building and matched by assembly. The sealed controller and package
fixtures exercise these links. The receipt now also hashes the built executable.
Packaging refuses an absent digest or a different installed binary before creating
an archive. The pinned Node installer copies the binary bytes on macOS and Linux.
Native release qualification remains separate.

Malformed record fixtures reproduce raw JSON and type exceptions on the base.
Assembly now reports the offending record and rejects a missing, empty or
non-boolean package check before publishing output. All 87 pinned Alpine
controller tests passed.

## Tickets



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






### DSLP-8 · P3 · Qualify remaining generic return and input shapes

- **Area:** deslop · types
- **Where:** buildsys/budgets.py; buildsys/comparison.py; buildsys/node.py; buildsys/release.py
- **Problem:** The missing-type-argument candidate still reports 30 declarations. Their valid JSON and controller shapes need separate evidence before this setting qualifies.
- **Recommendation:** Work one producer and its consumers at a time, preserve the accepted JSON forms and add a negative witness where precise types reject an actual bad program.
- **Fix with:** typing-audit
- **Effort:** M
