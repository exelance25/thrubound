# Changelog — Flowstate on Thru (`feature/thru-native-migration`)

## 2026-10-31 (Phase 7)

- **ThruBound Phase 7: community validation and network diagnostics.** No program, test, proof or SDK changes.
  - README rewritten for ThruBound; legacy README moved to `docs/legacy/`.
  - Community intro and technical Q&A drafts (not sent).
  - `thru/run_all_tests.sh` one-command runner with expected output; `docs/DEVELOPER_PACKAGE.md`.
  - Pinned evidence in `m2/thrubound-phase7/` (official binary rebuilt byte-identical; all suites rerun).
  - Read-only network diagnosis: Thru RPCs healthy from the user's network; both sandboxes blocked by proxy allowlists.
  - Report: `docs/PHASE7_COMMUNITY_VALIDATION.md`.

## 2026-10-30

- **ThruBound Phase 5 gate review** (branch `feature/thrubound`):
  - Gap review (seven questions).
  - Official Thru toolchain v0.4.2 build: reproducible, CLI image validation passed; not executed on ThruVM.
  - KSI-1 evidence and restricted trust model. On-chain check that the mint has no freeze authority (I-17).
  - `@thrubound/sdk` with a LOCAL SIMULATION transport, plus the independent app `examples/subscription-payer`.
  - Bounded model checking: depth 6, 93,536 states.
  - 13 named scenarios.
  - Verifier: aggregate checks.
  - Corrected mutation accounting: 18 caught + 1 equivalent. Earlier "all caught" claims were overstated.
  - Hand proofs in `INVARIANT_PROOF_REVIEW.md`.
  - One-page demo `thru/demo`.

- **Owner decisions D-12, D-13**: ThruBound option A (compose with Rate Limiter and Passkey Manager); CE-1 fixed. `SET_AGENT` refuses limits below what is used. New invariant I-16 / P12, functional test, verifier rule, 2 program mutants (18/18 caught). Fixed a harness bug where the budget scenario never ran. RISC-V hash `0bdd043f…`.

- **ThruBound gap analysis** (branch `feature/thrubound`): competitive analysis of Coinbase Agentic Wallets, Bursar (two projects), PayGuard, Accord, PolicyVault, Fiscus (not found) and Thru core programs (Rate Limiter, Passkey Manager); differentiation options A/B/C; draft product spec; migration matrix; counterexample CE-1 (`t ≤ L` breaks when the owner lowers limits).

- **PHASE 2 docs**: `THRU_ARCHITECTURE.md` (components, instruction set, EVM→Thru mapping), `THRU_ACCOUNT_MODEL.md` (byte layouts, seeds), `THRU_SECURITY_INVARIANTS.md` (I-1…I-15, KSI-1 Thru analogue, carried findings), `STATUS.md`, `TEST_REPORT.md`, `KNOWN_LIMITATIONS.md`, `DEPLOYMENT.md`; `.env.example`.
- `ef09399` **PHASE 3/6**: native C program (`thru/program`), vendored official C SDK, LOCAL SIMULATION (`thru/sim`), functional 29 / adversarial 28 / property campaign, program mutation check 16/16, independent verifier + 14 mutation tests. RISC-V build compiles (not executed on a Thru VM).
- `f112e11` **PHASE 0–1**: baseline report (legacy results reproduced in a clean clone), Thru compatibility record and decisions D-1…D-11. Network BLOCKED.

Legacy EVM history (M1 … MVP app) is on the original branches and in `STATUS.md` at the repository root.
