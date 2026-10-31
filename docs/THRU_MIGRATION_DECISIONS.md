# Flowstate on Thru — engineering decisions and PHASE 1 compatibility record

Status words: **PASS · FAIL · BLOCKED · NOT RUN · NOT REVIEWED**. "Source-documented" means read from official Thru sources (the `Unto-Labs/thru` repository at `a058dd8` = release v0.4.2, and npm packages 0.4.2). It never means "verified on chain".

## 1. PHASE 1 compatibility results (2026-10-30)

| Check | Result | Evidence |
|---|---|---|
| Official sources | `thru.org/docs` **not reachable** (proxy 403). The official repository `github.com/Unto-Labs/thru` (public mirror, tag v0.4.2, commit `a058dd8e00ad…`) **was cloned and read** instead: SDK headers, CLI source, ABI files and READMEs | `m2/thru-phase1/` |
| `thru` CLI | **PASS (install)**: `npm i thru` → `thru 0.4.2+e47b2a21` (prebuilt `thru-linux-x64`); `thru --help` lists getversion, account, program, token, txn, faucet, abi, dev, network, debug … | `m2/thru-phase1/cli-help.txt` |
| Network: `rpc.alphanet.thru.org`, `rpc.betanet.thru.org`, `grpc.thru.org`, `thru.org`, `scan.thru.org` | **BLOCKED** from the cloud workspace (proxy 403 / `dns error` in `thru getversion`) **and** from the linked computer's shell (connection refused); npm and GitHub reachable from both | `m2/thru-phase1/network.txt` |
| Official toolchain (`thru dev toolchain install`, release tarballs) | **BLOCKED**: needs `api.github.com` and release assets, both refused | same |
| C toolchain substitute | **PASS (compile only)**: Ubuntu `gcc-riscv64-unknown-elf` 13.2.0 + `picolibc-riscv64-unknown-elf` 1.8.6, with blst v0.3.15 built from the **exact revision pinned by the SDK** (`6d960cd0…`). The official C SDK (`libtn_sdk.a`) and the official `thru dev init` C template compile with the SDK's own flags (`-march=rv64imc_zba_zbb_zbc_zbs_zknh -mabi=lp64 …`) to a RISC-V ELF and a flat `.bin` | `m2/thru-phase1/toolchain.txt` |
| Toolchain pin match | **FAIL (deviation recorded)**: the official pins are riscv-gnu-toolchain 2026.01.23 and picolibc 1.8.9; this build uses gcc 13.2 and picolibc 1.8.6, so binaries are not bit-reproducible against the official toolchain | — |
| Local Thru VM / node | **NOT AVAILABLE**: the public mirror contains no runnable Thru VM or local node. RISC-V binaries can be compiled but **not executed**. Program logic is tested on the host (§3) | — |
| Wallet / passkey (`@thru/wallet`, `@thru/passkey` 0.4.2) | **BLOCKED** for runtime use: they need a reachable network and wallet service. Packages are installable | — |
| Token program ABI | **source-documented**: `rpc/abi/type-library/tn_token_program.abi.yaml` (8 instructions, below) | — |
| Token program address | **source-documented, not verified**: SDK `tn_sdk_programs.h` `TSDK_TOKEN_PROGRAM_ADDR_HEX = 4ce28434…1d31d5` ("fixed managed addresses for freshly bootstrapped networks"); CLI default `taTOKENKRgcl3vO0yVhftATDbXuhgWcfaaxv9xpEEdMdUE` | — |
| Test token (THRUSD or other), faucet | **NOT VERIFIED**: no token address is used or claimed. The CLI has `faucet` commands, but the network is unreachable | — |

## 2. Facts from official sources that shape the design

1. **Thru is RISC-V, not EVM.** Programs are RV64 binaries using a C SDK (documented path) or a Rust SDK (in-tree). Solidity does not run, there are no ERC-20 interfaces, and addresses are 32-byte public keys (`ta…` text form).
2. **One program per transaction.** The v1 header has a single `program_pubkey`; batching goes through a multicall program.
3. **Signer model.** The transaction carries **only the fee payer's signature**. In the SDK (`tn_sdk.c`), `tsdk_is_account_authorized_by_idx` is the authorization check:
   - account index 0 (fee payer) is always authorized;
   - the currently executing program is authorized;
   - otherwise only accounts that a **calling** program explicitly authorized in its `tsys_invoke` auth list. Those must be accounts **owned by that calling program**.
4. **Program-defined accounts:**
   - address = `sha256(owner_program ‖ is_ephemeral ‖ seed32)`;
   - created with `tsys_account_create(idx, seed, state_proof)`;
   - the state proof is supplied by the client.
5. **Time:** `tsdk_get_current_block_ctx()->block_time` is Unix time in **nanoseconds**; `slot` is the block number.
6. **Events and logs:** `tsys_emit_event`, `tsys_log`. Failure is `tsdk_revert(code)`, which reverts all state changes of the transaction.
7. **Token program** (ABI `thru.program.token` v0.1.0):
   - instructions: `initialize_mint`(0), `initialize_account`(1), `transfer`(2), `mint_to`(3), `burn`(4), `close_account`(5), `freeze_account`(6), `thaw_account`(7);
   - `transfer` = `u8 tag | u16 source_idx | u16 dest_idx | u64 amount` (packed);
   - `TokenAccount` = `mint[32] | owner[32] | amount u64 | is_frozen u8`;
   - **there is no approve / delegate / permit instruction.**

## 3. Decisions

| # | Decision | Reason | Consequence |
|---|---|---|---|
| D-1 | **C** for the on-chain program | official "documented path"; SDK, template and flags verified to compile here; the Rust SDK needs its own toolchain setup and is described as in-tree, not documented | the program is `thru/program/flowstate.c` |
| D-2 | Split into a **pure policy core** (`flowstate_core.c`: no syscalls, fixed-layout state in byte buffers) and a **thin Thru adapter** (`flowstate.c`: account checks, authorization, token CPI, events) | the core runs unchanged on the host for tests and in the RISC-V build | host tests exercise the same policy code that is compiled for Thru |
| D-3 | Host **simulation** of the SDK surface the adapter uses (accounts, fee-payer / invoke authorization, block time, events, revert) and an ABI-level model of the token program's `transfer` | no Thru VM is available | every result from it is labelled **LOCAL SIMULATION (host)**, never "on Thru" |
| D-4 | Start from **P1R2 semantics**, not M1: approval re-checks the current state (key validity, generation, per-tx, budget, execution-day daily window, recipient); revocation releases reservations | M1's known gaps R-1, R-2 and R-3 must not be re-implemented | |
| D-5 | **Replay protection by strict per-agent sequence:** a request's nonce must equal the agent's `next_nonce` | no per-nonce accounts; a replayed or out-of-order nonce is always rejected | agents submit requests sequentially |
| D-6 | **Approval binding:** `Approve` carries the full operation (vault, agent, recipient token account, mint, amount, nonce, expiry, op code). The program requires an exact match with the stored pending request, and the owner must be authorized in that transaction | the owner's transaction signature covers the instruction data, so the approval is bound to exactly that operation | a mismatch reverts |
| D-7 | **The vault account owns the vault's token account** (`TokenAccount.owner = vault`) | only the Flowstate program can authorize the vault account in `tsys_invoke`, so token movements out of the vault can only happen through Flowstate's checks | Thru counterpart of KSI-1: the remaining paths (burn, close_account, freeze by the mint's freeze authority) are analysed in `THRU_SECURITY_INVARIANTS.md` |
| D-8 | **No global admin.** The "global configuration" is compiled-in constants (token program address, limits, layout version) | an upgradeable admin key would be a central bypass | changing them needs a new program deployment |
| D-9 | Recipient allowlist **inline** in the agent account (fixed capacity 8) | one account per agent; atomic checks; no extra accounts per payment | at most 8 recipients per agent in the MVP |
| D-10 | Daily window = **UTC calendar day** from `block_time` (ns), as in M1/P1R2 | keeps the legacy semantics and their documented risk BF2-2 | 2 × daily around 00:00 UTC remains possible and is documented |
| D-11 | Network-dependent work (deployment, faucet, wallet, real transactions, indexer) is **BLOCKED**, not simulated as if real | network unreachable | acceptance criteria 12 and 13 cannot be met in this environment |
| D-12 | **Owner decision 2026-10-30: ThruBound architecture option A (compose).** Use Thru's core Rate Limiter and Passkey Manager where they fit; build only a thin extension program for expiry, shared allowlist, pending approval and revocation; plus SDK and Proof Lab | the Rate Limiter already is a reusable native policy gate (`PRODUCT_DIFFERENTIATION.md`) | depends on Rate Limiter behaviour that is ABI-documented only; five checks need a Thru network first |
| D-13 | **Owner decision 2026-10-30: CE-1, refuse lowering limits below what is used.** `SET_AGENT` on an existing agent fails with `INVALID_CONFIG` if `budget < spent + reserved` or, on the same UTC day, `daily < daily_used` | makes `t ≤ L` and `d ≤ D` hold in every reachable state, as the directive's invariant states | an owner who wants to stop an agent uses REVOKE or pause instead of a lower limit |
