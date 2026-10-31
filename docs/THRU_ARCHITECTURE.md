# Flowstate on Thru — architecture

Status words: **PASS · FAIL · BLOCKED · NOT RUN · NOT REVIEWED**. Branch `feature/thru-native-migration`. The legacy EVM implementation is unchanged on its own branches (`mvp-app`, `m2.0-m2.1`, `m1.1`, `master`).

> **What has run, and where.** The program below compiles for Thru's RISC-V target (compile only). Its logic has been executed **only on the host, inside a LOCAL SIMULATION** of the Thru runtime surface. It has **not** run on a Thru VM or on any Thru network. Network access to Thru is BLOCKED from both environments available to this project (see `THRU_MIGRATION_DECISIONS.md` §1).

## 1. Components

```
                ┌──────────────────────────────── Thru L1 (BLOCKED: not reached) ───────────────────────────┐
 owner wallet ──┤ tx (fee payer = owner) ─┐                                                                  │
                │                         ▼                                                                  │
 AI agent key ──┤ tx (fee payer = agent) ─► Flowstate program (C, RV64) ──tsys_invoke(transfer)──► Token program
                │                         │   vault / agent / request accounts (program-owned)      (official, v0.1.0)
                │                         └── events (tsys_emit_event) ──► indexer / app (planned)                 │
                └──────────────────────────────────────────────────────────────────────────────────────────────┘

 Local, today:  thru/tests (Python) ─ctypes─► libflowstate_sim.so = flowstate_core.c + flowstate.c + thru/sim (LOCAL SIMULATION)
                thru/verifier/verify_thru.py ◄── traces (JSONL) written by the property campaign
```

| Path | What it is | State |
|---|---|---|
| `thru/program/flowstate_core.{h,c}` | Pure policy core: all limit, nonce, approval, revocation and pause rules. No syscalls, so the same code runs on the host and on RISC-V | PASS (host tests) |
| `thru/program/flowstate.c` | Thin adapter: account loading, address derivation checks, signer checks, account creation, the token-program CPI, events | PASS (host tests) |
| `thru/program/flowstate_abi.h` | Wire formats: ops, instruction structs, seeds, events | — |
| `thru/program/GNUmakefile`, `Local.mk` | Official SDK build (`make-bin`), output `build/thruvm/bin/flowstate_c.bin` | PASS (compile only), sha256 in `m2/thru-phase3/flowstate_c.bin.sha256` |
| `thru/vendor/thru-sdk-c/` | Official C SDK, vendored unmodified from `Unto-Labs/thru@a058dd8` (Apache-2.0) | — |
| `thru/sim/` | **LOCAL SIMULATION**: host implementation of the SDK syscalls used, the SDK authorization rules, revert with full rollback, and a **model** of the token program's `transfer` | model, see §4 |
| `thru/tests/` | Python client (`fsclient.py`), functional, adversarial and property tests, program mutation check | PASS |
| `thru/verifier/` | Independent trace verifier and its mutation tests | PASS |
| TypeScript client / agent SDK, React app | Planned (PHASE 5) | NOT RUN |

## 2. Instruction set

One Flowstate instruction per transaction. Byte 0 is the op code, followed by a packed little-endian struct whose `u16` fields are indices into the transaction's account list.

| Op | Name | Signer (authorized account) | Effect |
|---|---|---|---|
| 0 | `INIT_VAULT` | owner | creates the vault account at a derived address; stores owner, mint, approval TTL (300 s … 30 days) |
| 1 | `BIND_TOKEN` | owner | binds the vault's token account once (it must be owned by the vault address, with the vault's mint) |
| 2 | `SET_AGENT` | owner | creates or reconfigures an agent account: per-tx ≤ daily ≤ budget, threshold ≤ per-tx, key expiry |
| 3 | `REVOKE` | owner | deactivates the agent, bumps its epoch, releases all reservations |
| 4 | `SET_RECIPIENT` | owner | adds or removes one allowlisted recipient (max 8 per agent) |
| 5 | `REQUEST` | agent | checks every limit; ≤ threshold → pays now through the token program; above → creates a pending request and reserves the amount |
| 6 | `APPROVE` | owner | executes one pending request; the approval struct must match the request exactly (§3) and every limit is checked again against current settings |
| 7 | `REJECT` | owner or that agent | closes a pending request, releases its reservation |
| 8 | `EXPIRE` | anyone | closes a request whose deadline has passed, or one invalidated by revocation |
| 9 | `SET_PAUSED` | owner | pause / unpause (refused after kill) |
| 10 | `KILL` | owner | irreversible emergency stop |
| 11 | `WITHDRAW` | owner | moves tokens from the vault token account to an owner-chosen token account of the same mint (works after kill, for recovery) |

## 3. Human approval binding

`APPROVE` carries an `fs_approval_t` = `vault ‖ agent ‖ recipient ‖ mint ‖ amount ‖ nonce ‖ expires_ns ‖ op`. The program rejects the approval with `APPROVAL_MISMATCH` unless **every** field equals the stored request and `op == APPROVE`. The owner's wallet signs the transaction that carries this struct, so the owner's signature covers exactly that operation. Tests: `test_adversarial.ApprovalBinding` changes each of the 8 fields one at a time; all are refused.

## 4. LOCAL SIMULATION: what is real and what is modelled

| Real program code | Modelled (assumption until checked on a Thru VM) |
|---|---|
| `flowstate_core.c` and `flowstate.c` compiled unchanged for the host | syscall behaviour: account create/resize/writable, `tsys_invoke`, events, revert rollback |
| SDK header types (`tsdk_txn_hdr_v1`, account metadata) | `tsdk_is_account_authorized_by_idx` rules (copied from SDK source, `tn_sdk.c`) |
| SHA-256 address derivation (`sha256(program ‖ 0 ‖ seed)`) with a portable SHA-256 checked against Python `hashlib` | **token program `transfer`**: the token program's source is not in the public mirror. The model enforces: token-account owner authorized, same mint, not frozen, sufficient balance, writable. Real behaviour may differ |

## 5. EVM → Thru mapping

| EVM (legacy AgentVault) | Thru (this branch) | Note |
|---|---|---|
| Solidity contract `AgentVault` / `AgentVaultP1R2` | C program `flowstate_c.bin` (RV64) | Solidity cannot run on Thru |
| Contract storage | Program-owned accounts at derived addresses (vault 136 B, agent 416 B, request 184 B) | `THRU_ACCOUNT_MODEL.md` |
| `msg.sender` | the account at a given index **and** `tsdk_is_account_authorized_by_idx(idx)` | only the fee payer signs a transaction |
| ERC-20 `transfer` / `transferFrom` from the vault contract | CPI `tsys_invoke` → token program `transfer` (tag 2), with the vault account in the auth list | the vault **account** owns the vault token account |
| ERC-20 `approve` allowance to the vault | none: the token ABI has no approve/delegate | removes the allowance attack surface (§ KSI-1 in `THRU_SECURITY_INVARIANTS.md`) |
| EIP-712 typed approval signature | owner-signed transaction carrying the full approval struct | same fields bound, plus `op` |
| `block.timestamp` (s) | `block_time` (ns) | UTC calendar day kept (BF2-2) |
| `mapping(agent => nonce)` | `next_nonce` inside the agent account; strict `nonce == next_nonce` | |
| `revert` | `tsdk_revert(code)`: whole transaction rolls back | |
| Events / logs | `tsys_emit_event` with packed structs | decoded independently by the verifier |
| Hardhat local chain, Mock USDC | LOCAL SIMULATION host library, modelled token | never displayed as a real transaction |
| Sepolia / Base Sepolia | Thru alphanet/betanet | **BLOCKED** |

## 6. Decisions

D-1 … D-11 are recorded in `THRU_MIGRATION_DECISIONS.md`.
