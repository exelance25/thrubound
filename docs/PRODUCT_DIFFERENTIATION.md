# ThruBound — product differentiation (gap analysis, 2026-10-30)

> **Update 2026-11-01:** the program has since run on the Thru **alphanet** (official-toolchain build, deploy, 42/42 live checks; `m2/thrubound-alphanet/EVIDENCE.md`). Statements below that say "BLOCKED", "not run on a network" or "local simulation only" describe the state on the date of this document.

Based on `COMPETITIVE_ANALYSIS.md`. **Decision (owner, 2026-10-30): option A, compose** (`THRU_MIGRATION_DECISIONS.md` D-12).

## 1. What is not new

These features are documented in existing products and must not be presented as inventions:
- per-transaction, periodic and lifetime limits;
- expiry and recipient allowlists;
- approval thresholds;
- pause and on-chain enforcement.

Bursar (Robinhood Chain) already ships nearly all of them on a mainnet.

## 2. The stated differentiation does not hold as written

The directive's intended difference is "a reusable native Thru policy kernel, developer SDK and independent mathematical verification toolkit … reusable by unrelated Thru applications".

The first part is **already provided by Thru's own Rate Limiter**. It is a core program that:
- sits in front of any target program;
- enforces per-call amount caps and windowed amount and call quotas, per caller or account;
- pins accounts with constraints;
- can sign downstream calls with a policy authority PDA;
- is already used by the faucet.

Building a second generic gate would recreate core Thru functionality, which the directive forbids ("Do not recreate existing Thru core functionality unnecessarily").

## 3. Gaps that remain on Thru (from the official ABIs)

| # | Gap | Rate Limiter | Passkey Manager | Evidence |
|---|---|---|---|---|
| G-1 | Spending authority that **expires** | no expiry field | authorities expire, but have no limits | ABIs |
| G-2 | **Several allowed recipients sharing one budget** | constraints are exact-match, ANDed, max 4; one recipient per policy, and separate policies mean separate budgets | none | ratelimit ABI |
| G-3 | **Human approval above a threshold**, bound to the exact payload, with a pending state | none | binds exact payload, but has no threshold or pending state | ABIs |
| G-4 | **Revocation that kills in-flight approvals** | admin can pause or replace the config; no notion of pending items | REMOVE_AUTHORITY | ABIs |
| G-5 | **A verifiable answer to "who else can move these funds?"** (authority confinement) for a given token account and policy, before money is put in. Examples: a policy without a selector lets the PDA `burn`; a passkey session authority has full wallet power | no tool; implementation source not public | no tool | ABIs; no tool found |
| G-6 | **Agent-friendly delegation API**: "pay this vendor ≤ 10 per transaction, ≤ 50 per period, for 7 days" as one call, compiled to native primitives | low-level matcher configuration (offsets, selectors) | low-level | `@thru/programs` clients |

G-5 is the most defensible gap:
- it is narrow;
- it applies to Thru's own programs as well as ours;
- no comparable product publishes it;
- it answers the directive's central worry: "Do not confuse a correct mathematical policy with proof that every token transfer must obey it."

## 4. Options

| Option | What gets built | For | Against |
|---|---|---|---|
| **A. Compose (recommended)** | (1) **ThruBound SDK**: one-call delegation that compiles to Rate Limiter policies (quotas, per-call caps, recipient pinning, selector restricted to `transfer`) plus Passkey Manager (owner approval through passkey VALIDATE). (2) **Thin ThruBound extension program**, only for G-1 to G-4 (expiry, shared multi-recipient allowlist, pending approval, revocation epochs), reusing the existing Flowstate core. (3) **Proof Lab**: confinement checker and invariant verifier for any Rate Limiter, Passkey or ThruBound setup | Does not recreate core functionality; the differentiation (G-5, G-6) is real; reuses the tested Flowstate core | Depends on Rate Limiter behaviour that is only ABI-documented (source not public, network BLOCKED); composing two programs through CPI needs testing on a real network |
| B. Keep the own kernel | Flowstate program generalised into "ThruBound Core" with downstream invocation; SDK; Proof Lab | Fully under our control; already tested in simulation | Overlaps the core Rate Limiter; harder to justify to the Thru community |
| C. Verification-only | Proof Lab and SDK for existing Thru programs; no new on-chain program | Smallest, clearly unique | Leaves G-1 to G-4 unsolved; the product is not a full permission layer |

**Recommendation: A.** Position ThruBound as:

> *"Give agents permission, not power": a delegation SDK and confinement verifier for Thru's native permission primitives, with a small extension program for expiry, shared allowlists and human approval.*

## 5. Before building on A, verify (network needed)

1. Rate Limiter CALL behaviour with and without an ATTESTED rule: who may call?
2. Whether a token account owned by the Rate Limiter authority PDA can be moved only through CALL.
3. Whether a selector of `0x02` (transfer) blocks `burn` and `close_account` through the PDA.
4. Whether the token program's `burn`, `close_account` and `freeze_account` accept only the account owner or also the mint authority.
5. Whether the extension program can be the sole attester, i.e. whether a program PDA in an invoke auth list satisfies "attester must be authorized".

Until these are checked on a Thru network, no "secure" claim is made. This follows the directive: "Do not market it as secure until that issue is resolved."
