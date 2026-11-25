# Performance methodology

Compare against the trustworthy contemporary reference on the same native
machine: the official `node-v26.12.1-darwin-arm64` binary, same Node
version, workload, environment, and warmup. Control CPU baseline and
report the machine. On a busy host, interleave sides (A/B/A/B) and say so.

```sh
python3 build.py compare-reference --target aarch64-apple-darwin [--reference /path/to/node]
```

Defaults to `node` on `PATH`; refuses version mismatches. Minimum 5 runs
per side, alternating. Reports per-probe samples, median, spread, and one
verdict: faster, slower, no-measurable-difference, or inconclusive. A gap
inside the run-to-run spread is no measurable difference. Error counts and
output correctness are always checked; a fast wrong answer proves nothing.

## Measured results (2026-10-26, arm64, host-shared timing)

| Probe | Reference (median of 5) | Candidate (median of 5) | Verdict |
| --- | --- | --- | --- |
| Cold startup | ~30.1 ms | ~30.9 ms | no-measurable-difference |
| JSON parse/stringify (60× 500-item docs) | 2 ms | 2–3 ms | no-measurable-difference |

First-sample startup is dominated by page cache on both sides; steady-state
samples converge. No optimization is claimed and none gates the release:
PIE-vs-non-PIE stays an experimental comparison only, and non-PIE is never
published. Production PGO is deferred until it can be qualified.

## Measured results (2026-10-26, x86_64 musl, host-shared timing)

Reference is the system `node` v26.12.1 (musl-linked) on the same Alpine
host; candidate is the freshly packaged `bin/node`, 5 alternating runs.

| Probe | Reference (median of 5) | Candidate (median of 5) | Verdict |
| --- | --- | --- | --- |
| Cold startup | 15.3 ms (first sample 86.3 ms cold page cache) | 15.2 ms | no-measurable-difference |
| JSON parse/stringify (60× 500-item docs) | 7 ms | 7 ms | no-measurable-difference |

## Size

The ceilings in `release-budgets.json` (keyed by target under `targets`) were measured from
`release-934b31ca`, the first shared-format `.tar.xz` release, on 2026-11-13, with 15% headroom
rounded up to the next megabyte. macOS: 22,133,348 bytes compressed and 179,809,306 bytes of
installed payload. Linux: 28,388,152 bytes compressed and 182,331,192 bytes of installed payload.
The single `node` binary dominates both payloads. CI fails when a ceiling is exceeded, and a
human reviews whether the growth is justified.

## Benchmark entrypoint

`make bench` runs the full selected suite and is manual-only. It includes native
builds that take an estimated two hours per target. Use the locked environment
and select a smaller tier for iteration:

```sh
PATH="$PWD/.venv/bin:$PATH" make bench-list
PATH="$PWD/.venv/bin:$PATH" make bench-check
PATH="$PWD/.venv/bin:$PATH" make bench BENCH_ARGS='--tier edit --dry-run'
PATH="$PWD/.venv/bin:$PATH" make bench BENCH_ARGS='--tier edit'
PATH="$PWD/.venv/bin:$PATH" make bench-check BENCH_ARGS='--tier change --area size'
```

`--tier` is a ceiling: `edit`, `change`, `scenario`, or `full`. Repeat
`--workload NAME`, `--area AREA`, or `--skip NAME` to select or exclude names.
Name and area filters intersect. Unknown and empty selections fail. Unsupported
platforms and other exclusions are printed and recorded. `bench-check` defaults
to Edit; `bench` defaults to Full. Dry runs do not preflight or write files.

| Workloads | Tier and area | Purpose and estimated cost | Requirements | Output |
| --- | --- | --- | --- | --- |
| `harness-tests` | Edit, harness | Comparison and budget correctness, seconds | Locked Python environment | Run log |
| `size-darwin`, `size-musl`, `size-musl-arm64` | Change, size | Compressed and installed size, seconds | Target archive in `dist/` | Run log and size verdict |
| `compare-darwin`, `compare-musl`, `compare-musl-arm64` | Scenario, runtime | Five interleaved startup and JSON pairs, minutes | Native candidate and reference Node 26.12.1, `perf-gate-ready` | Run log and comparison record |
| `build-darwin`, `build-musl`, `build-musl-arm64` | Full, build | Native build and packaging elapsed time, two hours | Locked native toolchain, cached inputs, disk space, `perf-gate-ready` | Run log and build outputs |

`make bench-list` prints each exact command. A run writes logs and `summary.json`
to a dated directory in `.work/benchmark/`. A successful size check means the
archive is within the existing ceilings. Other completions are not performance
verdicts. The driver checks selected inputs before running any workload, warns
when artifact freshness is unknown, and checks the timing gate before and after
timed workloads. A failed post-check makes timing inconclusive. The comparison
harness also writes `build/<target>/compare-work/compare-record.json` and the
driver copies it into the run directory. Build outputs stay in `build/` and
`dist/`. Preflight does not verify free disk, stale processes, or artifact
provenance; inspect those before a long run.

The JSON probe uses `Date.now()` and validates 30,000 parsed items; startup
checks the process exit. Neither represents a complete application. The runtime
comparison uses an upstream reference rather than an accepted prior build. It
has no release timing gate. The size gate uses the archived file length and sum
of regular file sizes, not RAM. Build time has no budget or accepted baseline.
For diagnosis, use separate untimed `node --cpu-prof` runs and platform process,
memory, and I/O tools; their overhead and process coverage must be recorded.
