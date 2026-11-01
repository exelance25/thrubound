# ThruBound — invariant proof review (2026-10-30)

> **Update 2026-11-01:** the program has since run on the Thru **alphanet** (official-toolchain build, deploy, 42/42 live checks; `m2/thrubound-alphanet/EVIDENCE.md`). Statements below that say "BLOCKED", "not run on a network" or "local simulation only" describe the state on the date of this document.

This document states the spending invariants, gives a **hand-written inductive argument** for each, lists its **assumptions**, and maps each claim to the evidence that supports it.

**No formal verification has been done.** The arguments below are written by hand and have not been machine-checked. Historical Flowstate (EVM) results are not used here; they stay labelled historical in `THRU_MIGRATION_BASELINE.md`.

## 1. Kinds of evidence (kept strictly apart)

| Kind | What it is here | Strength and limits |
|---|---|---|
| **Mathematical proof (hand-written)** | Induction over the program's state transitions, §3 | Covers all values and all sequences, **if** the code matches the description and the assumptions hold. Not machine-checked |
| **Bounded model checking** | `thru/tests/model_check.py`: every action sequence up to depth 6, real compiled code, tiny limits (93,536 states, 364,305 transitions) | Exhaustive only within its bounds and action alphabet |
| **Property-based testing** | `test_properties.py`: 30 seeds × 300 random steps, 12 invariants after every step, coverage gates | Random, not exhaustive |
| **Unit and scenario tests** | functional 31, adversarial 29, scenarios 13 (74 Python tests incl. the property campaign), SDK 5 | Specific cases |
| **Mutation testing** | `mutation_check.sh`: 19 single-check removals; 18 caught by the suites, 1 equivalent (justified). The model checker alone catches 14 | Measures whether the tests notice a missing check |
| **Differential testing** | SDK `check()` (TypeScript) against the program (C) on 3,000 random requests: all agree | Checks the SDK model against the code |
| **Independent verification** | `verify_thru.py` re-derives every invariant from raw events and final account bytes, with its own decoder; 37 traces; 15 tamper tests | A second implementation, still within the simulation |
| **LOCAL SIMULATION** | Every executable item above: real program code, **modelled** Thru runtime and token program | Not a Thru VM |
| **Testnet verification** | none | **BLOCKED** |

## 2. Model and symbols

For one agent:
- **Limits:** P (per transaction), D (per UTC day), L (lifetime), θ (approval threshold).
- **Counters:** t (spent), r (reserved by pending requests), d (amount charged to the UTC day `day`).
- **Other state:** `nonce` (next expected nonce), e (epoch), `active`.

For the vault: flags (PAUSED, KILLED), and `total_paid`.

All values are u64. Every addition is checked (`add_ok`; overflow means the transaction fails). Time `now` is the block time, and `today = ⌊now / 86,400·10⁹⌋`.

### Assumptions (each proof states which ones it needs)

| # | Assumption | Basis |
|---|---|---|
| H1 | **Atomicity.** A transaction that fails (`tsdk_revert`, or a failed `tsys_invoke`) leaves no state change. The program writes its state before calling the token program, so this matters | SDK documentation; simulated, not observed on a VM |
| H2 | **Serial effect on shared accounts.** Two transactions that write the same agent or vault account take effect one after the other | Thru runtime behaviour, **unverified** |
| H3 | **Monotone time.** Block time never decreases | runtime, unverified |
| H4 | **Account integrity.** Only the ThruBound program writes its accounts, and only through the instructions below. Accounts at its derived addresses can only be created by it | SDK rules; checked by the program (owner, size, derivation) |
| H5 | **Token behaviour.** `transfer` moves exactly `amount` from source to destination, or fails | token ABI; simulation model; **unverified** |
| H6 | **Code matches description.** The transitions below are what `flowstate_core.c` and `flowstate.c` implement | by reading; and see the mutation and differential evidence |

## 3. Invariants and inductive arguments

### J (lifetime): `t + r ≤ L`, and `r = Σ{x : open request of the current epoch}`

This implies `t ≤ L` (directive §5).

*Base.* A new agent has t = r = 0 and L > 0 (configuration rule `0 < P ≤ D ≤ L`).

*Step.* Assume J holds before a successful transaction that touches the agent. Every successful transition preserves it:

| Transition | Precondition checked by the program | Effect | Why J still holds |
|---|---|---|---|
| `SET_AGENT` (existing) | **L′ ≥ t + r** (CE-1, D-13); `0 < P′ ≤ D′ ≤ L′` | t, r unchanged | t + r ≤ L′ |
| `REQUEST`, instant | t + r + x ≤ L | t′ = t + x | t′ + r ≤ L |
| `REQUEST`, pending | t + r + x ≤ L | r′ = r + x; a new open request of the current epoch | J holds for both parts |
| `APPROVE` | request open and `epoch == e`, so x is counted in r; t + r ≤ L | r′ = r − x, t′ = t + x | t′ + r′ = t + r ≤ L. The sum condition holds because the request is closed and removed from both sides |
| `REJECT` / `EXPIRE`, current epoch | request open | r′ = r − x (no underflow, since x is part of r by J) | t + r′ ≤ L |
| `REJECT` / `EXPIRE`, stale epoch | — | r unchanged | the request was not in the current-epoch sum |
| `REVOKE` | — | r′ = 0, e′ = e + 1; all open requests become stale | t ≤ L; sum = 0 = r′ |
| `PAUSE`, `KILL`, `WITHDRAW`, `SET_RECIPIENT`, other agents | — | t, r, L unchanged | trivially |

A failed transaction changes nothing (H1). Interleavings reduce to a serial order (H2). **∎ J**, under H1, H2, H4, H6.

Evidence: model check S1 and S3 (every reachable state up to depth 6); property P2, P8, P12; verifier (shadow replay plus aggregate "paid ≤ final budget"); mutants `no_budget`, `allow_budget_below_spent`, `revoke_keeps_reserved`, `release_double`, `no_epoch_check` all caught.

### K (period): `day = today ⇒ d ≤ D`

*Base.* d = 0.

*Step.*

| Transition | Rule | Effect |
|---|---|---|
| `REQUEST` | if `day ≠ today`, then d := 0 and day := today. Requires d + x ≤ D | d′ = d + x ≤ D |
| `APPROVE`, request made today | requires d ≤ D | d unchanged: x was charged at request time |
| `APPROVE`, request made on an earlier day | resets the day if needed; requires d + x ≤ D | charged to the execution day |
| release on the same day | — | d decreases |
| `SET_AGENT` | if day = today, requires D′ ≥ d (CE-1) | d unchanged |

Time only moves forward (H3), so a past day's d never becomes "today" again. **∎ K**, under H1 to H4 and H6.

**Caveat (BF2-2, kept).** K bounds each **UTC calendar day**, not every 24-hour window. Up to 2·D can pass across midnight. Scenario `PeriodRollover` demonstrates this on purpose.

Evidence: model check S2; property P3 and P12; scenarios `PeriodRollover`; mutants `no_daily`, `allow_daily_below_used` caught. `no_approve_daily` is **equivalent**: K makes the same-day check at approval unreachable. It is kept as defence in depth.

### Per-transaction: every executed payment has x ≤ P in force at that moment

`REQUEST` checks x ≤ P. `APPROVE` checks x ≤ P again, against the **current** limits (R-3). **∎** (H6)

Evidence: model check T5 and T10; property P4; mutant `no_per_tx` caught.

### Replay: each nonce is accepted at most once; each request executes at most once

`REQUEST` requires `nonce == next_nonce`, then sets `next_nonce += 1` (checked). `next_nonce` never decreases: no instruction lowers it, and `SET_AGENT` keeps it.

A request account's address is derived from (vault, agent, nonce), so it is unique per nonce. `APPROVE` requires status PENDING and sets EXECUTED. No transition returns a request to PENDING. **∎** (H1, H4, H6)

Evidence: model check T12; scenarios `DuplicatesAndRepeats`; verifier (sequential nonces, one payment per (agent, nonce)); mutant `no_nonce` caught.

### Approval binding

`APPROVE` succeeds only if the supplied approval equals the stored request in vault, agent, recipient, mint, amount, nonce and expiry, and `op = APPROVE`. The transfer uses the stored amount and recipient. **∎** (H6)

Evidence: adversarial `ApprovalBinding` (each field); model check T13; mutant `no_approval_binding` caught.

### Revocation, expiry, pause, kill

- **Revocation.** `REQUEST` requires `active`. `APPROVE` requires `active` and `epoch == e`. `REVOKE` sets active = 0 and e + 1. A re-grant keeps e, so old requests stay stale.
- **Expiry.** `REQUEST` and `APPROVE` require `now < valid_until`.
- **Pause and kill.** `REQUEST` and `APPROVE` require neither PAUSED nor KILLED.
- **Kill is irreversible.** Only `fs_set_paused`, `fs_kill` and `BIND_TOKEN` write flags. `fs_set_paused` refuses after KILLED. Nothing clears KILLED. **∎** (H6)

Evidence: model check T2, T3, T4, T9, T11, S8; scenarios `RevocationDuringPending`; mutants `no_key_expiry`, `unpause_after_kill`, `no_epoch_check` caught.

### Recorded = transferred, and conservation

Each `PAID` and `WITHDRAWN` event carries the same amount variable that is passed to the single `transfer` call. `total_paid` and t increase by the same x. If the transfer fails, the whole transaction fails (H1). Under H5:
- vault balance = funded − Σ PAID − Σ WITHDRAWN;
- no tokens are created or lost. **∎**

Evidence: model check S4 to S6; property P7 and P9; verifier conservation and per-account inflow; scenarios `FailedTransfers` (nothing consumed), `ConcurrentSpending`.

### Integer overflow

Every addition is `add_ok`. Subtractions are r − x (safe by J) and d − x (guarded by `d ≥ x`). **∎**

Evidence: scenarios `CounterOverflow` (nonce, epoch, spent and daily at 2⁶⁴ − 1 by state injection); adversarial `Overflow`.

### Concurrent spending

Under H2, concurrent transactions are equivalent to some serial order, and J, K and the replay result hold for every serial order.

Evidence: scenario `ConcurrentSpending` (all 6 approval orders, 3 agents, too few tokens); the model checker explores all interleavings of its actions. **H2 itself is unverified on Thru.**

## 4. What is not covered by any of this

- Authority confinement outside the program (KSI-1): only **assumed** (H5, A1 to A5 in `KSI1_THRU_TRUST_MODEL.md`).
- Thru VM execution (compute limits, real syscall error paths).
- Block ordering, fees, liveness.
- Clients (SDK, app). The program is the authority; clients can only cause refused transactions.
