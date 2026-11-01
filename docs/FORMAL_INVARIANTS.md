# ThruBound — formal invariants (2026-10-31)

Nine properties, each with its assumptions and the **kind** of evidence behind it. **No machine-checked proof of the C code exists.**
- What is machine-checked: an **abstract model**, using SMT.
- What links the model to the code: **testing** (conformance, model checking, unit and property tests).
- What has been verified on chain: **nothing**.

## 1. Evidence kinds (never mixed)

| Kind | Artifact | What it establishes |
|---|---|---|
| **SMT proof (abstract model)** | `thru/proof/inductive_smt.py` (z3) | For **all** u64 values: every transition of the model preserves the invariant, and each property's obligation holds. 92/92 obligations as expected, including non-vacuity and 2 sanity counterexamples |
| **Conformance testing** | `thru/tests/test_model_conformance.py` | The C core (`fs_request`, `fs_approve`, `fs_reject`/`fs_expire`, `fs_agent_revoke`, `fs_agent_set`, called directly) agrees with the model's accept/refuse decision and every modelled field. 20,000 random boundary-biased trials, 0 disagreements. Catches 5/5 targeted C mutants |
| **Bounded model checking** | `thru/tests/model_check.py` | Every action sequence up to depth 6 (93,536 states) of the compiled program in the LOCAL SIMULATION, with tiny limits. No violation |
| **Unit, scenario, property, mutation tests** | `thru/tests/*`, `mutation_check.sh` | 77 Python tests (incl. conformance); property campaign 30×300; 19 of 20 mutants caught + 1 equivalent |
| **Independent verification** | `thru/verifier/verify_thru.py` | Re-derives the rules from raw events and account bytes (37 traces) |
| **On-chain test (alphanet)** | `.github/workflows/alphanet-e2e.yml`, `thru/network/alphanet-e2e.mjs` | 42/42 live checks on 2026-11-01 (`m2/thrubound-alphanet/`). Properties 1, 3, 4 and 6, the refusal paths, and the KSI-1 probes were exercised on the real VM and token program. These are examples on a real network, not a proof |

## 2. Assumptions

| # | Assumption | Status |
|---|---|---|
| H1 | A failed transaction changes nothing except the fee payer's nonce and fee | **Official docs** (Transaction Execution) |
| H2 | Transactions touching the same writable accounts take effect one after another | Not documented in the passages read; **unverified** |
| H3 | Block time never decreases | **Unverified** |
| H4 | Only the owning program writes its accounts; only it can authorise its PDAs | Official docs (Programs, invoke auth) and SDK |
| H5 | The token program's `transfer` moves exactly `amount` or fails; only the account authority can transfer, burn or close | Official docs for burn and freeze. **Alphanet probes (2026-11-01):** transfer, burn, close and freeze by non-authorities were refused, and the exact amounts arrived (5, 9, 100). Still not proven for every path (source not public) |
| H6 | The C code implements the model | **Tested** (conformance, mutation), not proved |

## 3. The model

**State.** Per agent:
- limits P, D, L, θ, expiry V;
- counters t (spent), r (reserved), d (today's use) with its day;
- nonce n, epoch e, active flag;
- one tracked request q (status, amount, nonce, epoch, day, expiry, binding fields);
- a ghost R, the sum of the open current-epoch requests;
- vault flags paused and killed, and `total_paid`.

All numbers are integers in [0, 2⁶⁴−1]. Checked additions become preconditions, exactly as in the C code.

**Transitions (12):**
- request: instant; pending creating q; pending creating another request;
- approve q; approve another request;
- reject or expire q; reject or expire another request;
- revoke;
- `SET_AGENT` (with CE-1);
- pause/unpause; kill;
- time passes (monotone).

**Invariant `Inv`:**
- configuration: 0 < P ≤ D ≤ L and θ ≤ P;
- **t + r ≤ L ∧ r = R**;
- an open current-epoch q is part of R;
- q's epoch ≤ e and q's nonce < n;
- day ≤ today, and **day = today ⇒ d ≤ D**;
- killed ⇒ paused;
- ranges.

**Second model, for properties 8 and 9.** Two agents share one vault, with balance B, funded F and withdrawn W, and invariant **B + t₁ + t₂ + W = F**, tᵢ ≤ Lᵢ. Payment, withdraw and failure transitions are atomic (H1).

## 4. The nine properties

| # | Property (directive §3) | Formal statement | SMT proof (model) | Conformance (C ↔ model) | Model check / tests |
|---|---|---|---|---|---|
| 1 | Spent never exceeds the budget | Inv ⇒ t ≤ L, preserved by all 12 transitions | ✔ | ✔ | S1; property P2/P12; scenarios |
| 2 | Reserved never exceeds the budget | Inv ⇒ r ≤ L (indeed t + r ≤ L) | ✔ | ✔ | S1, S3; P8 |
| 3 | A nonce cannot be used twice | n′ ≥ n for every transition; an accepted request has nonce = n and n′ = n + 1, so an accepted nonce is below every later n | ✔ | ✔ (n compared) | T12; `Replay`; verifier sequential nonces |
| 4 | A revoked agent cannot transact | Inv ∧ ¬active ⇒ ¬pre(request) ∧ ¬pre(approve) | ✔ | ✔ | T3/T11; `Revocation` |
| 5 | An expired permission cannot be used | now ≥ V ⇒ ¬pre(request) ∧ ¬pre(approve) | ✔ | ✔ | T4/T11; mutant `no_key_expiry` |
| 6 | Human approval is valid only for the exact request | pre(approve q) ⇒ all 8 bound fields equal | ✔ | ✔ (tampered approvals) | T13; `ApprovalBinding` |
| 7 | Pending requests cannot execute after revocation | stale (qe < e) stays stale in every transition, and stale ⇒ ¬pre(approve) | ✔ | ✔ | `RevocationDuringPending`; mutant `no_epoch_check` |
| 8 | Agents sharing a budget cannot exceed the total | t₁ + t₂ ≤ F and tᵢ ≤ Lᵢ, preserved | ✔ | — (two-agent model is separate) | `MultipleAgents`, `ConcurrentSpending` (all 6 orders) |
| 9 | Failure leaves accounting consistent | each transition: Δ(t₁ + t₂) = −ΔB − ΔW; failure is the identity (H1) | ✔ | ✔ (failed calls change no field) | `FailedTransfers`; model check 936 failed transfers, 0 inconsistencies |

**About property 8.** ThruBound has **no single cap shared by several agents**: each agent has its own lifetime budget, and the shared bound is the vault balance. If a shared cap across agents is required, it is not provided. A Rate Limiter GLOBAL bucket could provide one; composition is deferred (`PHASE6_INTEGRATION_REVIEW.md` §2).

## 5. Sanity: the proofs are not vacuous

- Each transition is enabled in some state satisfying Inv (12/12).
- Removing the CE-1 precondition from `SET_AGENT` makes the lifetime invariant fail: z3 returns a counterexample.
- Removing the epoch check from approval lets a stale request execute: counterexample.
- During development, z3 found a counterexample: a negative threshold input. It showed the model lacked the u64 input domain the C types impose. The model was corrected; this was not a code bug.

## 6. Reproduce

```bash
pip install z3-solver
python3 thru/proof/inductive_smt.py
cd thru/tests && FS_CONFORMANCE_TRIALS=20000 python3 -m unittest test_model_conformance
python3 model_check.py 6
```
