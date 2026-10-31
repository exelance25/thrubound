# ThruBound — product specification (DRAFT, 2026-10-30)

**Status: draft. Option A was chosen by the owner on 2026-10-30 (D-12).** The overall shape follows option A in `PRODUCT_DIFFERENTIATION.md` (compose with Thru's Rate Limiter and Passkey Manager, plus a thin extension program). Nothing in this document is implemented as ThruBound yet. The Flowstate program and tests on this branch are the starting point.

Working name: **ThruBound** (provisional; see the name check in `COMPETITIVE_ANALYSIS.md` §4).
Tagline: **"Give agents permission, not power."**

## 1. Problem

A developer wants an AI agent or external service to perform specific Thru actions, such as paying a vendor, without giving it a key that can do anything. They also need a checkable answer to the question "can anything else move these funds?"

## 2. Ten-second example

```ts
import { ThruBound } from "@thrubound/sdk";            // planned package; name unverified

const permission = await thrubound.grant({
  agent: agentAddress,
  token: testMint,                                        // test token only
  recipients: [vendorTokenAccount],
  perTransaction: 10_000_000n,                            // base units; integers only
  perPeriod: { amount: 50_000_000n, period: "utc-day" },
  lifetime: 200_000_000n,
  expiresIn: "7d",
  approvalAbove: 5_000_000n,                              // optional human approval (passkey)
});

const check = await thrubound.simulate(permission, { to: vendorTokenAccount, amount: 4_000_000n });
const receipt = await thrubound.request(permission, { to: vendorTokenAccount, amount: 4_000_000n, nonce });
const report = await thrubound.proofLab.confinement(permission);   // who else can move the funds?
```

**The SDK methods above are a design proposal. None of them exist yet.** Every underlying call must use real `@thru/sdk` and `@thru/programs` APIs; no API is invented.

## 3. Components

| Component | Scope | Built on |
|---|---|---|
| **ThruBound Core** | Thin extension program for what Thru core programs lack:<br>- expiry;<br>- shared multi-recipient allowlist;<br>- pending human approval bound to the exact payload;<br>- revocation epochs;<br>- strict nonces.<br>Funds are held by an account that only the policy path can authorize | Flowstate core (`thru/program/flowstate_core.c`), which already implements all of these in simulation. Downstream invocation through the token program, or through Rate Limiter CALL if verification (§7) allows |
| **ThruBound SDK** | Register a policy; grant, simulate, request, approve, revoke; read state; receipts | `@thru/sdk`, `@thru/programs` (ratelimit, passkey-manager, token), `@thru/passkey` |
| **ThruBound Proof Lab** | Invariant checker, state-transition simulator, property-based, adversarial and boundary tests, counterexample generation, reproducible reports, **authority-confinement analysis** | `thru/verifier`, `thru/tests` (existing) |
| Demo dashboard | Policies, active permissions, limits, remaining budgets, rejected and approved requests, receipts, security status | React. A demonstration only, not the product |
| Second application | A separate small app (e.g. a "subscription payer") that uses only the SDK | Proves reusability (directive §10.7) |

## 4. Mathematical rule (directive §5)

Symbols:
- P = per-transaction maximum;
- D = per-period maximum;
- L = lifetime maximum;
- d = spent in the current period;
- t = lifetime spent;
- x = requested amount.

All values are u64 base units with checked arithmetic and no floating point.

**Eligibility:**
- 0 < x
- x ≤ P
- x ≤ D − d
- x ≤ L − t
- the agent is authorized and unexpired, the recipient is allowed, the nonce is unused, the policy is neither paused nor revoked, and any required human authorization is valid.

**Success:** d′ = d + x, t′ = t + x. The policy update and the transfer happen in one transaction, so a failed transfer reverts both.

Mapping to the existing code:

| Symbol | Field |
|---|---|
| P | `per_tx` |
| D | `daily` |
| L | `budget` |
| d | `daily_used` |
| t | `spent` |

Pending approvals reserve `x` in `reserved`, so the code checks `t + reserved + x ≤ L`, which is stricter.

### CE-1: the invariant `t ≤ L` did not hold under owner reconfiguration (RESOLVED 2026-10-30, D-13)

The current program lets the owner lower L below t, and D below d. Counters are kept and further payments are refused. The literal invariant "0 ≤ t ≤ L" is therefore false in reachable states:
- in the 30 simulation traces, 8 agents end with `spent > budget`;
- 3 agents end with `daily_used > daily`;
- example: `seed-01`, agent `1a30d94f…`, spent 64,746,403 with budget 40,000,000.

No payment ever pushed t above the L in force at that moment; the verifier checks exactly that. **Decision needed before the proofs are written:**
- **(a)** refuse configurations with L < t or D < d, so the invariant holds as written; or
- **(b)** restate the invariant as "every payment satisfies t + x ≤ L at the moment it executes" (monotone safety), and show the remaining allowance as max(0, L − t).

**Resolution (owner decision, option a):** `SET_AGENT` now refuses `budget < spent + reserved` and, on the same UTC day, `daily < daily_used`. The invariant holds in every reachable state and is checked:
- after every step of the property campaign (P12; 231 refused lowering attempts, 0 accepted);
- by the independent verifier on every `AGENT_SET`;
- by a functional test;
- by two program mutants, both caught.

The pre-fix traces, which showed the counterexample, are superseded; their hashes are in `m2/thru-phase3/traces/all-traces.sha256`.

### Period source

Thru's documented clock is `block_time` (nanoseconds) in the block context, and the Rate Limiter uses slot or unix seconds. Flowstate uses the UTC day `block_time / 86,400 × 10⁹`. Known effect (BF2-2): up to 2·D around a period boundary.

## 5. Required security properties (directive §6)

These map to the Flowstate invariants in `THRU_SECURITY_INVARIANTS.md`.

| # | Property | Existing invariants and tests |
|---|---|---|
| 1 | per-tx limit | I-3 |
| 2 | period limit | I-4 |
| 3 | lifetime limit | I-5 |
| 4 | alternative transfer path | I-12 and KSI-1 analogue. **Open on a real network** |
| 5 | unauthorized CPI | I-12 (token program address check), reentrancy guard |
| 6, 7 | replay; approval reuse | I-6, I-9 |
| 8 | expiry | I-2 |
| 9 | revocation | I-10 |
| 10 | pause | I-11 |
| 11 | integer overflow | checked arithmetic; Overflow tests |
| 12 | concurrent spending | Concurrency tests; on Thru, transactions writing the same account are serialized, which is **unverified on a network** |
| 13 | unauthorized policy modification | I-1 |
| 14 | recorded spending equals transferred amount | I-14; verifier conservation |

**Authority-confinement test (to be designed in the Proof Lab).** For a protected token account, list every authority that the token program accepts for each instruction (transfer, burn, close_account, freeze_account), and show that each one resolves to the policy path. This needs the real token program behaviour (BLOCKED).

## 6. Non-goals

- A generic AI wallet dashboard.
- Custody.
- Mainnet without explicit approval.
- Real funds.
- USDC (the example uses a test mint).

## 7. Prerequisites (need a Thru network)

The five checks listed in `PRODUCT_DIFFERENTIATION.md` §5, plus deployment of the extension program and one end-to-end testnet flow verified against chain state.
