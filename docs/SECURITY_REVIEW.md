# ThruBound — internal security review (2026-10-31)

> **This is an internal review, not an independent audit.** It was carried out by the same engineering process that wrote the code. Nothing here replaces a third-party audit.

## Scope

- **Program:** `thru/program/flowstate.c`, `flowstate_core.c`, `flowstate_core.h`, `flowstate_abi.h`, line by line.
- **Official rules checked:** the official Thru docs (`thru.org/docs`, read 2026-10-31):
  - "Quickstart: Build a C Program";
  - C SDK reference: Syscalls, Cross-Program Invocation, Headers and Entry Points, Accounts and Transaction Context;
  - Transactions; Faucet; `tsys_invoke`.
- **Official SDK release:** `Unto-Labs/thru` v0.4.3 (2026-10-30), diffed against the vendored v0.4.2.
- **Also reviewed:** the simulation (`thru/sim/sim.c`), the TypeScript SDK's dependencies, and the authority analyzer's sources.

## Findings

| # | Severity | Finding | Status |
|---|---|---|---|
| SR-1 | **Critical (functional)** | Account creation resized the account **before** making it writable. The official reference says `tsys_account_resize` requires "The account must already be writable", and the quickstart uses the order create → set writable → resize. On a real Thru VM every vault, agent and pending-request creation would have failed. The simulation did not enforce the rule, so all tests passed | **Fixed.** Order is now create → writable → resize. The simulation now enforces both official rules: resize needs writable (returns 3), and any program-owned account whose data changed without `tsys_set_account_data_writable` reverts the transaction with 0xB009. The old code fails 31 tests under the stricter simulation. New mutant `create_not_writable` is caught |
| SR-2 | Medium (defence in depth) | Official SDK v0.4.3 adds invoke-target authentication (UNTO-2328 / VERIA-1): a program that takes the token program's index from instruction data must check it is the real program, or a substituted executable (for example the no-op program) "succeeds" without moving tokens. ThruBound already compared the address; it did not check the account exists and carries the PROGRAM flag | **Fixed.** Address + exists + PROGRAM-flag check (equivalent to `tsdk_is_program_at_idx`). New test: a no-op executable passed as the token program is refused (`FS_ERR_WRONG_TOKEN`); the simulation now models no-op executables |
| SR-3 | Medium (supply chain) | `@thrubound/sdk` depended on `@thru/programs ^0.4.2`. Version 0.4.3 **removed the Rate Limiter client** (`@thru/programs/ratelimit`), so a fresh install outside our lockfile would resolve 0.4.3 and the SDK would fail to load | **Fixed.** `@thru/sdk` and `@thru/programs` pinned to exactly 0.4.2 |
| SR-4 | Info (positioning) | The **Rate Limiter is gone from the official v0.4.3 SDKs and C headers** (program and faucet rate-limit policy addresses removed). Its status on the networks after the upcoming reset is unknown | Documented. The analyzer's Rate Limiter checks are marked legacy (v0.4.2 ABI). Positioning text updated |
| SR-5 | Low | `BIND_TOKEN` may skip the mint check (`mint_idx = FS_NO_ACCOUNT`). The vault can then hold a freezable mint without an on-chain flag | Accepted: the flag `FS_VAULT_MINT_UNFREEZABLE` stays clear and the analyzer reports RISK. Recommend always passing the mint |
| SR-6 | Low | Pending-request accounts are never closed. State grows by 184 bytes per pending request | Accepted for alpha; a close instruction is a candidate for a later version |
| SR-7 | Low | The owner can withdraw while requests are pending (R-4), so a later approval can fail for lack of funds | Accepted, documented. Fails safely (transaction reverts) |
| SR-8 | Info | Daily limit is a UTC calendar day: up to 2× daily around 00:00 UTC (BF2-2) | By design, documented |
| SR-9 | Info | Upgrade authority: a managed program stays upgradeable by its authority until finalized | Open (T9). Deploying for production requires finalizing or disclosing the authority |

## Official C-program rules — conformance

| Rule (source) | ThruBound | Result |
|---|---|---|
| Entry point marked `TSDK_ENTRYPOINT_FN` (quickstart; Headers and Entry Points) | yes | PASS |
| Instruction data: docs read it with `tsdk_txn_get_instr_data`; `tsys_invoke` reference says the callee gets "a0 instruction data virtual address, a1 instruction data length"; Rust SDK: "the same bytes passed to your entry function" | `start(data, size)` uses a0/a1. This is also correct when called through CPI (for example from the Passkey Manager), where `tsdk_get_txn()` would return the outer transaction | PASS (documented choice) |
| Validate sizes before reading structs (quickstart; Common Patterns) | every instruction checks its size first, and copies into an aligned local with `memcpy` (no unaligned casts) | PASS |
| End with `tsdk_return` or `tsdk_revert` | yes | PASS |
| `tsys_account_create`, then set writable, then resize (quickstart; Syscalls) | **was violated (SR-1)**, now fixed | PASS after fix |
| Set writable before writing account data (Syscalls) | every write goes through `make_writable` or the create path; enforced by the simulation (0xB009) | PASS |
| CPI: check both `tsys_invoke` result and callee error (CPI reference) | both checked | PASS |
| CPI auth entries only for accounts owned by the current program (CPI reference) | only the vault PDA is authorised; the SDK wrapper also checks it | PASS |
| Verify the invoke target (SDK v0.4.3, UNTO-2328) | address + exists + PROGRAM flag | PASS after SR-2 |
| Account lists: no duplicates, read-write and read-only each sorted (Transactions) | clients canonicalise; the simulation enforces it | PASS |
| `block_time` is Unix nanoseconds (Accounts and Transaction Context; block context table) | the program assumes nanoseconds (`FS_NS_PER_DAY`) | PASS (now verified from docs) |
| Program image: managed image version 1, eight-byte zero trailer (`@thru/programs/deploy`) | official toolchain output; accepted by `validateManagerProgramImage` (`@thru/programs` 0.4.3) and the official CLI | PASS |
| Token `transfer` encoding (`tn_token_program.abi.yaml`, unchanged in v0.4.3) | `[tag 2][u16 src][u16 dst][u64 amount]`, 13 bytes, byte-identical to `createTransferInstruction` from `@thru/programs` | PASS |

## Assumptions still open

| | Status after this review |
|---|---|
| H1 failed transactions are atomic | official docs |
| H2 transactions on the same writable accounts take effect serially | **not documented** in the official docs (searched 2026-10-31); unverified |
| H3 block time never decreases | **not documented**; unverified (`block_time` units now verified as Unix ns) |
| H5 / KSI-1 only the account authority can move, burn or close a token account | ABI and CLI help support it; **on-chain probes written** (`thru/network/alphanet-e2e.mjs`), run pending network access |
| H6 C code implements the model | tested (conformance, 20 mutants), not proved |

## Evidence after the fixes

- **Tests:** 77 Python tests (one new); SDK 12/12; verifier 37/37 and 15/15.
- **Mutation:** 20 mutants, 19 caught + 1 equivalent.
- **Formal:** model check and SMT 92/92 unchanged.
- **ThruVM binary:** official toolchain v0.4.2, built twice, byte-identical, sha256 `e0843ea2ac3ef917b765df9f7c8d5706a1d9938888a1a0019bc4726809b127a6`, 27,616 bytes (`m2/thrubound-p8/`).
