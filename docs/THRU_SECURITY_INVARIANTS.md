# Flowstate on Thru — security invariants

Status words: **PASS · FAIL · BLOCKED · NOT RUN · NOT REVIEWED**. **No security audit and no formal verification have been done.** "PASS" below means the tests listed passed against the LOCAL SIMULATION (real program code, modelled Thru runtime and token program). Nothing here has been observed on a Thru VM or network.

Every invariant is enforced **inside the on-chain program** (`flowstate_core.c` / `flowstate.c`), not in a client, app or backend.

## 1. Invariants

| # | Invariant | Enforced in | Tests | Status (simulation) |
|---|---|---|---|---|
| I-1 | Only the vault owner can configure agents, recipients, pause, kill, withdraw and approve | `require_signer` (address == stored owner **and** `tsdk_is_account_authorized_by_idx`) | adversarial `UnauthorizedOwner`; mutation `adapter:no_signer_auth` | PASS |
| I-2 | Only a registered, active, unexpired agent can request; never with the owner's key | `fs_request`, `fs_agent_set` | `UnauthorizedAgent`, `Revocation`, P-campaign | PASS |
| I-3 | Each payment ≤ per-tx limit (current settings, also at approval) | `fs_request`, `fs_approve` | `Limits`; mutation `core:no_per_tx` | PASS |
| I-4 | Payments per UTC day ≤ daily limit | same | `Limits`; mutations `core:no_daily`, `core:no_approve_daily` | PASS |
| I-5 | `spent + reserved ≤ budget` when a request is accepted or approved | same | `Limits`; mutation `core:no_budget` | PASS |
| I-6 | Nonce strictly equals `next_nonce`; consumed once; never reset | `fs_request` | `Replay`; mutation `core:no_nonce`; verifier nonce check | PASS |
| I-7 | Only allowlisted recipients (checked again at approval) | same | `Allowlist`; mutation `core:no_recipient_check` | PASS |
| I-8 | An approval executes exactly the request it names (vault, agent, recipient, mint, amount, nonce, expiry, op) | `fs_approve` | `ApprovalBinding` (each field); mutation `core:no_approval_binding` | PASS |
| I-9 | A request executes at most once and never after its deadline | request status + `expires_ns` | `Expiry`, `Concurrency`; verifier double-execution mutation | PASS |
| I-10 | Revocation invalidates every pending request of the old epoch and releases its reservation exactly once | `fs_agent_revoke`, `release` | `Revocation`; mutations `core:no_epoch_check`, `core:revoke_keeps_reserved`, `core:release_double` | PASS |
| I-11 | No payment while paused or killed; kill is irreversible | `fs_vault_check_live`, `fs_set_paused` | `PauseKill`; mutation `core:unpause_after_kill` | PASS |
| I-12 | Funds leave the vault token account only through Flowstate's checks; the vault token account is the bound one; the token program is the official address | adapter `token_transfer`, `load_token_account` | `AlternateTransferRoutes`, `WrongTokenAndRecipient`; mutations `adapter:no_token_program_check`, `adapter:no_vault_token_check` | PASS (model) |
| I-13 | Program state accounts cannot be substituted (owner, size and derived address checked) | `load_owned`, `require_derived` | `AccountSubstitution`; mutation `adapter:no_owner_check` | PASS |
| I-14 | Token conservation: vault balance = funded − paid − withdrawn; no tokens created or lost | token CPI | property P9; verifier conservation | PASS (model) |
| I-16 | Limits never drop below what is already used: `spent + reserved ≤ budget` always, and `daily_used ≤ daily` while the counter's day is today (CE-1, D-13) | `fs_agent_set` | functional `test_ce1_limits_cannot_drop_below_used`; property P12 after every step; verifier on every `AGENT_SET`; mutants `core:allow_budget_below_spent`, `core:allow_daily_below_used` | PASS |
| I-17 | If the mint is passed to `BIND_TOKEN`, the vault is bound only to a mint without a freeze authority, recorded as `FS_VAULT_MINT_UNFREEZABLE` (closes the freeze path; KSI-1 trust model) | adapter `ix_bind_token` | functional `test_bind_token_unfreezable_mint`; mutant `adapter:no_freeze_check` | PASS |
| I-15 | A failed instruction changes nothing | `tsdk_revert` | every negative test checks state unchanged; verifier "failed tx with events" mutation | PASS (simulated rollback) |

## 2. KSI-1 — historical EIP-3009 bypass (EVM) and its Thru analogue

**Historical finding (kept, still OPEN on the EVM branches).** In the legacy EVM design, a token-level authorization path (EIP-3009 `transferWithAuthorization` / ERC-1271 contract signatures) could move vault funds without passing the vault's budget and daily accounting. The record is in `docs/THRU_MIGRATION_BASELINE.md` §5 and the legacy reports; nothing on this branch changes it.

**Thru analogue — the class of risk is "any token-program path that moves the vault's tokens without Flowstate".**

| Path | Thru situation | Status |
|---|---|---|
| Approve / delegate / allowance | The official token ABI (`thru.program.token` v0.1.0) has **no** approve, delegate or permit instruction | source-documented |
| Signature-based transfer (EIP-3009 style) | No such instruction in the ABI | source-documented |
| Direct `transfer` by the agent, owner or an attacker | `transfer` carries only `source_idx, dest_idx, amount` (no authority field), so the source account's owner must be authorized. The vault token account is owned by the **vault address**, which only the Flowstate program can authorize (a program can authorize only accounts it owns, via `tsys_invoke`) | PASS in simulation (`AlternateTransferRoutes`; 260 refused direct transfers in the property campaign) — **model** |
| `burn` (tag 4) | The ABI names an `authority_account_index` but does not say which authority is accepted (token-account owner, mint authority, or either). Flowstate never invokes it | NOT VERIFIED: token program source not public |
| `close_account` (tag 5) | Same: an `authority_account_index`, accepted authority not documented | NOT VERIFIED |
| `freeze_account` (tag 6) | Takes an `authority_account_index` and the mint; most likely the mint's authority. Freezing would block payments (denial of service, not theft) | NOT VERIFIED; with a test token whose mint authority is the vault owner this is limited to self-harm |
| Writing the token account directly | Accounts are writable only by their owner program | source-documented (runtime rule), NOT VERIFIED on a VM |

**KSI-1 stays OPEN** until these paths are checked against the real token program on a Thru network.

## 3. Carried findings

| ID | Thru status |
|---|---|
| BF2-2: UTC calendar day lets up to 2 × daily pass around 00:00 UTC | **carried unchanged** (D-10). Documented, not fixed |
| BF2-3: lowering limits or revoking can lock reservations until someone acts | revocation releases reservations immediately; lowered limits block payments but keep counters. Anyone can `EXPIRE` past-deadline or stale requests |
| BF2-4: same-block ordering decided by the block producer | **NOT REVIEWED** for Thru block production |
| R-1 (stale approvals after revoke) | addressed by epochs (I-10) |
| R-2 (key validity at approval) | checked at approval |
| R-3 (current limits at approval) | checked at approval |

## 4. What the evidence does not show

- Behaviour on a real Thru VM (instruction metering, syscall error codes, account proof handling).
- The real token program's behaviour (only a model).
- Anything about network-level ordering, fees or availability.
