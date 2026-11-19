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

The independent missing-archive fixture then caught mutant 13, which removes
its diagnostic. The eight remaining `validate_triple` identities altered path
case (11, 23, 25, 33, 35, 76, 78 and 80). The disposable case-sensitive Linux
ARM64 trial at `1a45eb7` caught all 133 identities with no surviving or missing
outcomes. The complete 90-test suite passed on pinned Alpine. Other release and
producer boundaries remain open.
[Hosted run](https://github.com/laputa-systems/node-build/actions/runs/44307096562) A hand-injected change from `is True` to
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

The assembly entrypoint slice at `8e2ea74a8248c6a36ad452a4ccd8e8cb9e1da7ae`
measured every mutation in `git_revision`, `clean_build_revision`, and
`load_record` in two independent archived copies on macOS arm64, Python 3.15.2,
mutmut 3.8.1 and pytest 9.2.0 from the mirror. Both commands exited 0 under
the 120-second cap, one mutmut worker, and `cpu-guard --cores 2`. The selected
identity sets were equal: 47 Git revision, 5 clean revision, 10 record, 62
total. Baseline: 34 killed, 23 survived, 5 no-tests. Candidate: 42 killed,
20 survived, 0 no-tests. Both had 0 timeouts, suspicious, skipped, type-check
kills, interrupted, unviable, and uncompleted selected mutations. The 388
progress denominator includes unselected functions. The 133 prior identities
were not rerun; `buildsys/release.py` was byte-identical in both copies and
the checkout.

All five clean-revision identities moved from no-tests to killed. Git revision
45 and 47 and record 2 moved from survived to killed. The candidate's remaining
survivors are Git revision 6, 7, 12, 13, 15, 21, 24, 25, 28, 29, 30, 32,
35, 36, 37, 39, 41, 46 and record 5, 7. `mutmut show` identifies Git 6/12/24
as timeout changes, 7/13 as equivalent default `check` values, 15/21 as command
case changes on this case-insensitive host, and 25 as `check=True`. Git 28–30
change the non-checkout error, which the scratch fixture does not reach because
it is nested in this checkout; 46 changes the root diagnostic while retaining
the asserted substring. Git 32/35/36/37/39/41 alter splitting or trimming Git
output and need distinctive checkout paths or output to distinguish. Record 5
uses the host default encoding, and 7 changes the spelling to `UTF-8`; both
survive under this UTF-8 locale. These remain open evidence, not claims of
equivalence across environments. More distant producer and output assembly
behaviors remain open.

The new fixture writes real records and initializes a disposable Git repository,
then checks clean, ignored, nested and untracked states. In a third archived
copy, replacing `return None if git_dirty(repo_root) else revision` with
`return revision` made `ReleaseInputTest.test_checkout_revision_and_cleanliness_follow_real_git_state`
fail on the untracked file (pytest exit 1, expected `None`). The unmodified
release suite passed 22 tests and 38 subtests, and `make lint` passed. The
broader controller selection had 48 passing tests but failed the known host
lock check: Xcode 27.2 versus 27.1 and SDK 27.2 versus 27.0.

Reproduce the two runs from the base and a checkout containing the tests:

```sh
mkdir -p .work/tmp/baseline .work/tmp/candidate
uv venv --python 3.15 .work/venv
uv pip install --python .work/venv/bin/python --index-url https://pypi.17166969.xyz/simple 'mutmut==3.8.1' 'pytest==9.2.0' 'laputa-buildlib==0.1.0'
for d in baseline candidate; do
  git archive 8e2ea74a8248c6a36ad452a4ccd8e8cb9e1da7ae | tar -x -C ".work/tmp/$d"
  printf '\n[tool.mutmut]\nsource_paths = ["buildsys/"]\nonly_mutate = ["buildsys/release.py"]\npytest_add_cli_args_test_selection = ["tests/test_release.py"]\nalso_copy = [".github/"]\n' >> ".work/tmp/$d/pyproject.toml"
  mkdir -p ".work/tmp/$d/.work/tmp"
done
cp tests/test_release.py .work/tmp/candidate/tests/test_release.py
for d in baseline candidate; do
  (cd ".work/tmp/$d" && TMPDIR="$PWD/.work/tmp" timeout 120 cpu-guard --cores 2 -- ../../venv/bin/mutmut run --max-children 1 'buildsys.release.x_load_record__mutmut_*' 'buildsys.release.x_git_revision__mutmut_*' 'buildsys.release.x_clean_build_revision__mutmut_*')
done
```

Compare the three complete key sets and values in `mutants/buildsys/release.py.meta`
`exit_code_by_key` for each copy; `mutmut show <identity>` displays a mutation.
For the fault control, archive the base into a third copy, copy the candidate
test file, make the replacement above in that copy, and run
`python -m pytest -q tests/test_release.py::ReleaseInputTest::test_checkout_revision_and_cleanliness_follow_real_git_state`.


The staging slice at base `0650c30475497f734e2f8eec8b763b2ca03f9964`
uses the real manifest writer and sealed local archives. It checks the copied
bytes, manifest metadata, absent optional metadata, and rejection of a staged
digest mismatch. On macOS ARM64 with Python 3.15.2, mutmut 3.8.1 and pytest
9.2.0, two independent copies selected the same 101 `stage_triple` identities.
Existing tests caught 55 and left 46 live. The new tests caught all 101.
A repeat of the final candidate caught the same 101. No selected timeouts,
missing tests, unchecked results or other outcome classes occurred.


Hand faults in a third archived copy made the metadata test fail for a zero
archive size, the optional metadata test fail for a `None` default, and the
digest rejection test fail when its guard was disabled. Each pytest command
exited 1. The missing-source case also verifies the error names the original
archive, and the success case asserts the exact copied bytes. The full release
test file passed 28 tests and 38 subtests, and lint passed.

Reproduce the selected runs from this base and candidate:

```sh
mkdir -p .work/tmp
uv venv --python 3.15 .work/venv
uv pip install --python .work/venv/bin/python --index-url https://pypi.17166969.xyz/simple 'mutmut==3.8.1' 'pytest==9.2.0' 'laputa-buildlib==0.1.0'
for d in base candidate; do
  mkdir -p ".work/tmp/$d/.work/tmp"
  git archive 0650c30475497f734e2f8eec8b763b2ca03f9964 | tar -x -C ".work/tmp/$d"
  if [ "$d" = candidate ]; then cp tests/test_release.py ".work/tmp/$d/tests/test_release.py"; fi
  printf '\n[tool.mutmut]\nsource_paths = ["buildsys/"]\nonly_mutate = ["buildsys/release.py"]\npytest_add_cli_args = ["-k", "assembles_standard_assets or archive_changed_between_validation_and_copy or StageTripleTest"]\npytest_add_cli_args_test_selection = ["tests/test_release.py"]\nalso_copy = [".github/"]\n' >> ".work/tmp/$d/pyproject.toml"
done
for d in base candidate; do
  (cd ".work/tmp/$d" && TMPDIR="$PWD/.work/tmp" timeout 120 cpu-guard --cores 2 -- ../../venv/bin/mutmut run --max-children 1 'buildsys.release.x_stage_triple__mutmut_*')
done
```

Compare the selected `exit_code_by_key` entries in each
`mutants/buildsys/release.py.meta`. The direct staging selection avoids the
deliberate concurrency barrier inside each mutation iteration; the full release
suite runs that barrier separately. Published artifacts and native builds were
not tested in this slice.


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


At `cb208c8`, replacing a qualified fixture after validation made assembly
publish the replacement. The copied archive is now checked against the earlier
qualified digest. Each attempt stages in its own temporary directory. The
controlled replacement fails with no output and a valid retry succeeds. Two
concurrent attempts each reached the checksum barrier. Exactly one published
a complete checksum-verified release and both cleared their temporary staging.
All 94 pinned Alpine tests plus Ruff and ty passed.

Assembly command mutation at `d021381ccfb624e3b02d31c0058c526582715743`
selected the same 64 `assemble_all` identities in two fresh macOS seals.
The original caught 45 and missed 19. The candidate caught 63 and missed
one. ID 16 uppercases `sources.lock.json`; both names resolve to the same
file on this volume. Its mutation outcome on Linux is unmeasured.

The command tests exercise empty and invalid targets, sorted multi-target
release output, verified checksums, cancellation by a rename failure, and
a competing publication. A deterministic callback creates a nonempty
competing destination, and the real rename then fails. Assembly leaves
the competing file intact and removes its private staging tree. Changing
the losing assembler's diagnostic to `AssemblyError(None)` made that
focused test exit 1 on the message assertion. The independent two-thread
test runs in ordinary CI. All 102 pinned Alpine controller tests and
Ruff and ty passed.

Use the staged-triple recipe with this new base and a fresh scratch pair.
Set `pytest_add_cli_args = ["-k", "AssembleTest and not concurrent_assemblers"]`
and select `buildsys.release.x_assemble_all__mutmut_*`. Both runs exited
zero within 120 seconds. The production mutation files compare byte
for byte and the selected result maps account for all 64 identities.
Native release qualification and the wider Tests gate remain open.

Doctor lock admission at `c1c8b097b9deccc5836cffac613472ef43d7aa20`
reproduced an uncaught `TypeError` for a null toolchain. A list and
a string with the expected field names, and a numeric baseline flag,
reached host inspection before rejection. The candidate checks the
object shape of every required section and string values in the four
sections consumed by Doctor. The real Doctor path returns 2 with the
exact section or field error before inspecting the host. The ordinary
suite still checks the tracked lock on the pinned Alpine builder.
The lock's versions and supported targets are unchanged.

At `2b97433e023dc638d2cc2fc8de8720e8665d76fd`, two fresh
Doctor admission runs selected the same 52 `load_bootstrap_lock` and
`validate_bootstrap_lock` mutants (mutmut 3.8.1 and pytest 9.2.0).
The base caught 46 and missed six. The candidate catches all 52.
The added cases distinguish a missing section, a missing deployment
target and a rejected lock schema while preserving the file diagnostic.

Use the preceding Node recipe with this base, `only_mutate =
["buildsys/bootstrap.py"]`, `also_copy = ["build.py",
"bootstrap.lock.json", "sources.lock.json"]`, and pytest selection
`tests/test_controller.py -k test_doctor_rejects_malformed_lock_sections_before_inspecting_host`.
Run the two qualified function patterns and compare the resulting
`mutants/buildsys/bootstrap.py.meta` records. Both commands exited
zero within 120 seconds with the same generated production files.

The last assembly case also has a case-sensitive control. Copy an
exact archive of the checked revision into the pinned Alpine
container's own filesystem. Run
`python3 -m unittest tests.test_release.AssembleTest.test_assembly_lists_both_targets_and_all_checksum_assets`
using the unchanged controller files. Change only the
`assemble_all` lockfile string to `SOURCES.LOCK.JSON` and rerun
with a fresh `PYTHONPYCACHEPREFIX`. The control exits 1 with
`FileNotFoundError` for the uppercase lock path. This resolves the
single macOS casefold survivor from the 64-identity assembly scope.
No new native release ran.


**Native Node artifact trial**

[Run 44367665068](https://github.com/laputa-systems/node-build/actions/runs/44367665068)
qualified Node 26.12.1 on native x86-64 Linux musl and macOS ARM64.
The workflow at `8c99b76803902055cc891503a0451434e97b433a` used the
same build sources and lockfiles as `597add72e9b3ea144819bc751876f1b221f30c97`.
Reproduce with `make doctor`, `make build` and `make verify` for each
native `TARGET`, using the pinned Alpine and `xcode-27` environments
from [the trial](https://github.com/laputa-systems/node-build/pull/37).
Both targets passed all 18 smoke cases and the compressed and unpacked
size budgets. The archive digests were computed in the runner jobs.

| Target | Compressed bytes | Payload bytes | Archive SHA-256 |
| --- | ---: | ---: | --- |
| `x86_64-unknown-linux-musl` | 28,381,240 | 182,335,288 | `b7a0557ef6e36cceb28e503cc0989d9095758c309cebc50cc26b4fe545a5e13f` |
| `aarch64-apple-darwin` | 22,108,932 | 179,809,306 | `4841d975d30d30b25b2e823eef5e51a220f194177e90871300f3e26a264d5054` |

Linux took 1 h 54 min and macOS took 2 h 1 min including packaging and
verification. The earlier 100-minute attempts ended during V8 compilation.
The extended run sampled active compiler processes while the buffered
make log was unchanged, then completed both builds. DSLP-4 retains the
wider controller mutation and whole-change qualification.

**Archive budget boundary**

The `check-budgets` command now rejects string, null, Boolean and negative
byte ceilings through its exit 2 diagnostic. A real xz archive fixture
checks both exact limits, each exceeded limit, missing inputs and exclusion
of symlinks from payload size. The new CLI test failed against `cc0ca86`
before the fix.

With only the archive fixtures over `cc0ca86`, Mutmut 3.8.1 and pytest
9.2.0 caught 64 of 67 identities in `buildsys/budgets.py`. With the
validation fix and CLI test, the selection caught 78 of 81 identities.
The three surviving changes omit the default `tarfile.open` mode or
uppercase `dist` and `release-budgets.json` on the case-insensitive
macOS volume. The latter two remain distinguishable on a case-sensitive
filesystem.

Both uppercase changes failed the exact-ceiling fixture on an isolated
case-sensitive Linux ARM64 filesystem with Python 3.14.10 and the
Buildlib wheel verified against `uv.lock`. At `ff3448f` the unchanged
case passes. Independently change `"dist"` to `"DIST"` or
`"release-budgets.json"` to `"RELEASE-BUDGETS.JSON"` in
`buildsys/budgets.py`. Run
`python -B -m unittest tests.test_controller.ArchiveBudgetTest.test_archive_budget_accepts_exact_ceilings`
after each change. The cases report a missing archive and an unreadable
budget file respectively. All 81 outcomes in this scope are accounted
for across the two filesystems, including the equivalent default
tarfile mode.

To reproduce, archive the revision into a disposable directory under
`.work/tmp`. In that copy configure Mutmut with
`source_paths = ["buildsys/"]`, `only_mutate = ["buildsys/budgets.py"]`
and `pytest_add_cli_args_test_selection = ["tests/test_controller.py::ArchiveBudgetTest"]`.
Create `.work/tmp` inside the copy and run
`uvx --with laputa-buildlib==0.1.0 --with pytest==9.2.0 mutmut@3.8.1 run --max-children 1 'buildsys.budgets.*'`.
Read `exit_code_by_key` in `mutants/buildsys/budgets.py.meta`.

**Reference comparison boundaries**

`compare-reference` now identifies the binary when the version probe
cannot start or times out. A real non-executable reference file
reproduced an uncaught permission error at `e287fb4`. The CLI fixture
now checks exit 2 and the diagnostic. Separate executable fixtures
check version mismatch, nonzero status and explicit and PATH lookup.
Deterministic samples verify both probe orders and the persisted JSON.

The typed probe fields preserve the existing JSON report. Import
`_ProbeResult` in a scratch checker input and assign a scalar to
`candidate_ms` to reproduce the ty rejection. With the same
`buildsys/comparison.py` source and 177 generated keys, the comparison
suite moved from 118 to 132 catches. Use the archive budget mutation
recipe above with `only_mutate = ["buildsys/comparison.py"]`, the
locked Buildlib wheel, `tests/test_compare.py`, and selection
`buildsys.comparison.*`. The wider comparison scope remains open.

All 12 comparison cases, Ruff and ty passed. The full macOS suite
reported one host lock mismatch, reproduced at `e287fb4`. The host
has Xcode and SDK 27.2 against the locked Xcode 27.1 and SDK 27.0.

**Release controller inventory**

At `b9fc2374026027c77ec74c44a0ff825bad7ca372`, the full
`buildsys.release.*` selection caught 350 of 395 identities on native
macOS ARM64. The 41 survivors were in Git probes (31), record loading
(2), target validation (7) and multi-target assembly (1). The four
uncovered identities belonged to the unused single-target Python
wrapper. The CLI has called `assemble_all` for both the single-target
and default forms since `d294843`. The controller is an unpackaged
project and the wrapper had no callers in the tree. Removing it leaves
the 32 release cases passing, including standard assembly for one and
two targets, and Ruff and ty clean.

Reproduce the census with the preceding archive and locked Buildlib
wheel recipe. Set `only_mutate = ["buildsys/release.py"]`,
`also_copy = ["build.py", "bootstrap.lock.json", "sources.lock.json", ".github"]`,
and select `tests/test_release.py` and `buildsys.release.*`. Use Python
3.15.2, mutmut 3.8.1 and pytest 9.2.0 with one mutation worker. The
seven target-validation path variants and the one assembly lockfile
variant have the case-sensitive Linux controls documented above.
The remaining 33 outcomes in the Git probes and record loader stay
in DSLP-4.

`git rev-parse` and `git status` have a bounded timeout. At `f10806e`
both timeout controls escaped the assembly CLI as `TimeoutExpired`.
Now either stops assembly with exit 2 and the Git subcommand in the
diagnostic. No staging directory or new output is created. A normal
build records no checkout revision if either query cannot finish,
using the same fallback as for an unavailable checkout. Reproduce
with `python -m unittest tests.test_release.AssembleTest.test_git_probe_timeout_stops_assembly_and_leaves_build_provenance_unbound`.
All 33 release cases, Ruff and ty passed.

`assemble_all` now declares the three result fields used by the CLI.
The release directory stays a string, with ordered lists for targets
and assets. A scratch annotation using `AssemblyResult` rejects
`{"release_dir": "dist/release", "targets": 1, "assets": []}`
under `ty check`. The existing assembly cases still check asset names,
ordering and manifests. The 33 release cases and both linters passed.

The receipt reader now has a subprocess test with a C locale and
Python UTF-8 mode disabled. A UTF-8 receipt with a non-ASCII value
still loads. In a disposable source copy, omitting the explicit
encoding reproduces the ASCII decoding error. Python recognizes
`UTF-8` as the same codec as `utf-8`, which accounts for the other
record-loader survivor in the census above. A separate real Git
fixture truncates only its own temporary index. The failed status
query raises the assembly error and does not bind build provenance.
Removing the status check made that test fail. Run the
`ReleaseInputTest` cases to reproduce both controls. All 34 release
cases and both linters passed.

The Git probe tests now exercise an unborn checkout, a checkout path
containing a newline and a trailing space, a user preference that
hides untracked files, and the existing 60-second query deadline.
On macOS ARM64 the exact 92 query and record identities moved from
70 catches before #45 to 73 with #45 and 83 with these cases. No
previous catches were lost. The three runs used the same
`buildsys/release.py` and tests selected with
`-k 'ReleaseInputTest or git_probe_timeout'`.

Use the preceding archive recipe with the patterns for `_git_query`,
`git_revision`, `git_dirty`, `clean_build_revision` and `load_record`.
A separate `load_record` run used `LC_ALL=C PYTHONUTF8=0
PYTHONCOERCECLOCALE=0 PYTHONIOENCODING=utf-8`. It caught nine of ten,
including the omitted UTF-8 encoding. The remaining codec spelling
is equivalent. On case-sensitive Alpine 3.24.2 ARM64, Git 2.54.1
successfully ran `git rev-parse --show-toplevel HEAD` in an isolated
checkout and rejected `head`. The two `check` argument variants
match the subprocess default. The two `rstrip` variants remove the
same final newline after a hexadecimal revision. Two variants add
sentinel text to existing errors while preserving the error category
and message content. These account for all nine macOS survivors.

The full release module at `46c82f2658aa2fa5ed5cd6cc433108ae86a5bf96`
accounted for all 390 identities on both native ARM64 hosts. Ubuntu
caught 382 and macOS caught 373. The identity sets and generated spans
matched exactly. Linux caught the nine case variants documented above.
The eight shared survivors comprise five equivalent operations, two
diagnostic-only changes and the omitted UTF-8 encoding caught in the
C locale run. The release module's critical outcomes are dispositioned.

Reproduce with the [exact hosted workflow](https://github.com/laputa-systems/node-build/blob/7f389ca/.github/workflows/release-mutation-trial.yml)
at the recorded source. It uses Python 3.15.2, mutmut 3.8.1, pytest 9.2.0,
`tests/test_release.py` and one mutation worker. The pinned Buildlib
reader validates the full metadata and span sets. The job logs retain
both compressed sidecars and the named survivors.
[Native census](https://github.com/laputa-systems/node-build/actions/runs/44428020350)

The package installer now closes its output pipe before returning.
A real fixture child reproduced an open pipe after a successful
installation, a nonzero exit and a clean exit without an install
tree. The test checks the actual child exit, both output streams,
the staged bytes and preservation of a sibling stage file. The
process context owns pipe closure and reaps the child. Each of the
three cases now passes.

The hardening report fixture uses the existing synthetic ELF and
Mach-O files and exercises both report writers. It verifies relative
image paths, the declared target and a recorded hardening result
against the persisted document. It supplies the unsigned result
at the native signature-check boundary so the same fixture works on
Linux and macOS. The prior native artifact checks cover `codesign`.
All 36 release cases and both linters passed.

The first hosted package census found 113 no-test outcomes in the
two functions. The new local full-module census used Python 3.15.2,
mutmut 3.8.1 and pytest 9.2.0. It caught 217 of 309 identities
with all identities exercised. The installer implementation and
host differ between the runs. Reproduce with the preceding archive
recipe, changing the source to `buildsys/package.py`, selecting
`tests/test_release.py` and `tests/test_product.py`, and running
`buildsys.package.*`. DSLP-4 retains the 92 package survivors.

The native Linux input census selected `InputsTest`,
`ExtractedSourceTest`, `BuildReceiptTest`, and `PackageRecordTest`.
It accounted for all 49 identities with 29 catches. The runner
copies the scratch path and locked fixture files into each audit
workspace. Buildlib's reader rejected the earlier run's 23 no-test
results before the receipt-writing tests were included.
[Native input census](https://github.com/laputa-systems/node-build/actions/runs/44429877423)

The new output cases check a complete JSON receipt, a shorter rewrite
and extraction of an ordinary compressed directory into a missing
directory chain. The matched JSON selection moved from 11 to 20
catches of 23. The remaining encodings write the same ASCII JSON bytes
on the supported hosts. The nested extraction case also catches
all three changes that disable creation of destination parents.
Run the two new `InputsTest` methods directly. For mutmut use the
preceding archive recipe with `buildsys/inputs.py`, selecting the
receipt-writing tests and the two new methods.

The native ARM64 Linux and macOS input jobs used the same 49
identities and both caught 41 with identical outcomes. The three
`render_json` survivors (19, 21 and 23) select equivalent encodings
for the ASCII output of the JSON writer. In `extract_tar`, mutant 11
uses the default read mode, which follows the same compression
autodetection path. Mutants 22 and 24 use the Python 3.15.2 default
`data_filter`, verified by opening an empty archive under the
locked interpreter. Mutants 18 and 20 change only the diagnostic
text of the same rejection. The input scope is fully dispositioned.

The paired package jobs exercised the same 309 identities. Linux
caught 226 and macOS caught 217. The nine differences are changes
in path casing caught on the case-sensitive Linux filesystem.
These are `install_to_stage` 13 and 37 and `package` 10, 12, 53,
55, 67, 148 and 150. The 83 shared survivors still need dispositions.
The four jobs log the full result maps and source spans. Reproduce
from the exact proof revision, which adds the trial workflow to
the accepted source.
[Proof revision](https://github.com/laputa-systems/node-build/commit/61dea39cd67a41cfc6552889f6706c4b99475526)
· [Native input and package results](https://github.com/laputa-systems/node-build/actions/runs/44431737952)

The publication fixture checks receipt parsing, a missing or changed
installed binary and the persisted package record. A failed product
finding or a receipt edit during validation leaves the archive and
the package record unpublished. Both native jobs caught the same
23 additional identities among the original 309. Linux caught 249
and macOS caught 240. The nine path-case differences held, leaving
60 shared survivors. The Linux default tests and lint passed at
`5060d5c12e30257bbe7e9a780a68d1a4f4d27cda`.
[Publication cases](https://github.com/laputa-systems/node-build/pull/52)
· [Matched package jobs](https://github.com/laputa-systems/node-build/actions/runs/44433110100/attempts/1)

Both native budget jobs accounted for all 81 identities. Linux
caught 80 and macOS caught 78. The shared survivor is
`archive_payload_bytes` mutant 5. It omits the read mode, so
Python 3.15.2 uses the same compression autodetection. Linux catches
`check_budgets` 6 and 32 because the changed budget file and dist path
casing fails on its filesystem. The budget scope is dispositioned.
The first macOS budget attempt failed to resolve the mirror name.
The exact retry completed.

Both comparison jobs accounted for all 177 identities. Linux
caught 135 and macOS caught 132. The differences are casing changes
in the build and comparison directories and in the report filename
(`compare` 11, 13 and 138). The 42 shared survivors remain open.
[Budget and comparison results](https://github.com/laputa-systems/node-build/actions/runs/44433110100/attempts/2)

A local mixed-change control at `5060d5c1` used the pinned Buildlib
diff parser and result reader with Node's prototype selection. In
an archived checkout, remove
`test_git_probe_timeout_stops_assembly_and_leaves_build_provenance_unbound`
and split `targets.native_target` into a host lookup assigned to a
local followed by the same target conversion. Parse
`git diff --name-status -M -z HEAD` against the untouched fixture
commit. The test change adds `buildsys/release.py` to the changed
`buildsys/targets.py`. All 38 remaining ordinary release tests
passed. Using the release archive recipe above, run
`buildsys.release.x__git_query__mutmut_*` before and after the edit.
All 19 identities and spans matched. Five changed from caught to
surviving (5, 11, 14, 17 and 19), and the other outcomes held.
This exercises the release arm of the selection. DSLP-4 retains
the full changed-production policy and hosted verification.

The archive layout and epoch tests caught 294 of the same 309
package identities on Linux and 285 on macOS, with 45 additional
catches on each host. The installer encoding fix then changed
the production source. The new matching census has 315 identities.
Linux caught 305 and macOS caught 296. The same nine path-case
outcomes explain the platform difference.
[Archive layout results](https://github.com/laputa-systems/node-build/actions/runs/44435038022)
· [Installer fix](https://github.com/laputa-systems/node-build/pull/56)
· [Post-fix census](https://github.com/laputa-systems/node-build/actions/runs/44436014451)

All ten shared survivors in the post-fix run are in
`install_to_stage`. The ordinary nested-stage and C-locale test
passed in a fresh archive. Replacing the function body with each
rendered mutmut variant independently produced these results:

| Suffixes | Outcome |
| --- | --- |
| 4, 6, 8 | The controller cannot create the nested staging path. |
| 16, 19 | The log writer falls back to ASCII and raises `UnicodeEncodeError`. |
| 49, 50 | The installer inherits ASCII and the controller reports an installer failure. |
| 23, 52, 54 | Uppercase UTF-8 names resolve to the same codec. The fixture passes. |

Use the package archive recipe at `f04ca441590ef9b5ed6d7d92b2f066fc8911763d`.
Run `buildsys.package.x_install_to_stage__mutmut_*` and take each body
from `mutants/buildsys/package.py`. In a fresh archive for each body,
run `uv run --frozen python -B -m unittest tests.test_release.PackageStageTest.test_installer_creates_nested_stage_and_captures_utf8_under_c_locale -q`.
Run the unchanged body as the positive control. Isolate bytecode
caches between controls because the separate process imports the
edited file. The package scope is fully dispositioned.

The native target trial ran the constructor after initialization
and exercised omitted-target resolution with both released
baselines and the parked Linux ARM64 target. Both native jobs
accounted for 18 identities and caught 15. `target_for_triple`
3, 4 and 5 change only the wording of the same parked-target
diagnostic. The target scope is fully dispositioned.
[Target admission cases](https://github.com/laputa-systems/node-build/pull/53)
· [Native target results](https://github.com/laputa-systems/node-build/actions/runs/44434306494)

The paired comparison census at `33dce866` accounts for the same
177 identities and spans as the first trial. Linux caught 168 and
macOS caught 167. The work-directory fixture exercises both real
version probes and a second report write to the same path.

- `binary_version` 7 and 13 leave `subprocess.run` checking disabled.
- `compare` 34, 43, 44, 62, 71 and 72 change the candidate label.
  The worker sends the reference label to the reference executable
  and all other labels to the candidate. The recorded values and
  verdict ignore the sample labels.
- `compare` 129 changes the note's surrounding diagnostic text.
- `compare` 138 uppercases the report filename. The case-sensitive
  Linux fixture catches the change.

These dispositions complete the comparison scope. Reproduce with
the selected `tests/test_compare.py` archive recipe at the exact
proof revision. Its native jobs recorded both maps and all spans.
[Repeat-run cases](https://github.com/laputa-systems/node-build/pull/59)
· [Native comparison results](https://github.com/laputa-systems/node-build/actions/runs/44437652960)


#### Whole-change control and release recipes

The draft whole-change workflow qualified its planner and six controller
modules on Linux and macOS at `2a7e33877d7fdf151bc0de486e3d1138de05e249`.
All 12 shards passed. The verifier checks regular result files, source
digests and the rendered bodies of dispositioned mutations. Its test
deletion control changes a production target expression and removes the
release Git deadline test. Ordinary CI and lint passed. The other ten
mutation shards passed. The release shard reopened Git query variants
5, 11, 17 and 19 on Linux, and also 14 on macOS. Reproduce by checking out
the exact control revisions and running the draft workflow's matching
platform jobs. The whole-change lane still needs the remaining critical
modules in DSLP-4.
[Draft and controls](https://github.com/laputa-systems/node-build/pull/61) ·
[Positive run](https://github.com/laputa-systems/node-build/actions/runs/44442512453) ·
[Deletion run](https://github.com/laputa-systems/node-build/actions/runs/44443467063)

Both native target recipes now check the complete configure command,
CPU baseline flag, optimization and minimum platform. The focused
validation cases also check rejection of an unsupported target and the
diagnostics for missing fields, missing flags and banned flags.
Using the existing release mutation recipe on a fresh source archive
with mutmut 3.8.1, pytest 9.2.0 and CPython 3.15.2, select
`buildsys.product.*` and `buildsys.recipes.*` with `ProductTest`,
`RecipesTest`, `tests/test_release.py` and `tests/test_product.py`.
Both local arms have identical spans. Product caught all 25 identities.
Recipes went from 66 of 80 to all 80. The local full suite's only
failure is the recorded Xcode and SDK mismatch. Native CI uses the
locked host tools.

#### Qualification receipt

A real release-layout archive now exercises the qualification command
with fixtures at the native product inspection, smoke and relocation
boundaries. The fixtures check stale-work removal, the extracted binary,
archive digest, all three groups of findings, and a persisted failure
record before admission is refused. The rejected cases include missing
archives, absent binaries and concurrent findings from the three
checks. Qualification now leaves creation of the extraction destination
to its existing archive reader.

The selected qualification runner originally reported no tests
for all 195 identities. With the redundant creation removed and the
new fixture, the macOS selection caught 180 of the current 189.
Variants 36, 38 and 172 change path case and need the native Linux check.
Variants 65–70 change defaults of the smoke directory creation.
The archive reader already created the parent and the current
qualification has removed the previous work tree. Reproduce the local
selection with the release archive recipe, selecting
`buildsys.qualify_runner.*` and
`tests/test_product.py::QualificationReceiptTest`.

#### Reproduction receipts

The reproduction checks now retain two real-format binary fixtures and
verify the receipt digest, file size, paths, verdict and differing
chunk offsets. The cases cover identical output, changes confined to
Mach-O UUID or ELF build-ID metadata, and a content change. The ELF
case starts without a build tree. The existing-tree case verifies
cleanup between builds and preservation of unrelated target data.
The verdict no longer has an unused initial value.

The earlier selection caught 22 of 177 identities and marked the
other 155 as unexercised. The current source catches 170 of 174 on
macOS. All four survivors uppercase a path used by `wipe_tree`
(5, 7 and 12) or the receipt writer (`reproduce` 132). Repeat on native
Linux to check those variants on a case-sensitive filesystem. Use
the release archive recipe with `buildsys.reproduce.*`,
`tests/test_product.py::ReproduceReceiptTest` and
`tests/test_release.py::ReproduceDiffTest`.

#### Native toolchain probes

Fixture output now exercises the macOS and Linux command probes and
checks all reported toolchain and baseline fields. The tests cover
a failing command with plausible stdout, unparseable output, and musl
version output on either stream. They also check each diagnostic when
the host identity differs from the lock.

The earlier bootstrap selection caught 52 of 423 identities and marked
371 as unexercised. On the same source and spans, the fixture selection
caught all 423 locally. Use the release archive recipe with
`buildsys.bootstrap.*` and `tests/test_controller.py::BootstrapTest`,
excluding `test_lock_matches_host` from the mutation subprocess. The
ordinary controller still checks the real host where the locked native
toolchain is present. Both new checks and both linters passed.

#### Installed product inspection

Real-format ELF and Mach-O fixtures now check the staged installation.
The ELF case verifies required headers, the license, excluded tools
and the distinct results for embedded staging and source paths. The
Mach-O cases check architecture, target platform, minimum OS, PIE,
signature results and a relative library lookup. The installed-artifact
jobs above still exercise native signing and actual binary execution.

With the same 516 identities and spans, the earlier controller census
caught 156 and reported 118 unexercised identities. The new fixtures
exercise all 516 and catch 340. Run `buildsys.validate_product.*`
with the release archive recipe and `tests/test_product.py`,
`tests/test_elf.py` and `tests/test_release.py`. The 176 survivors
remain in DSLP-4. The new checks and both linters passed.

#### Relocation receipts

The relocation tests execute the copied program from ordinary paths
and paths with spaces. They verify materialization of a relative
settings link, preservation of an existing destination, embedded path
diagnostics, failed process output and both timeouts.

The matched current selection catches 104 of 111 identities. The
earlier selection caught two and marked 101 unexercised. Variants 4
and 7 of `copy_tree` preserve the symlink copy default. Variants 7
and 12 of `run_version` preserve subprocess error-checking behavior.
Variants 6 and 8 of `verify_relocation` uppercase an installed path
and need the case-sensitive Linux check. Variant 80 changes only the
diagnostic length. Run `buildsys.relocate.*` with
`tests/test_product.py::RelocateTest` and the release archive recipe.
All five focused tests and both linters passed.

#### Binary path policy

The path tests resolve references from their loading image and from
each executable directory. They check absolute paths inside the
installation and normalized system spellings. The native ELF allowlist
now uses its exact-name set directly. The Mach-O system path check
uses normalized equality because a trailing slash cannot survive
normalization at those prefixes.

The local selection catches 82 of the current 83 Mach-O path
identities and the single ELF policy identity. In
`rpath_directories` 22, the executable-path branch ignores the changed
image argument. Use the release archive recipe with
`buildsys.macho_paths.*`, `buildsys.elf_policy.*` and the matching
Mach-O, installed-product and ELF fixtures. All 19 focused checks
and both linters passed.

#### Architecture smoke probe

The architecture check now requires a successful subprocess exit
before accepting the reported identity. A real shell fixture prints
the expected Linux identity and exits 7. The previous check accepted
that output. The fixed check reports the exit and stderr, and the
matching successful probe still passes. A separate suite fixture
checks continuation after subprocess timeout, probe failure and an
unavailable addon compiler.

The focused `run_node`, `check_arch` and `run_suite` selection caught
103 of 143 identities with `tests/test_smoke.py`. The rest of the
smoke controller and focused survivors remain in DSLP-4. Both new
tests and both linters passed.


#### Inspector announcement deadline

A subprocess that wrote partial stderr and stayed alive held
`check_inspector` in a blocking read. A separate successful fixture showed
its child remained unreaped on return. Read only when the pipe is ready,
bound the announcement buffer and wait for the killed child on exit.

The fixtures exercise the written script, inspector arguments, partial
stderr, an announcement with or without a newline, an empty target
list, and invalid UTF-8 before EOF. All six smoke tests and lint
passed. A focused macOS ARM64 run using mutmut 3.8.1 and pytest 9.2.0
caught 72 of 90 inspector identities. The remaining 18 stay in
DSLP-4. Reuse the smoke recipe above with
`buildsys.smoke.x_check_inspector__mutmut_*`.



#### Inspector target-list decoding

The inspector child could return a malformed response that raised a
Python decoding or type error outside the smoke suite's failure
handling. The probe now reports malformed UTF-8, invalid JSON, and a
missing or unusable target ID as smoke failures. A real short-lived
fixture child exercises those responses and is reaped every time.
The fixtures failed on the prior decoder. Both linters and all 15 smoke
cases passed on the candidate.

#### Mach-O entrypoint kind

The installed-tree fixture names a Mach-O shared library `bin/node`
and supplies a separate valid executable. The old product check
accepted this layout. It now checks the kind of the named entrypoint.
Replacing that file with the executable makes the same fixture pass.

All 32 product tests and lint passed. The current archive selection
using the product and release suites caught 323 of 514 identities on
macOS ARM64. This scope includes 163 of 273 in `macho_tree_checks`.
The remaining identities stay under DSLP-4.


#### Configure receipt reuse

A matching receipt and a directory named `config.mk` previously
skipped configuration. Reuse now requires a generated file. The
real shell fixture checks the configure flags, deployment target,
working directory with spaces, the 600-second subprocess deadline,
captured diagnostics and receipt creation after success. The same
recipe fingerprint binds the canonical recipe and patch level.

All four focused tests and lint passed. The five-function selection
for configuration environment, marker, fingerprint, reuse, and
command caught 105 of 114 on macOS ARM64. The other nine stay in
DSLP-4. Reuse the controller mutation recipe with
`tests/test_controller.py::ConfigureMarkerTest`.


#### CLI target admission

Explicit unsupported targets now return status 2 and a stderr
diagnostic naming the command, option, and help invocation. Before
this change, six commands raised uncaught errors and two reported
unrelated missing inputs. The existing native target and job
defaults still reach the same controller calls. Assembly continues
to accept a comma-separated target list and rejects an unsupported
member before reading checkout state.

The ten command controls cover the parked Linux ARM64 spelling and
a mixed assembly list, with valid build and reproduction controls
for stdout and argument forwarding. All 51 focused tests and lint
passed.


The expanded CLI cases verify success and error streams for fetch,
package, qualification, assembly, published smoke, comparison and
budget checks. They also verify the default assembly set and the
controller test command's discovery and result status.

Across the same 381 identities at `44558734`, the matched controller
scope moves from 164 to 285 caught. The broader run retains 95
survivors and one timeout. The timed-out `main` variant 20
routes ordinary commands into controller discovery. Selecting
`tests/test_cli.py::ControllerTestCommandContract` alone caught
the same variant. The broader timeout remains distinct from
the test catches. All six CLI tests and lint passed.


#### Version, help, addon and excluded payload probes

The staged executable fixture exercises version and help content,
exit status, stderr, footer uniqueness, and completion output.
Native-addon fixtures verify both compiler argument sets, the
deadline, the generated load command and the compiler and load
failure paths. Either excluded executable fails admission.

The four selected functions caught 210 of 217 identities on
macOS ARM64 using `tests/test_smoke.py`. Seven variants change
path case, default Darwin spellings that take the same branch,
or the falsey default subprocess check. The native repeat
and wider smoke inventory stay under DSLP-4. All nine smoke
tests and lint passed.

The installed Node test smoke probe now requests the TAP reporter
and requires one exact passing-count line. At `0f016df9`, a local
process that returned zero caused the previous checker to accept
`# pass 10`, an unrelated line containing `pass 1`, and two
conflicting pass counts. The shell fixture now rejects each
output, checks the actual arguments, and requires zero exit status.

The locked Darwin ARM64 Node 26.12.1 binary at
`~/.local/share/nodejs/26.12.1-npm12.2.2-darwin-arm64/bin/node`
reported `v26.12.1` and passed the existing sample through the
candidate `check_node_test`. The new selection caught 28 of 29
`check_node_test` variants on macOS. Variant 16 changes the case
of the fixture directory name on this case-folded volume.
Select `tests/test_smoke.py::TestRunnerSmokeTest` with
mutmut 3.8.1 and pytest 9.2.0 in the controller archive.
All 11 focused smoke tests and both linters passed.

#### Worker and child smoke path

At `8cd5550f`, the pinned Darwin ARM64 Node 26.12.1 failed
the worker-and-child smoke probe with a JavaScript syntax error
when its staged path contained an apostrophe. A temporary
directory named with the prefix `owner's build ` and a symlink
to the installed Node binary reproduce the failure. The probe
now runs its child with Node's `process.execPath`. It passes
with the same path and binary.

All 12 focused smoke tests and both linters passed. The
controller fixture checks the generated command, the status,
and the required success evidence. It caught 27 of 65 variants.
Adding an isolated probe with the actual Node binary to the
same mutmut 3.8.1 and pytest 9.2.0 selection caught 62 of 65.
For the native repeat, run `check_workers_child` on that symlink
in each variant and set `CHECK_TIMEOUT` to 3 seconds. Variants
44 and 46 use the default text encoding, which writes the
same ASCII program on the supported hosts. Variant 48 uses
the equivalent `UTF-8` spelling.

#### Smoke runner process and suite outcomes

The process fixture verifies the child working directory, argument
boundaries, inherited environment, both streams, nonzero status and the
deadline. The architecture fixture checks its actual child arguments.
Suite fixtures verify default-target forwarding, successful addon
reporting, and bounded errors from both final checks. All 18 smoke
cases, the help-footer test, and both linters passed.

The controller has no callers of the internal `run_node` environment
override. Removing it lets the subprocess inherit the same environment.
On macOS ARM64 the added cases caught all 122 matched architecture and
suite variants, up from 92. On the changed process wrapper, 14 of 16
variants were caught. The two remaining variants replace `check=False`
with `None` or omit it. Both preserve nonzero result handling. The
selection used mutmut 3.8.1 and pytest 9.2.0.

#### Excluded payload directory entries

The published smoke and installed layout checks accepted an excluded
entry when its symlink target was missing. Both now check the directory
entry itself. On the previous source the fixtures accepted dangling
`bin/npm`, `bin/npx` and `lib/node_modules` links. The new checks reject
them alongside regular files. The layout fixtures also verify the
status and detail of valid required headers and absent payloads.

The native macOS ARM64 trial used mutmut 3.8.1 and pytest 9.2.0 with
`check_exclusions` and `validate_layout` selected. It caught 81 of 86
variants. Three change path case on this filesystem and two substitute
an equivalent falsey `follow_symlinks` value. All 12 smoke and 33 product
cases and both linters passed. The only full controller failure was
the local Xcode and SDK lock check, which also failed on the base.

#### Async filesystem readback

The async filesystem smoke previously accepted corrupted readback with
its original length. The Node child now emits the read bytes. The
controller compares them with the bytes written and requires zero exit.
The portable shell fixture checks matching data, wrong data of the same
length, and an error exit that prints matching data.

The pinned macOS ARM64 Node 26.12.1 rejected an equivalent-length fault
that the base accepted. Set `NODE_OPTIONS` to `--require=<fixture>` with
`require('node:fs/promises').readFile = async () => 'y'.repeat(1000)` and
run `check_fs_async` in fresh scratch. Remove the preload and repeat to
verify the written file contains 1,000 `x` bytes. The portable case and
native control together caught all 35 `check_fs_async` identities with
mutmut 3.8.1 and pytest 9.2.0. All 13 smoke cases and both linters passed.

#### HTTPS fixture path handling

The locked macOS ARM64 Node 26.12.1 reproduced a syntax error when the
HTTPS probe's fixture directory contained an apostrophe. The controller
now passes the key and certificate as separate Node arguments. A real
loopback probe passed with the original fixtures and with their symlinks
under an apostrophe-and-space directory. It still accepts the trusted
certificate and rejects the untrusted one. The portable cases check the
argument boundaries and refusal after a nonzero exit. All 20 smoke
cases and both linters passed.

#### Complete success lines in installed probes

Ten probes previously accepted a marker inside a longer line. The
fixtures reproduced acceptance of lines such as `did not report http
ok`. The probes now require a complete success line and a zero exit.
The fixtures cover output, child command and error detail. Startup has
a separate deterministic clock and status case. All 22 smoke cases and
both linters passed. All twelve selected native probes passed with
Node 26.12.1 and its shipped headers on macOS ARM64.

The full portable `buildsys/smoke.py` inventory using mutmut 3.8.1 and
pytest 9.2.0 at base `468d0761` reported 536 caught, 133 surviving, and
330 unexercised identities out of 999. With the new tests and marker
checks, all 999 ran. It caught 683 with 316 surviving and no timeouts.
The broader native script effects and survivor dispositions remain open.

## Tickets



### DSLP-4 · P2 · Tests: coverage, boundary gaps, mutation

- **Area:** deslop · tests
- **Where:** test suites and CI
- **Problem:** Coverage and several boundary selections are measured. Release, inputs, budgets, targets, package and comparison are dispositioned. The remaining controller scopes need their critical dispositions and the retained whole-change lane.
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
- **Where:** buildsys/node.py; buildsys/release.py
- **Problem:** The missing-type-argument candidate has open declarations in these modules. The comparison and assembly results have checked shapes and negative witnesses. Parsed release records and the build controller need separate evidence.
- **Recommendation:** Work one producer and its consumers at a time, preserve the accepted JSON forms and add a negative witness where precise types reject an actual bad program.
- **Fix with:** typing-audit
- **Effort:** M
