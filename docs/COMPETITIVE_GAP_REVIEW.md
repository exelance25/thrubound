# ThruBound — competitive gap review (Phase 5 gate, 2026-10-30)

Builds on `COMPETITIVE_ANALYSIS.md` (products, Thru core programs, sources) and `PRODUCT_DIFFERENTIATION.md` (gaps G-1 to G-6, decision D-12). No novelty is claimed for any single feature. Every statement about another product cites its source; anything not documented there is marked "not documented".

## Additional products reviewed in this round

| Product | Where enforcement happens | Relevant features | Source |
|---|---|---|---|
| **Squads v4 spending limits** (Solana) | Part of the Squads v4 program. The blog does not explicitly say "enforced on chain"; the program source has `spending_limit_use.rs` | Per-member allowance, one token per limit, destination list, monthly or "None" period | [Squads blog](https://squads.xyz/blog/spending-limits), [program source](https://docs.rs/squads-multisig-program/latest/src/squads_multisig_program/instructions/spending_limit_use.rs.html) |
| **ZeroDev permissions** (EVM smart accounts) | Plugins to the Kernel smart account (the page does not detail the enforcement mechanism) | "1 signer + N policies + 1 action"; call, rate-limit, timestamp, gas and signature policies | [ZeroDev docs](https://docs.zerodev.app/smart-accounts/permissions/intro) |
| **Turnkey agentic wallets** | Inside the secure enclave **before signing** (not on chain) | Recipient and contract/function conditions, human-plus-agent consensus, DENY circuit breaker | [Turnkey docs](https://docs.turnkey.com/features/policies/delegated-access/agentic-wallets) |

Together with Coinbase Agentic Wallets, Bursar, PolicyVault, Thru's Rate Limiter and Thru's Passkey Manager: **every individual ThruBound feature already exists somewhere.**

## The seven questions

### 1. What exact problem does ThruBound solve?

On Thru, a developer who wants an AI agent or service to spend a token on its own has two native options. Each leaves a gap:

- **A Passkey Manager authority** (session key with an expiry).
  - While valid, it has the wallet's **full** power: no amount, period or recipient limits (ABI).
- **A Rate Limiter policy.**
  - Low-level matcher configuration: byte offsets, selectors, exact-match account constraints.
  - **No expiry, no shared multi-recipient allowlist, no pending human approval.**
  - The developer must work out alone whether the protected funds can still move some other way.

ThruBound's narrowed problem statement:

> **Give an agent a bounded, expiring, revocable allowance over one Thru token (per-transaction, per-day and lifetime limits, a recipient list, optional human approval above a threshold), and get a checkable report of who else could move those funds.**

### 2. Who experiences it?

Developers of Thru applications that let software spend on a user's behalf: agent payments, subscriptions, API micropayments, bots.

**Honest caveat:** Thru is a young network. Its ecosystem could not be inspected from here (`thru.org` unreachable), and no user interviews were done. **Demand is unvalidated.**

### 3. How do they solve it today?

**On Thru:**
- hand-configured Rate Limiter policies;
- passkey session authorities;
- a custom program per application.

**Elsewhere:**
- custodial or enclave policy engines that check before signing (Turnkey, Coinbase);
- smart-account session-key policies (ZeroDev);
- on-chain spending limits (Squads, Bursar, PolicyVault).

### 4. Why are the existing Thru core programs insufficient?

From their official ABIs (implementation source not public):

| Need | Rate Limiter | Passkey Manager |
|---|---|---|
| Expiry | ✘ | per authority, but no limits |
| Several recipients sharing one budget | ✘ (exact-match constraints, ANDed) | ✘ |
| Pending human approval above a threshold, bound to the payload | ✘ | binds payload, no threshold or pending state |
| Revocation that cancels in-flight approvals | ✘ | ✘ |
| Report of other authorities over the funds | ✘ | ✘ |

They are insufficient **for this specific allowance shape**. They are not insufficient in general: the Rate Limiter is a good generic gate.

### 5. What does ThruBound add that is demonstrably different?

Only what can be shown today:

1. **One Thru-native program implementing the full allowance shape** above: expiry, a shared allowlist of 8, pending approval bound to 8 fields, revocation epochs, `t ≤ L` in every state.
   - Compiles with the **official** Thru toolchain.
   - Behaviour shown **in LOCAL SIMULATION only**.
2. **Verification shipped with the product (Proof Lab):**
   - an independent trace verifier;
   - property campaigns and bounded exhaustive exploration;
   - program mutation testing;
   - a confinement trust model (`KSI1_THRU_TRUST_MODEL.md`);
   - an on-chain-recorded "mint unfreezable" fact.

   Among the products reviewed, none documents this kind of verification kit or a confinement report.

What is **not** different: the policy features themselves (Bursar and Squads have most of them on other chains).

**Verdict:** the differentiation is **defensible but narrow**: "Thru-native allowance with verification included". Its value depends on Thru adoption, and the security claim stays conditional on KSI-1.

### 6. Can a completely independent Thru application integrate it?

**In LOCAL SIMULATION: yes.** `examples/subscription-payer` is a separate package. It depends only on the SDK's public entry point and the published ABI, and runs all seven gate steps (`SDK_INTEGRATION_GUIDE.md`).

**On a Thru network: not yet shown (BLOCKED).** The SDK has no network transport, because one could not be tested here.

### 7. What is the smallest useful product?

**"ThruBound Allowance" v0**, consisting of:
- the program;
- a TypeScript SDK with `createVault`, `grantAgent`, `request`, `approve`, `reject`, `revoke`, `pause`, `inspect`, `check`;
- `thrubound verify`, which runs the independent verifier and the confinement report.

There is no dashboard beyond a one-page demo.

Composition with the Rate Limiter (decision D-12) is **deferred** until its behaviour can be checked on a network. Until then the program holds funds itself through its vault address, which is the confinement design documented in `KSI1_THRU_TRUST_MODEL.md`.

**Release gate for v0:**
- the five network checks in `PRODUCT_DIFFERENTIATION.md` §5;
- the four KSI-1 checks;
- one finalized testnet deployment, verified against chain state.
