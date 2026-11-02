# ThruBound

**Give agents permission, not power.**

ThruBound is a research prototype of a Thru-native program and TypeScript SDK. It lets an owner give an AI agent (or any automated key) a **bounded token allowance** instead of wallet access.

> **Status: v0.1.0-alpha research prototype. Not ready for production.**
> - **Tested on the Thru alphanet (test network) on 2026-11-01: 42/42 checks passed** with real transactions, throw-away test keys and test tokens (`m2/thrubound-alphanet/EVIDENCE.md`). Not on mainnet.
> - The program compiles reproducibly with the official Thru toolchain v0.4.2.
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

- **It is not a generic gate for program calls.** It only authorises token-program transfers. (Thru's Rate Limiter covered arbitrary calls; the official v0.4.3 release removed it from the SDKs.)
- **It is not a wallet.** The owner is any Thru account. Owner approval from a passkey wallet, through the Wallet program's `validate` + target-instruction flow (official v0.4.3; the older `invoke` instruction is marked legacy), is planned but has **not** been built or executed.
- It does not limit **native THRU** (fees or native transfers), only token-program tokens. One token per vault.
- It does not schedule payments. The agent triggers them.
- It has no single cap shared by several agents. The shared bound is the vault balance.
- It does not protect against a compromised **owner** key; the owner can withdraw everything.
- **SDK network transport:** `@thrubound/sdk` only talks to the local simulation so far. Network calls live in the test harness `thru/network/harness.mjs`, and there is no wallet integration yet.

## Limitations and open risks

- **KSI-1 (open, with alphanet evidence):** if the token program allowed any path that moves, burns or closes the vault's token account without ThruBound, the limits would be bypassed. On the alphanet the real token program refused every direct path we tried. Its source is not public, so other paths cannot be ruled out.
- **Assumptions:**
  - **H2 (unverified):** transactions on the same accounts take effect serially.
  - **H3 (unverified):** block time never decreases.
- **Upgrade authority:** managed programs stay upgradeable until finalized. The alphanet test deployments are not finalized; a real deployment must be (`thru program finalize`) or disclose its authority.
- **Daily limit around midnight:** up to 2× daily can pass around 00:00 UTC (calendar day, by design).
- **Program addresses:** the token program address comes from the official SDK and was confirmed by real transfers on the alphanet. Thru's docs say an Alphanet reset is coming; addresses must be re-checked after it.

Full lists: [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md), [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## How it was checked — and what that means

| Kind of evidence | Result | What it does **not** show |
|---|---|---|
| Official toolchain v0.4.2 build | reproducible binary, sha256 `e0843ea2…27a6`, rebuilt byte-identical on GitHub; accepted by the official image validator (`validateManagerProgramImage`) | behaviour (see the alphanet row) |
| Local simulation: the same C program compiled for x86-64 inside a model of the Thru runtime and token program | 77 Python tests, 12 SDK tests, verifier 37/37, model check depth 6 (93,536 states), 19 of 20 mutants caught + 1 equivalent | real network behaviour; the token program is a **model** |
| SMT (z3) on an **abstract model** | 92/92 obligations, 9 properties (no overspend, no replay, revoke and expiry hold, exact approval binding, failure consistency) | a proof of the C code. The model↔C link is **testing** (20,000 conformance trials, 0 disagreements) |
| **Thru alphanet (real test network)** | **42/42 checks PASS**: the official binary was deployed. Live on chain: vault, agent, payments, limits, nonce replay, approval binding, revocation and withdraw. KSI-1 probes: direct transfer, burn, close and freeze of the vault's token account by the owner or agent key are all refused by the real token program | mainnet; H2/H3; every possible token-program path (the token program source is not public) |

An internal security review (not an audit) found and fixed one critical functional bug: accounts were resized before being made writable, which a real Thru VM rejects. See [`docs/SECURITY_REVIEW.md`](docs/SECURITY_REVIEW.md).

Local results are not network results; only the alphanet row is. Details: [`m2/thrubound-alphanet/EVIDENCE.md`](m2/thrubound-alphanet/EVIDENCE.md) (every transaction) and [`docs/FORMAL_INVARIANTS.md`](docs/FORMAL_INVARIANTS.md) (assumptions).

## Try it (Linux or WSL2; Windows native unsupported)

```bash
bash thru/run_all_tests.sh                 # every check, about 4-5 minutes
cd examples/subscription-payer && npm start   # the example app (after the line above)
cd thru/demo && npm start                  # demo page on http://127.0.0.1:3100
```

On the alphanet:
- Latest live run (42/42): https://github.com/exelance25/thrubound/actions/runs/41294408870
- Evidence, every transaction: [`m2/thrubound-alphanet/EVIDENCE.md`](m2/thrubound-alphanet/EVIDENCE.md)
- Re-run it yourself: https://github.com/exelance25/thrubound/actions/workflows/alphanet-e2e.yml (**Run workflow**).

The workflow builds with the official toolchain, deploys, runs the live checks with throw-away test keys and faucet funds, and publishes the results in the job summary.

Prerequisites, WSL steps and expected output: [`docs/DEVELOPER_PACKAGE.md`](docs/DEVELOPER_PACKAGE.md). SDK usage: [`docs/SDK_INTEGRATION_GUIDE.md`](docs/SDK_INTEGRATION_GUIDE.md).

## Repository map

| Path | What |
|---|---|
| `thru/program/` | the ThruBound program (C, official Thru C SDK v0.4.2) |
| `thru/sim/` | local model of the Thru runtime and token program (simulation only) |
| `thru/tests/`, `thru/verifier/`, `thru/proof/` | tests, independent verifier, SMT model |
| `thru/sdk/` | `@thrubound/sdk` (TypeScript, unpublished) |
| `thru/network/` | alphanet end-to-end test and network harness |
| `thru/demo/`, `examples/subscription-payer/` | demo page and independent example app |
| `docs/` | documentation, see [`docs/README.md`](docs/README.md) for what is current and what is a dated record |

Current status: [`docs/STATUS.md`](docs/STATUS.md) · Security review: [`docs/SECURITY_REVIEW.md`](docs/SECURITY_REVIEW.md)

**License:** Apache-2.0 (`LICENSE`, `NOTICE`). The vendored official Thru C SDK (`thru/vendor/thru-sdk-c`) keeps its own Apache-2.0 license and notice.

Contributing: `CONTRIBUTING.md` · Security reports: `SECURITY.md` · Changes: `CHANGELOG.md`
