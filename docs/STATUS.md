# Flowstate on Thru — status (2026-10-30)

## ThruBound — security review and alphanet preparation (2026-10-31, branch `feature/thrubound`)

- **Internal security review (not an audit):** `docs/SECURITY_REVIEW.md`.
  - **Critical functional bug fixed (SR-1):** accounts were resized before being made writable. The official rule says resize needs a writable account, so every account creation would have failed on a real VM. The simulation now enforces the rule.
  - **Invoke-target check hardened (SR-2):** token program index must name an existing PROGRAM account (official v0.4.3 guidance).
  - **Dependencies pinned (SR-3):** `@thru/*` 0.4.2, because v0.4.3 removed the Rate Limiter client.
- **Official facts newly verified from the docs:**
  - `block_time` is Unix nanoseconds.
  - The token transfer encoding is byte-identical to `@thru/programs`.
  - The program image passes the official validator.
  - **H2/H3 remain undocumented.**
- **Evidence:** `m2/thrubound-p8/`. New binary sha256 `e0843ea2…27a6`. 11/11 local check groups PASS; 77 Python tests; mutants 19 caught + 1 equivalent of 20.
- **Alphanet:** the test is written (`thru/network/alphanet-e2e.mjs`, GitHub Actions `alphanet-e2e`); **not run yet**.
  - The automation sandboxes cannot reach `*.thru.org`.
  - Artifact pages cannot call outside hosts.
  - The run needs push access to `exelance25/thrubound` so the workflow can execute on GitHub's network.

## ThruBound — Phase 7: community validation (2026-10-31, branch `feature/thrubound`)

Report: `docs/PHASE7_COMMUNITY_VALIDATION.md`. No feature changes.
- **Network:** the official RPCs (alphanet, betanet) are healthy and reachable from the user's own network (read-only gRPC-Web health checks in the browser). Both automation sandboxes block `*.thru.org` at their egress proxy (`blocked-by-allowlist`). **Nothing was deployed or sent.**
- **Evidence pinned:** `m2/thrubound-phase7/EVIDENCE_MANIFEST.md`. All 11 local check groups PASS; the official binary was rebuilt byte-identical.
- **Community:** README rewritten; drafts in `docs/community/` (not sent); developer package `docs/DEVELOPER_PACKAGE.md`.
- **Blocked on owner:** no public repository, no license chosen.

## ThruBound — Phase 6: integration and trust proof (2026-10-31, branch `feature/thrubound`)

Full review: `docs/PHASE6_INTEGRATION_REVIEW.md`. In this phase:
- the official Thru docs were read through the linked computer's browser;
- a real client bug was fixed: account lists must be sorted and without duplicates;
- the authority analyzer was added;
- the abstract model was proved with SMT and conformance-tested against the C code;
- the developer onboarding test was run (9 frictions, 6 fixed);
- demand was researched: **not validated**.

| Evidence level | Claims |
|---|---|
| Verified on a real Thru network | **none** (RPC unreachable from every environment; nothing deployed) |
| Verified with the official compiler and tools | ThruVM build with toolchain v0.4.2 is reproducible; the official CLI accepts the program image; the account-list rule and the atomicity rule are taken from the official docs |
| Verified in the local simulation | the whole permission flow; the SDK and two independent apps; 76 Python tests; model check depth 6; verifier 37/37; conformance 20,000 trials |
| Justified mathematically | 9 properties proved by SMT on the abstract model (92/92 obligations), with assumptions H1–H6 (`FORMAL_INVARIANTS.md`) |
| Not yet verified | KSI-1 on the real token program; passkey approval via `invoke`; Rate Limiter composition; H2/H3; deployment and upgrade authority; demand |



## ThruBound — Phase 5 gate review (2026-10-30, branch `feature/thrubound`, see `git log`)

| Area | What is actually complete | Only simulated | Validated with official Thru tools | Blocked |
|---|---|---|---|---|
| Product differentiation | `COMPETITIVE_GAP_REVIEW.md`: narrow but defensible (Thru-native allowance with verification included). Every individual feature exists elsewhere; Thru's Rate Limiter already is a generic gate. Demand unvalidated | — | — | Thru ecosystem review (`thru.org` unreachable) |
| Native program | C program with official SDK; all rules in the program | behaviour (LOCAL SIMULATION) | **compiles reproducibly with official toolchain v0.4.2 + release SDK; official CLI image validation accepts the `.bin`; ISA, ELF layout and imports match the official template** | execution on ThruVM, deployment |
| KSI-1 | evidence table and restricted trust model (`KSI1_THRU_TRUST_MODEL.md`); on-chain unfreezable-mint check (I-17) | direct-transfer refusals | burn/close/freeze authorities documented by official CLI help | on-chain confirmation; **KSI-1 OPEN** |
| SDK + independent app | `@thrubound/sdk` public API; `examples/subscription-payer` runs the 7 gate steps through it | all of it (only a simulation transport exists) | addresses via official `@thru/sdk` derivation | network transport, passkey approval |
| Verification | hand proofs with assumptions; bounded model check depth 6; 74 Python tests; mutation 18 caught + 1 equivalent; verifier 37/37; differential 3,000/3,000 | all executable evidence | — | testnet verification |
| Demo UI | see `thru/demo` (Phase 6) | yes | — | — |

**Acceptance criteria (ThruBound directive §12):**
- differentiation documented: **DONE**;
- program compiles: **DONE** (official toolchain);
- core permission flow: **SIMULATED**;
- SDK integrates with a separate app: **SIMULATED**;
- invariant proof or verification result for each: **DONE** (hand proofs + bounded checks, not formal);
- alternative routes tested: **PARTIAL** (transfer only, modelled);
- concurrency tested: **SIMULATED** (serial-effect assumption H2 unverified);
- passkey integrated: **NOT DONE**;
- testnet verified: **BLOCKED**;
- reproducible setup: **PARTIAL** (program build and local suites yes; network no);
- docs and demo: **DONE** (local).



> **2026-10-30, product direction override: "ThruBound".** The gap analysis found that Thru's core **Rate Limiter** program already provides a reusable native policy gate, so the generic "policy kernel" positioning is not defensible as written. The owner chose **option A (compose)** (D-12), and CE-1 was fixed by refusing limits below what is used (D-13). Details are in:
> - `docs/COMPETITIVE_ANALYSIS.md`
> - `docs/PRODUCT_DIFFERENTIATION.md`
> - `docs/THRUBOUND_PRODUCT_SPEC.md`
> - `docs/MIGRATION_MATRIX.md`
>
> Branch: `feature/thrubound`.


**Status words: PASS · FAIL · BLOCKED · NOT RUN · NOT REVIEWED · PARTIAL.** A passing test is not a security approval. **No audit, no formal verification.** No Thru network was reached, nothing was deployed, and no real funds, keys or signatures were used.

| | |
|---|---|
| Branch | `feature/thru-native-migration` (from `mvp-app` @ `14f1bf1`) |
| Legacy EVM code | untouched: `mvp-app` `14f1bf1`, `m2.0-m2.1` `b75807f`, `m1.1` `b248c50`, `master` `d64673d` |
| Commits on this branch | `f112e11` PHASE 0–1 · `ef09399` PHASE 3/6 program, simulation, tests, verifier · (this commit) PHASE 2 docs |
| Thru network | **BLOCKED**: `rpc.alphanet.thru.org`, `rpc.betanet.thru.org`, `grpc.thru.org`, `thru.org`, `scan.thru.org` refused from the cloud workspace and from the linked computer |

## Phases

| Phase | State | Evidence |
|---|---|---|
| 0 Recovery & baseline | **PASS** | `docs/THRU_MIGRATION_BASELINE.md`, `m2/thru-baseline/` |
| 1 Thru compatibility | **PARTIAL**: CLI and SDK installed and read; network, wallet, official toolchain BLOCKED | `docs/THRU_MIGRATION_DECISIONS.md`, `m2/thru-phase1/` |
| 2 Architecture docs | **PASS** (docs written) | `THRU_ARCHITECTURE.md`, `THRU_ACCOUNT_MODEL.md`, `THRU_SECURITY_INVARIANTS.md`, `THRU_MIGRATION_DECISIONS.md` |
| 3 Native program | **PARTIAL**: written, compiles for RISC-V, tested in LOCAL SIMULATION; **never executed on a Thru VM** | `thru/program/`, `m2/thru-phase3/` |
| 4 Token program integration | **PARTIAL**: CPI to the official `transfer` (tag 2) written to the source-documented ABI; tested only against a **model** | `thru/program/flowstate.c`, `thru/sim/sim.c` |
| 5 Web app (React + @thru/*) | **NOT RUN** (next) | — |
| 6 Security testing | **PASS in LOCAL SIMULATION** | `docs/TEST_REPORT.md` |
| 7 Testnet | **BLOCKED** (network unreachable) | `docs/DEPLOYMENT.md` |
| 8 Release | **NOT RUN** | — |

## Final acceptance criteria (directive §13)

| # | Criterion | State |
|---|---|---|
| 1 | Original project and Git history preserved | **PASS**: no branch rewritten; new work only on the migration branch |
| 2 | Native program compiles reproducibly | **PARTIAL**: compiles (`flowstate_c.bin`, sha256 `0bdd043f…`), but with gcc 13.2 / picolibc 1.8.6 instead of the official pinned toolchain (download BLOCKED), so not reproducible against the official toolchain |
| 3 | Vault creation works | **PARTIAL**: PASS in LOCAL SIMULATION; NOT RUN on Thru |
| 4 | Agent registration works | **PARTIAL**: same |
| 5 | Spending policies enforced on-chain | **PARTIAL**: enforced in program code; PASS in LOCAL SIMULATION; NOT RUN on Thru |
| 6 | Token transfer through the official Token Program | **INCOMPLETE**: CPI written to the documented ABI, tested against a model only |
| 7 | Human approval bound to the exact transaction | **PARTIAL**: all 8 fields bound and tested in simulation |
| 8 | Replay protection works | **PARTIAL**: PASS in simulation |
| 9 | Revocation and emergency pause work | **PARTIAL**: PASS in simulation |
| 10 | Independent verifier passes | **PASS** on 30 LOCAL SIMULATION traces; verifier mutation tests 15/15 |
| 11 | All required security tests pass | **PASS in simulation**: 58 unit + property campaign + 18/18 program mutants caught |
| 12 | React app interacts with the actual Thru test network | **INCOMPLETE / BLOCKED** |
| 13 | Real testnet transactions and balances independently verified | **INCOMPLETE / BLOCKED** |
| 14 | Setup and deployment instructions work from a clean environment | **NOT RUN** |

**The migration is not complete.** Criteria 6, 12, 13 and 14 are unmet; 2–5 and 7–9 hold only in simulation.

## What needs the user

Nothing to approve right now. To unblock criteria 6, 12 and 13, the work needs an environment that can reach a Thru test network (alphanet or betanet RPC). Possible routes, none taken yet: run the deployment steps from a computer whose network allows `*.thru.org`; or allowlist the Thru hosts for this workspace. Any testnet deployment will be announced before it happens; mainnet is out of scope without explicit approval.
