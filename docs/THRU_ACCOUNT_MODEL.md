# Flowstate on Thru — account model

All layouts are packed (`#pragma pack(1)`) little-endian C structs from `thru/program/flowstate_core.h` and `flowstate_abi.h`. The Python client and the independent verifier carry their own copies of these formats; tests assert the sizes.

## 1. Address derivation

```
seed    = sha256(tag ‖ fields)                       (32 bytes)
address = sha256(flowstate_program ‖ 0x00 ‖ seed)   (Thru program-defined address, not ephemeral)
```

| Account | tag | fields |
|---|---|---|
| Vault | `"flowstate/vault/v1"` | owner (32) ‖ vault_id (u64 LE) |
| Agent | `"flowstate/agent/v1"` | vault address (32) ‖ agent key (32) |
| Request | `"flowstate/request/v1"` | vault address (32) ‖ agent key (32) ‖ nonce (u64 LE) |

Every handler re-derives the expected address from the stored fields and refuses the account if it differs (`FS_ERR_DERIVATION`), and requires the account to be owned by the Flowstate program with the exact size (`FS_ERR_BAD_ACCOUNT`). Substitution tests: `test_adversarial.AccountSubstitution`.

Accounts are created by the program with `tsys_account_create(idx, seed, proof)`. The state proof is supplied by the client after the optional trailing `u32 proof_sz` field. **The proof format has not been exercised against a real node** (BLOCKED); the simulation accepts the proof bytes without checking them.

## 2. Vault — `fs_vault_t`, 136 bytes, magic `"FSV1"`

| Offset | Field | Type | Meaning |
|---|---|---|---|
| 0 | magic | u32 | `0x31565346` |
| 4 | version | u8 | 1 |
| 5 | flags | u8 | bit0 PAUSED, bit1 KILLED (kill sets both; irreversible) |
| 6 | r0 | u16 | reserved |
| 8 | owner | [32] | the only key that can configure, approve, pause, kill, withdraw |
| 40 | mint | [32] | the single token this vault pays in |
| 72 | token_account | [32] | bound once; must be owned by the vault address |
| 104 | vault_id | u64 | lets one owner have several vaults |
| 112 | approval_ttl_ns | u64 | 300 s … 30 days |
| 120 | total_paid | u64 | sum of all payments |
| 128 | agent_count | u32 | |
| 132 | r1 | u32 | reserved |

## 3. Agent — `fs_agent_t`, 416 bytes, magic `"FSA1"`

| Offset | Field | Type | Meaning |
|---|---|---|---|
| 0 | magic, version, active, recipient_cnt, r0 | u32,u8,u8,u8,u8 | |
| 8 | vault | [32] | owning vault address |
| 40 | agent | [32] | agent public key (never equal to owner; never changes) |
| 72 | epoch | u64 | bumped by every revocation |
| 80 | per_tx, daily, budget, threshold | u64 ×4 | limits; `0 < per_tx ≤ daily ≤ budget`, `threshold ≤ per_tx` |
| 112 | valid_until_ns | u64 | agent key expiry |
| 120 | day | u64 | UTC day index of `daily_used` |
| 128 | daily_used, spent, reserved | u64 ×3 | `spent + reserved ≤ budget` when a request is accepted |
| 152 | next_nonce | u64 | strictly increasing, never reset |
| 160 | recipients | [8][32] | allowlist |

Reconfiguring an agent (`SET_AGENT` on an existing account) changes limits and expiry and re-activates it, but **keeps** `spent`, `reserved`, `daily_used`, `epoch` and `next_nonce`. Lowering a budget below `spent` therefore blocks further payments instead of resetting them.

## 4. Request — `fs_request_t`, 184 bytes, magic `"FSR1"`

| Offset | Field | Type |
|---|---|---|
| 0 | magic, version, status, r0 | u32,u8,u8,u16 — status: 1 PENDING, 2 EXECUTED, 3 REJECTED, 4 EXPIRED, 5 INVALIDATED |
| 8 | vault, agent, recipient, mint | [32] ×4 |
| 136 | amount, nonce, epoch, day, created_ns, expires_ns | u64 ×6 |

A request account is created once per (vault, agent, nonce) and never reused: a closed request keeps its final status.

## 5. Approval — `fs_approval_t`, 153 bytes (instruction payload, not an account)

`vault[32] ‖ agent[32] ‖ recipient[32] ‖ mint[32] ‖ amount u64 ‖ nonce u64 ‖ expires_ns u64 ‖ op u8`.

## 6. Token accounts (official token program, source-documented)

`TokenAccount` = `mint[32] ‖ owner[32] ‖ amount u64 ‖ is_frozen u8` (73 bytes). The vault token account's `owner` is the **vault address**. The program checks the token-program account address, the token account's program owner, size, mint and binding before every transfer.

Token program address: `4ce28434a460725def3b4c9585fb404c36d7ba181671f69ac6ff71a4411d31d5` from the SDK header (`TSDK_TOKEN_PROGRAM_ADDR_BYTES`, "fixed managed addresses for freshly bootstrapped networks"). **Source-documented only; not verified on any network.** It can be overridden at build time with `-DFS_TOKEN_PROGRAM_BYTES=…` if a network uses a different address.

## 7. Transaction account lists

Index 0 = fee payer (signer), 1 = Flowstate program, then read-write accounts, then read-only accounts. Instruction fields name the indices; e.g. `REQUEST` names `vault_idx, agent_acct_idx, agent_signer_idx, request_acct_idx, vault_token_idx, recipient_token_idx, token_program_idx` (`FS_NO_ACCOUNT = 0xFFFF` for an unused slot).
