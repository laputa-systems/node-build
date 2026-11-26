Prefix: NODE
Next: 7

# Open work

### NODE-1 · P3 · Qualify remaining generic return and input shapes

- **Area:** types
- **Where:** buildsys/node.py; buildsys/release.py
- **Problem:** The missing-type-argument candidate has open declarations in these modules. The comparison and assembly results have checked shapes and negative witnesses. Parsed release records and the build controller need separate evidence.
- **Recommendation:** Work one producer and its consumers at a time, preserve the accepted JSON forms and add a negative witness where precise types reject an actual bad program.
- **Fix with:** typing-audit
- **Effort:** M

### NODE-2 · P3 · Cover representative runtime and build regressions

- **Area:** bench
- **Where:** buildsys/benchmarks.py; buildsys/comparison.py; docs/PERFORMANCE.md
- **Problem:** Unproven: five startup and synthetic JSON samples compare against upstream rather than an accepted prior build, and no build-time gate exists. User-visible regressions can be missed.
- **Recommendation:** Define representative completed-work runtime and native build comparisons against an accepted anchor, with variance and host validity before proposing gates.
- **Fix with:** refactor-benchmarks
- **Effort:** L

### NODE-3 · P3 · Add attribution and provenance for performance runs

- **Area:** bench
- **Where:** buildsys/comparison.py; buildsys/benchmarks.py; docs/PERFORMANCE.md
- **Problem:** Comparison records omit binary identities, host pressure and process-tree resource attribution. JSON timing has millisecond resolution, and fixed reference-first order can bias results.
- **Recommendation:** Record artifact identity and host conditions, balance order, and document separate CPU sampling, memory and I/O diagnostics with their overhead.
- **Fix with:** benchmark-checklist
- **Effort:** M

### NODE-4 · P3 · Verify benchmark input freshness and run isolation

- **Area:** bench
- **Where:** buildsys/bench.py; buildsys/comparison.py
- **Problem:** The driver warns but cannot establish archive and candidate freshness. The comparison harness reuses compare-work, and free space and leftover processes are not checked.
- **Recommendation:** Use existing receipts to verify inputs and add bounded disk and process checks without changing the comparison contract.
- **Fix with:** none
- **Effort:** M

## Decisions

### NODE-6 · Linux node is Alpine-only (2026-11-26)

Node-build publishes no `*-linux-gnu` target. The Linux builds require an Alpine (musl 1.2.6+) host; they are not a drop-in for glibc hosts. napi-rs addons that select their binding from the host libc load a GNU binding and cannot load into musl node, so workloads that need them (vite, vitest, oxlint) must run on Alpine. A glibc host with a distribution musl package can run addon-free workloads. The behavior is documented in [README.md](README.md#run-it).

`joshuarli/extensions` and `joshuarli/stats` keep their reasoned `setup-node` exemptions in stuff's `fleet/policy/owned-substitutes.toml`, reassessed only when those jobs run on a musl host.
