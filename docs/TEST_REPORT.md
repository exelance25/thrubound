# Flowstate on Thru — test report (2026-10-30)

## Update 2026-11-01: alphanet live test

| Check | Where | Result |
|---|---|---|
| Official-toolchain build on GitHub, byte-identical to the pinned hash | `alphanet-e2e` workflow | **PASS** |
| Deploy + ThruBound flows + refusals + KSI-1 probes | Thru alphanet, real transactions | **PASS 42/42** (`m2/thrubound-alphanet/EVIDENCE.md`) |
| Local suites (77 Python tests, verifier, model check, SMT, 20 mutants) | GitHub `ci` workflow and locally | **PASS** |

Rows below marked "NOT RUN / BLOCKED" for network execution are earlier, dated results.

**Everything in this report ran in a LOCAL SIMULATION**: the real program sources (`flowstate_core.c`, `flowstate.c`) compiled for the host and linked against `thru/sim/` (a host implementation of the Thru SDK syscalls used, and a model of the token program's `transfer`). **No Thru VM, no Thru network, no real tokens.** No audit or formal verification has been performed.

Environment: Linux x86-64, Python 3.13.16, gcc 13.3.0 with `-Wall -Wextra -Wconversion -Werror -fsanitize=undefined -fno-sanitize-recover=all`; RISC-V build with riscv64-unknown-elf-gcc 13.2.0. Raw outputs: `m2/thru-phase3/`.


## Current results — ThruBound Phase 5 gate (2026-10-30, branch `feature/thrubound`)

Everything executable below ran in the **LOCAL SIMULATION**, except the RISC-V build and the CLI image check, which used **official Thru tools**. Raw outputs are in `m2/thrubound-p2/` (official toolchain) and `m2/thrubound-p5/` (everything else). **No Thru VM, no network, no real tokens.**

| Suite | Result |
|---|---|
| RISC-V build, **official toolchain** v0.4.2 (gcc 15.2.0) + release C SDK | **PASS (compile)**: `flowstate_c.bin` 27,584 B, sha256 `4f49941902c4a1e0…`; two builds identical |
| Official `thru` CLI 0.4.2 local program-image validation | **PASS (format only)**: accepted, stopped at the intentionally unreachable RPC; `.elf` and random bytes rejected |
| Python: functional 31, adversarial 29, property campaign 1 (30×300, P1–P12, coverage gates), scenarios 13 | **PASS 74/74** |
| Bounded model check, depth 6 (real code, tiny limits) | **PASS**: 93,536 states, 364,305 transitions, 0 violations |
| Program mutation check (19 mutants, full 30-seed campaign) | **18 caught + 1 equivalent** (`no_approve_daily`, dead under I-16, argued in `INVARIANT_PROOF_REVIEW.md`) |
| Same mutants judged by the model checker alone | 14 caught; the other 5 are outside its action alphabet (account substitution, freeze check) or equivalent |
| Independent verifier | **PASS 37/37** traces (30 property + 7 scenario) |
| Verifier tamper tests | **PASS 15/15** |
| SDK (`thru/sdk`): public surface, official address derivation, full flow, authorization, differential 3,000 requests | **PASS 5/5** |
| Independent app `examples/subscription-payer` (7 gate steps) + verifier on its trace | **PASS** |
| Execution on a Thru VM / testnet | **NOT RUN / BLOCKED** |

**Correction to earlier reports.** The reports of 16/16, 18/18 and 19/19 mutants caught were overstated. The mutation check ran a reduced 10-seed property campaign, and two mutants (`no_owner_check`, `no_approve_daily`) were counted as caught only because that campaign failed a **coverage gate**. A coverage failure does not detect anything.

What changed:
- The check now runs the full campaign and labels coverage-only failures as NOT DETECTED (`m2/thrubound-p5/program-mutations-before-fix.txt` shows the miss).
- A new test (forged read-only vault) catches `no_owner_check`.
- `no_approve_daily` is equivalent and documented as such.

**Bugs found in this round** (all in tests or tooling, none in the program):
- the scenario harness compared a tuple with 0;
- some tests assumed `flags == 0` means "live";
- the SDK trace writer lost precision on nanosecond timestamps (> 2⁵³).

## Earlier runs (kept for the record)

## Summary

| Suite | Command (from `thru/`) | Result |
|---|---|---|
| Host build | `bash build_host.sh` | **PASS** |
| RISC-V build (official SDK make rules) | `cd program && make` (see `DEPLOYMENT.md`) | **PASS (compile only)**: `flowstate_c.bin` 26,680 B, sha256 `0bdd043fb5d373dd5d6f0f73267b660785bb2ce9b327e121be39e44f4c6b704e` (after CE-1; the earlier build was `bd18a92f…`, 26,392 B) |
| Functional | `cd tests && python3 -m unittest test_functional` | **PASS 30/30** |
| Adversarial | `python3 -m unittest test_adversarial` | **PASS 28/28** |
| Property campaign (30 seeds × 300 steps, 11 invariants, coverage gates ≥ 20) | `python3 -m unittest test_properties` | **PASS**, 0 violations |
| Program mutation check (18 mutants, each removes one security check) | `bash tests/mutation_check.sh` | **PASS 18/18 caught** |
| Independent verifier on 30 traces | `python3 verifier/verify_thru.py` | **PASS 30/30** |
| Verifier mutation tests (14 tamperings + clean) | `cd verifier && python3 -m unittest test_verifier` | **PASS 15/15** |
| Execution on a Thru VM | — | **NOT RUN** (no VM available) |
| Testnet transactions | — | **BLOCKED** |

## Update 2026-10-30: CE-1 fix (owner decision D-13)

`SET_AGENT` refuses limits below what is already used. Added:
- functional test `test_ce1_limits_cannot_drop_below_used`;
- property invariant P12, checked after **every** step (global checks used to run every 10 steps);
- boundary-value and budget scenarios, plus 231 refused lowering attempts (gate: no lowering may succeed);
- a verifier rule on every `AGENT_SET`, with a verifier mutation;
- two program mutants.

While adding the budget scenario, a harness bug was found and fixed: a tuple was compared with `0`, so the scenario never ran. Coverage after the fix: budget blocks 95, daily blocks 68, approved payments 114, instant 266. Evidence: `m2/thrubound-ce1/`.

## Functional (30)

VaultCreation, AgentRegistration, Payments (instant and pending), Approval, Limits (per-tx, daily, budget), Expiry, Allowlist, Revocation, PauseKill.

## Adversarial (28)

| Class | What is tried |
|---|---|
| Replay | reused nonce, skipped nonce, re-execution of an executed request |
| UnauthorizedAgent | unknown key, revoked agent, expired key, agent using another agent's account |
| UnauthorizedOwner | attacker as owner for every owner-only op; owner key not authorized (not the signer) |
| WrongTokenAndRecipient | other mint, unbound token account, unlisted recipient |
| ApprovalBinding | each of vault, agent, recipient, mint, amount, nonce, expiry, op changed one at a time |
| Concurrency | two requests racing the budget; approve after reject; double approve |
| Overflow | u64-max amounts and limits |
| AlternateTransferRoutes | direct token `transfer` from the vault token account by attacker, agent and owner |
| AccountSubstitution | foreign-owned, wrong-size and wrongly-derived vault/agent/request accounts |
| PauseAndRevocationBypass | requests and approvals while paused/killed; approving a pre-revocation request |

Every negative test also checks that no state changed.

## Property campaign

Invariants P1–P11: spent ≤ budget at acceptance, reserved = sum of open current-epoch requests, nonces unique and increasing, no payment while paused/killed/revoked, approved payments match their request, request closes once, conservation (P9), failed transactions change nothing, and more (`thru/tests/test_properties.py` header).

Coverage over 30 seeds (all gates ≥ 20): instant payments 211, approved 83, per-tx blocks 102, daily blocks 23, budget blocks 63, bad nonce 85, stale approvals blocked 63, expired-key blocks 583, paused blocks 648, allowlist blocks 177, wrong token 86, approval mismatch 100, unauthorized 503, direct transfers refused 260, expired/stale closes 95, rejections 90.

## Program mutation check (18/18 caught: OVERSTATED, see the correction above)

core: `no_per_tx`, `no_daily`, `no_budget`, `no_nonce`, `no_recipient_check`, `no_key_expiry`, `no_epoch_check`, `no_approval_binding`, `no_approve_daily`, `revoke_keeps_reserved`, `release_double`, `unpause_after_kill`, `allow_budget_below_spent`, `allow_daily_below_used`. adapter: `no_signer_auth`, `no_token_program_check`, `no_vault_token_check`, `no_owner_check`.

## Independent verifier

`thru/verifier/verify_thru.py` imports nothing from the tests or the program. It decodes raw event bytes with its own layouts, replays them through its own state machine and checks: failed transactions emit nothing; one event per success of the right kind; owner-only ops signed by the owner; nonces strictly sequential; every approved payment executes exactly one open, current-epoch, unexpired request with the same recipient and amount; no payment while paused/killed/revoked or with an expired key; per-tx, daily and budget limits; allowlist; kill irreversible; and at the end, token conservation, per-account balances explained by events, every agent field, and every request account's on-chain status.

Totals over 30 traces (after CE-1): 7,604 transactions (2,609 succeeded, 4,995 refused), 266 instant and 114 approved payments, 360 requests, 215 closures. Earlier run (before CE-1): 7,325 transactions.

Mutation tests (each must be flagged): inflated amount, replayed nonce, double execution, payment while paused, payment by a revoked agent, failed transaction keeping effects, dropped rejection, agent self-approval, unlisted recipient, tokens from nowhere, vault drained, unpause after kill, tampered snapshot, limit lowered below spent (CE-1).

**Found and fixed during this phase:** (1) the verifier first treated `REJECT` as owner-only; the program intentionally lets an agent cancel its own request, so the verifier rule was corrected to "owner or that request's agent" and still checks it. (2) A dropped rejection of a stale request was not detectable from agent counters alone; the trace snapshot now includes the raw request accounts and the verifier reconciles every request's status.

## Not covered

Thru VM execution (compute limits, real syscall error codes, account proofs), the real token program, network ordering, fees, the wallet, the indexer, and the web app (not written yet).
