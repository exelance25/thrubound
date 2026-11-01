# ThruBound SDK — integration guide (v0.1.0)

> **Scope:** the SDK's only transport today is the local simulation. The program itself has run on the Thru alphanet. Network calls are shown in the test harness `thru/network/harness.mjs`, which is not yet part of the SDK.

> **Environment.** The SDK talks to the ThruBound program through a `Transport`. The only transport that exists is `LocalSimulationTransport`: the real program code, compiled for your machine, running inside a model of the Thru runtime.
>
> There are **no signatures, no network and no real tokens**, and every `Receipt` says `environment: "local-simulation"`. A Thru network transport is **not implemented**: no Thru RPC was reachable, so one could not be built and tested honestly.

## 0. Prerequisites (from the Phase 6 onboarding test)

- **Tested on:** Linux x86-64 (Ubuntu 24.04) with gcc 13, Node.js 22 and Python 3.13.
- **Windows:** untested. Run it inside WSL (Ubuntu). The simulation library is a Linux `.so` built with gcc.
- **Optional:** `pip install z3-solver` only for `thru/proof/inductive_smt.py`.
- **Network:** none needed. Everything runs locally (LOCAL SIMULATION).

## 1. Install (from this repository)

```bash
cd thru && bash build_host.sh                 # builds build/host/libflowstate_sim.so
cd sdk && npm ci && npm run build && npm test # @thrubound/sdk (private package)
```

In your application:

```json
"dependencies": { "@thrubound/sdk": "file:<path>/thru/sdk", "@thru/sdk": "0.4.2" }
```

**Addresses** are ordinary Thru addresses (`ta…`), 64 hex characters, or 32 raw bytes. The SDK uses the official `@thru/sdk` `Pubkey` type and its `deriveProgramAddress` function.

In the simulation there are no wallets, so any 32 bytes act as an actor's address:

```ts
import { randomBytes } from "node:crypto";
import { Pubkey } from "@thru/sdk";
const newKey = () => new Uint8Array(randomBytes(32));
const asAddress = (b: Uint8Array) => Pubkey.from(b).toThruFmt();   // "ta…"
```

**Amounts, ids, nonces and times are `BigInt`** (`10n`, not `10`). The SDK rejects plain numbers with a clear message.

## 2. Public API

Only what `@thrubound/sdk` exports is supported: `ThruBound`, `LocalSimulationTransport`, and the types `Address`, `Limits`, `Receipt`, `Permission`, `PendingRequest`, `Transport`, `Decision`. Encoders and decoders are internal.

| Method | Who signs | What it does |
|---|---|---|
| `createVault({owner, vaultId, mint, approvalTtlSeconds?})` | owner | Creates a vault for one token. Returns `vault` |
| `bindTokenAccount({owner, vault, tokenAccount, mint?})` | owner | Binds the vault's token account, which must be owned by the vault address. Passing `mint` also proves on chain that the mint has no freeze authority |
| `grantAgent({owner, vault, agent, limits, recipients?})` | owner | Creates or changes a permission. `limits = {perTransaction, perDay, lifetime, approvalAbove, expiresAt}`. Limits can never go below what is already used |
| `allowRecipient({owner, vault, agent, recipient, allowed?})` | owner | Adds or removes one allowlisted token account (max 8) |
| `requestPayment({agent, vault, recipient, amount, nonce?})` | agent | At or below `approvalAbove`: paid at once (`outcome: "paid"`). Above it: `"pending"`. Otherwise `"refused"` with a `reason` |
| `approve({owner, vault, agent, nonce})` | owner | Executes exactly that pending request; the approval names all of its fields |
| `reject({actor, vault, agent, nonce})` | owner or the agent | Closes a pending request |
| `expire({caller, vault, agent, nonce})` | anyone | Closes a request past its deadline, or one made stale by a revocation |
| `revokeAgent`, `pause`, `emergencyStop`, `withdraw` | owner | Revocation also kills pending requests. `emergencyStop` cannot be undone. `withdraw` is the owner's exit |
| `getPermission`, `getPendingRequests`, `getVault`, `getTokenBalance` | — | Read on-chain state, including remaining budgets |
| `check({vault, agent, recipient, amount, nonce?})` | — | Predicts the program's **policy** decision without sending anything. It agrees with the program on 3,000 random requests (differential test). It does not cover signer authorization or token balances, and the program stays the authority |
| `exportProofLabSnapshot({vault, agents, tokenAccounts, fundedTotal})` | — | Raw state in the format the independent verifier checks |
| `analyzeAuthorities({vault, agents})` | — | **Who can move or block these funds?** Returns `findings` (each VERIFIED, UNVERIFIED or RISK, with its evidence) and `movers` (who, how, up to how much). Pass every agent of the vault. See `docs/AUTHORITY_ANALYSIS.md` |
| `analyzeTokenAccount({tokenAccount, ratelimit?})` | — | The same for any token account. With `ratelimit: {program, policy}` it reads a Rate Limiter policy through the official `@thru/programs` client |

Refusal reasons are the program's error names: `PER_TX`, `DAILY`, `BUDGET`, `RECIPIENT_NOT_ALLOWED`, `BAD_NONCE`, `AGENT_EXPIRED`, `UNKNOWN_AGENT`, `PAUSED`, `KILLED`, `NOT_OWNER`, `APPROVAL_MISMATCH`, `STALE_REQUEST`, `NO_PENDING`, `TRANSFER_FAILED`, `INVALID_CONFIG`, and others.

## 3. Ten-second example

```ts
import { ThruBound, LocalSimulationTransport } from "@thrubound/sdk";

const sim = new LocalSimulationTransport({ library: ".../libflowstate_sim.so" });
const tb = new ThruBound(sim);

const { vault } = await tb.createVault({ owner, vaultId: 1n, mint });
await tb.bindTokenAccount({ owner, vault, tokenAccount, mint });
await tb.grantAgent({
  owner, vault, agent, recipients: [vendor],
  limits: { perTransaction: 10n, perDay: 50n, lifetime: 200n, approvalAbove: 8n, expiresAt: now + 7n * 86_400n },
});

const r = await tb.requestPayment({ agent, vault, recipient: vendor, amount: 5n }); // r.outcome === "paid"
```

## 4. A complete independent application

`examples/subscription-payer/` is a separate package. It imports only `@thrubound/sdk` and `@thru/sdk`, and runs the seven gate steps:
1. register a policy;
2. authorize an agent;
3. make a valid request;
4. execute through the policy layer with approval;
5. see invalid actions rejected;
6. revoke;
7. independently read and verify the state.

```bash
cd examples/subscription-payer && npm install && npm start && npm run verify
```

`npm run verify` runs `thru/verifier/verify_thru.py` on the trace the app wrote. That verifier shares no code with the SDK or the program.

## 5. Simulation-only helpers

These exist on `LocalSimulationTransport` and **not** on a real chain (all arguments are 32-byte `Uint8Array`s; amounts are `bigint`):
- `createTestMint(mint, authority, freezeAuthority = null)`;
- `createTestTokenAccount(address, mint, owner, amount)`. A vault's token account must be owned by the vault address: pass `Pubkey.from(vault).toBytes()` as `owner`;
- `createRawAccount(address, owner, data)`: any other account, for example a Rate Limiter policy in analysis tests;
- `setTime`, `advanceSeconds`: move the simulated clock;
- `saveTrace(path, snapshot?)`: write the executed transactions for the verifier. Then run `python3 thru/verifier/verify_thru.py <path>`.

## 6. Not yet available

- A Thru network transport (signing with `@thru/sdk`, submission, account proofs).
- Passkey approval through Passkey Manager VALIDATE.
- Rate Limiter composition (decision D-12, deferred).

All three need a reachable Thru network. See `KNOWN_LIMITATIONS.md`.
