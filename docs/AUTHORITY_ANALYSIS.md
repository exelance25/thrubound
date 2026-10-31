# ThruBound Proof Lab — authority analysis (2026-10-31)

> **"Which authorities, accounts and programs can move (or block) these funds?"**

Code: `thru/sdk/src/authority.ts`. Public API: `ThruBound.analyzeAuthorities({vault, agents})` and `ThruBound.analyzeTokenAccount({tokenAccount, ratelimit?})`. Tests: `thru/sdk/test/authority.test.mjs` (5).

## 1. Classification rules (strict)

| Status | Rule |
|---|---|
| **VERIFIED** | Every piece of evidence is an official Thru source (docs at thru.org, official ABI, official CLI 0.4.2, official SDK 0.4.2) **or real chain data**. |
| **UNVERIFIED** | Anything rests on simulated account data, on ThruBound's own code, or on an inference. |
| **RISK** | A condition that can move or block the funds outside the agent policy. **Anything the analysis cannot read is RISK, never assumed safe.** |

Each finding lists its evidence. The evidence kinds are:
- `official-doc`
- `official-abi`
- `official-cli`
- `official-sdk`
- `chain-data`
- `simulated-chain-data`
- `thrubound-code`
- `inference`

With the LOCAL SIMULATION transport, account facts are `simulated-chain-data`, so they can **never** be VERIFIED. Only purely documentary findings can be. The tests assert this.

## 2. What is checked

| Area | Finding ids | RISK when |
|---|---|---|
| Token account itself | `token-account`, `token-program`, `frozen-now` | unreadable; not owned by the token program; frozen |
| Delegation | `no-delegation` | never: the official ABI has no approve, delegate or permit → VERIFIED |
| Account authority (transfer / burn / close) | `account-authority` | owner ≠ vault address (or ≠ Rate Limiter authority PDA) |
| Freeze authority | `freeze-authority` | mint has one, or the mint is unreadable |
| Mint authority | `mint-authority` | never (mint_to cannot take funds per the docs; reported for supply) |
| Vault owner | `owner-withdraw` | always: WITHDRAW is unlimited by design |
| Vault state | `vault-state` | — (informational: paused or stopped) |
| Agents | `agent:<address>` | agent account missing |
| Agents not given to the analysis | `agents-unlisted` | fewer agents passed than the vault's `agent_count` |
| Pending approvals | movers list | — |
| ThruBound program upgrade authority | `program-upgrade` | always, until the manager meta account is read on a network or the program is finalized |
| Programs ThruBound invokes | `downstream-programs` | — (only the token program, only `transfer`; deployment not verified) |
| Atomicity | `atomicity` | never (official docs) → VERIFIED |
| **Rate Limiter custody** (via the official `@thru/programs` client) | `rl-authority`, `rl-policy`, `rl-admin`, `rl-target`, `rl-selector`, `rl-recipient`, `rl-caller`, `rl-quota`, `rl-paused` | owner is not the policy's authority PDA; policy unreadable; admin can rewrite rules (always); target is not the token program; no selector restricting to `transfer`; no destination constraint; no attested caller; no amount limit |

The **movers** list says who can move (or block) funds, by which path, up to how much, and whether that is bounded by an agent policy.

## 3. Sample (LOCAL SIMULATION; `m2/thrubound-phase6/authority-sample.json`)

Setup: a vault with 1,000 test tokens. One agent may pay 10 per payment, 50 per day and 200 in total, with approval above 8. It has paid 5 and has 9 waiting.

| Who | How | Up to |
|---|---|---|
| owner | WITHDRAW (owner) | 995 (everything), **not limited** |
| agent | REQUEST, payments ≤ 8 without approval | 36 today, 186 in total |
| owner | APPROVE the agent's pending request | 9 |

Summary: 2 VERIFIED, 9 UNVERIFIED, 2 RISK.
- **RISK:**
  - the owner can withdraw everything (by design);
  - the program's upgrade authority is not determined.
- **VERIFIED:**
  - no delegate or allowance can exist (official ABI);
  - a failed transaction changes only the fee payer's nonce and fee (official docs).
- **UNVERIFIED** (correct in the simulation, but not on real chain data or not officially documented):
  - authority with the vault address;
  - no freeze authority;
  - official token program address;
  - agent caps.

## 4. Official passages the rules rely on

Short quotations, from thru.org/docs, read 2026-10-31 through the linked computer's browser:

| Topic | Passage |
|---|---|
| Token Program | `burn`: "Requires the account authority". `freeze_account`: "Requires the freeze authority on the mint". `mint_to`: "Requires the mint authority". The addresses "do not confirm deployment on the current network" |
| invoke | the SDK rejects auth accounts "not owned by current program" (`0xBAD0A171`) |
| Transaction Execution | "Failed executions preserve nonce advancement and fee collection only" |
| Transactions | "No duplicate accounts are allowed anywhere in the transaction" |
| CLI 0.4.2 | `token close-account`: `<AUTHORITY>` = "Account authority address"; remaining balance goes to `<DESTINATION>` |

## 5. Limits of the tool

- On a network it would need a network transport, which is not implemented, so **no finding has been VERIFIED from chain data yet**.
- "Account authority = the token account's `owner`" is an **inference**: the token account layout has no other authority field. It stays labelled as such.
- The tool cannot see the token program's or the Rate Limiter's implementation (not public), or the ThruBound program's upgrade authority. These are reported, not assumed.
- Agents must be passed in. If fewer are given than the vault records, that is reported as RISK.
