# Security review and pre-network fixes (2026-10-31) — evidence

All results here are LOCAL SIMULATION or static tools, except the read-only facts quoted from the official
Thru docs (thru.org/docs, read in the user's browser) and the official repository Unto-Labs/thru v0.4.3
(commit c7ed8d96, 2026-10-30, read-only clone).

| File | What |
|---|---|
| `flowstate_c.bin` | ThruVM binary, official toolchain v0.4.2 + C SDK v0.4.2, built twice, byte-identical: sha256 `e0843ea2ac3ef917b765df9f7c8d5706a1d9938888a1a0019bc4726809b127a6`, 27,616 bytes. Accepted by `validateManagerProgramImage` (`@thru/programs` 0.4.3) |
| `run_all_tests.txt`, `run_all_tests.log` | one-command run after the fixes: 11/11 PASS (77 Python tests, mutants 19 caught + 1 equivalent of 20) |
| `old-code-under-strict-sim.txt` | the pre-fix program (commit 2635ff7) under the stricter simulation: `FAILED (failures=31)` — the simulation now detects SR-1 |
| `source-sha256.txt` | hashes of the changed sources and of the alphanet test scripts |

Findings and conformance table: `docs/SECURITY_REVIEW.md`. Nothing here was executed on a Thru network.
