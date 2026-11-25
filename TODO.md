Prefix: NODE
Next: 7

# Open work

### NODE-6 · P2 · Native addons cannot load under the musl Linux build on glibc hosts

- **Area:** Linux targets, compatibility
- **Where:** the `*-unknown-linux-musl` release targets; consumers' napi-rs addons (rolldown, oxlint)
- **Problem:** On a glibc host such as GitHub's Ubuntu runners, napi-rs loaders decide libc from the host (`/usr/bin/ldd`), pick the `*-linux-*-gnu` binding, and fail to load it into the musl node process (`Error loading shared library libgcc_s.so.1 ... rolldown-binding.linux-x64-gnu.node`). Installing both libc variants with pnpm does not help, because the loader never tries the musl binding. So vite, vitest and oxlint builds cannot use owned node on glibc runners (joshuarli/extensions#30 closed; reproduced for joshuarli/stats' statsctl build in ubuntu:24.04 with node 26.13.1 x86_64 musl). Packages that spawn a separate native executable, such as tsrs and esbuild, work.
- **Recommendation:** Decide between publishing a glibc-loadable Linux build (a `*-linux-gnu` target built against an old glibc baseline) and documenting musl node as Alpine-only; then remove the stats and extensions exemptions in stuff's `fleet/policy/owned-substitutes.toml`.
- **Fix with:** architect
- **Effort:** L

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
