# ThruBound

**Give agents permission, not power.**

ThruBound is a research prototype of a Thru-native program and TypeScript SDK. It lets an owner give an AI agent (or any automated key) a **bounded token allowance** instead of wallet access.

> **Status: v0.1.0-alpha research prototype, LOCAL SIMULATION only. Not ready for production.**
> - Not deployed on any Thru network. No transaction has ever been sent.
> - The program compiles reproducibly with the official Thru toolchain v0.4.2, but **has never executed on a Thru VM**.
> - Not audited. Not formally verified.
> - Do not use with real funds.

## What it does

An owner creates a **vault** that holds one token (Thru token program) and grants each agent:
- a per-payment limit, a daily limit (UTC calendar day) and a lifetime budget;
- an expiry;
- a recipient allowlist (up to 8 addresses);
- an approval threshold. Above it, a payment is **reserved** and waits for the owner. The owner's approval is bound to exactly 8 fields: vault, agent, recipient, token, amount, nonce, expiry, operation.
- a strict nonce, so a request cannot be replayed or skipped.

The owner can revoke an agent, which also invalidates its pending requests (epochs). The owner can also pause, kill and withdraw.

Limits cannot be lowered below what has already been used: such a change is refused. **All rules are enforced by the on-chain program, not by the SDK.**

It also ships an **authority analyzer**. For a vault, a plain token account or a (legacy, v0.4.2) Rate Limiter policy, it reports who else could move the funds:
- **VERIFIED** only from official sources or real chain data;
- **UNVERIFIED** for simulated data or assumptions;
- **RISK** for anything unreadable or dangerous.

## What it does not do

- **It is not a replacement for Thru's Rate Limiter or Passkey Manager.**
  - The **Rate Limiter** was Thru's generic, windowed policy gate for arbitrary program calls. Thru's official v0.4.3 release (2026-10-30) removed it from the official SDKs; its future on the networks is not documented. ThruBound covers token transfers only and does not try to replace a generic call gate.
  - The **Passkey Manager** is the intended way for an owner to approve, via its `invoke` path. That path is designed but has **not** been executed.
- It does not limit **native THRU** (fees or native transfers), only token-program tokens. One token per vault.
- It does not schedule payments. The agent triggers them.
- It has no single cap shared by several agents. The shared bound is the vault balance.
- It does not protect against a compromised **owner** key; the owner can withdraw everything.
- **Network:** the SDK has no Thru network transport yet, only the local simulation.

## Limitations and open risks

- **KSI-1 (open):** if the real token program allowed any path that moves, burns or closes the vault's token account without ThruBound, the limits would be bypassed. Official docs and CLI help support the expected authority rules, but the behaviour has not been tested on chain.
- **Assumptions:**
  - **H2 (unverified):** transactions on the same accounts take effect serially.
  - **H3 (unverified):** block time never decreases.
- **Upgrade authority:** a deployed program would need to be finalized or its upgrade authority disclosed.
- **Daily limit around midnight:** up to 2× daily can pass around 00:00 UTC (calendar day, by design).
- **Program addresses:** token and Passkey Manager (wallet) addresses come from the official SDKs. The docs say they target an upcoming Alphanet reset.

Full lists: [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md), [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## How it was checked — and what that means

| Kind of evidence | Result | What it does **not** show |
|---|---|---|
| Official toolchain v0.4.2 build | reproducible binary, sha256 `e0843ea2…27a6`; accepted by the official image validator (`validateManagerProgramImage`, `@thru/programs` 0.4.3); earlier builds also passed the official CLI's image check | that it runs correctly on a Thru VM |
| Local simulation: the same C program compiled for x86-64 inside a model of the Thru runtime and token program | 77 Python tests, 12 SDK tests, verifier 37/37, model check depth 6 (93,536 states), 19 of 20 mutants caught + 1 equivalent | real network behaviour; the token program is a **model** |
| SMT (z3) on an **abstract model** | 92/92 obligations, 9 properties (no overspend, no replay, revoke and expiry hold, exact approval binding, failure consistency) | a proof of the C code. The model↔C link is **testing** (20,000 conformance trials, 0 disagreements) |
| Thru network | **none.** Read-only health checks only (Phase 7) | — |

An internal security review (not an audit) found and fixed one critical functional bug: accounts were resized before being made writable, which a real Thru VM rejects. See [`docs/SECURITY_REVIEW.md`](docs/SECURITY_REVIEW.md).

**Test results are not network verification.** Details and assumptions: [`docs/FORMAL_INVARIANTS.md`](docs/FORMAL_INVARIANTS.md) and [`m2/thrubound-phase7/EVIDENCE_MANIFEST.md`](m2/thrubound-phase7/EVIDENCE_MANIFEST.md).

## Try it (Linux or WSL2; Windows native unsupported)

```bash
bash thru/run_all_tests.sh                 # every check, about 4-5 minutes
cd examples/subscription-payer && npm start   # the example app (after the line above)
cd thru/demo && npm start                  # demo page on http://127.0.0.1:3100
```

Prerequisites, WSL steps and expected output: [`docs/DEVELOPER_PACKAGE.md`](docs/DEVELOPER_PACKAGE.md). SDK usage: [`docs/SDK_INTEGRATION_GUIDE.md`](docs/SDK_INTEGRATION_GUIDE.md).

## Repository map

| Path | What |
|---|---|
| `thru/program/` | the ThruBound program (C, official Thru C SDK v0.4.2) |
| `thru/sim/` | local model of the Thru runtime and token program (simulation only) |
| `thru/tests/`, `thru/verifier/`, `thru/proof/` | tests, independent verifier, SMT model |
| `thru/sdk/` | `@thrubound/sdk` (TypeScript, unpublished) |
| `thru/demo/`, `examples/subscription-payer/` | demo page and independent example app |
| `docs/` | status, threat model, limitations, proofs, Phase 6–7 reviews |
| `docs/legacy/` *(full AgentVault repository only)* | the original EVM AgentVault project; not part of the public ThruBound repository |

Current status: [`docs/STATUS.md`](docs/STATUS.md) · Phase 7 review: [`docs/PHASE7_COMMUNITY_VALIDATION.md`](docs/PHASE7_COMMUNITY_VALIDATION.md)

**License:** Apache-2.0 (`LICENSE`, `NOTICE`). The vendored Thru C SDK keeps its own Apache-2.0 license. See `LICENSING.md` for the path map when the legacy AgentVault code is present.

Contributing: `CONTRIBUTING.md` · Security reports: `SECURITY.md` · Changes: `CHANGELOG.md`
