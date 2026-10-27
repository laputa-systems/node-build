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

macOS first qualified artifact: 44,023,851 bytes compressed, 179,704,746
bytes installed payload (dominated by the 118 MB binary). Linux first
qualified artifact: 55,278,558 bytes compressed, 190,965,048 bytes
installed payload (dominated by the 129.8 MB binary). Ceilings live in
`release-budgets.json` with ~28% headroom and are enforced in CI.
