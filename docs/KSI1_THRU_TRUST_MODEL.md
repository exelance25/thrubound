# KSI-1 on Thru — evidence and restricted trust model (2026-10-30)

**KSI-1 remains OPEN.** On Thru, the class of risk is "any path that moves or destroys a vault's tokens without passing ThruBound's policy checks". This document collects every piece of available evidence, states the assumptions, and says exactly what the MVP can and cannot guarantee.

**The historical EVM finding is unchanged** and stays documented on the EVM branches. In EVM, an EIP-3009 / ERC-1271 token-level authorization path could bypass vault accounting.

**Implementation source of the token program: not public.** Nothing below comes from reading the token program's code, and nothing has run on a Thru network.

Evidence grades:

| Grade | Meaning |
|---|---|
| **ABI** | official ABI YAML (`tn_token_program.abi.yaml`, v0.1.0) |
| **CLI** | official `thru` CLI 0.4.2 help text (`m2/thrubound-p3/cli-token-help.txt`) |
| **SDK** | official SDK source |
| **SIM** | our local simulation (a model) |
| **INFERRED** | a conclusion from documented facts, stated as such |

## 1. Evidence per path

| Path | Who must authorize (evidence) | Can it bypass ThruBound? | Evidence grade |
|---|---|---|---|
| `transfer` (tag 2) out of the vault token account | No authority field in the instruction (`source_idx, dest_idx, amount`; ABI). The CLI's `transfer` takes only FROM/TO/AMOUNT, with the fee payer as signer (CLI) | Only if someone other than the token account's owner can authorize it. The vault token account's `owner` is the vault address, checked at BIND_TOKEN | ABI, CLI. Authority = owner is **INFERRED**: the token account layout has no other authority field |
| `burn` (tag 4) | "Account authority address" (CLI) | same as transfer. Destroys tokens; does not move them | CLI, ABI; INFERRED that account authority = owner |
| `close_account` (tag 5) | "Account authority address"; sends the remaining balance to a DESTINATION (CLI) | **An alternative transfer path**, authorized by the account authority, i.e. the vault | CLI; INFERRED as above |
| `freeze_account` / `thaw_account` (tags 6, 7) | the mint's "Freeze authority address" (CLI). A mint may have no freeze authority (`has_freeze_authority`, ABI; `--freeze-authority` optional, CLI) | Freezing blocks payments (denial of service), it does not move funds | ABI, CLI |
| `mint_to` (tag 3) | "Mint authority address" (CLI) | Adds tokens; cannot take the vault's | CLI |
| Who can authorize the vault address | Authorized accounts are the fee payer, the executing program, or accounts in a calling program's `tsys_invoke` auth list that the calling program owns (SDK `tn_sdk.c`). The vault account is owned by the ThruBound program and is no one's key | Only ThruBound can authorize it. ThruBound invokes only `transfer` (tag 2), from `REQUEST`, `APPROVE` and `WITHDRAW` | SDK. Runtime enforcement **INFERRED** from the SDK; not observed on a VM |
| Writing token account data directly | Program-owned accounts are writable by their owner program (SDK model) | no | SDK, INFERRED |
| ThruBound's own instructions | All checks in the program (`THRU_SECURITY_INVARIANTS.md`) | `WITHDRAW` (owner only) is the documented exit path, by design | SIM: tests, property campaign, mutation check |
| Direct `transfer` attempts by attacker, agent and owner | — | refused | **SIM** (`test_adversarial.AlternateTransferRoutes`; property campaign: 0 successes) |

## 2. Restricted trust model

ThruBound's fund-protection claim holds **only under these assumptions**:

| # | Assumption | Status |
|---|---|---|
| A1 | The token program accepts `transfer`, `burn` and `close_account` from a token account only when the account's **owner** is authorized | CLI-documented ("account authority"); equality with `owner` INFERRED; **unverified on chain** |
| A2 | The runtime authorizes an account only as the SDK describes (fee payer, executing program, or a calling program's own accounts in its invoke auth list) | SDK-documented; **unverified on a VM** |
| A3 | No token-program instruction moves balances other than those in the ABI | ABI lists 8 instructions; **unverified** |
| A4 | The token program at the configured address is the official one | the program checks the address against the SDK constant (`4ce28434…`, the same address as `taTOKENKR…`); deployment on a given network **unverified** |
| A5 | The ThruBound program is deployed immutable (no upgrade authority), or its upgrade authority is trusted | deployment-time choice. The CLI offers `program finalize` ("make it immutable"); **not done** (nothing deployed) |

**What the MVP guarantees under A1–A5** (each point checked in simulation, see `INVARIANT_PROOF_REVIEW.md`):
- Vault tokens leave only through ThruBound's `REQUEST` / `APPROVE` (policy-checked) or the owner's `WITHDRAW`.
- No one else can transfer, burn or close the vault token account.

**What it does not guarantee:**
- If the mint has a freeze authority, that authority can freeze the vault (denial of service).
  - Mitigation, enforced on chain: pass the mint to `BIND_TOKEN`. The vault is then accepted only if the mint has **no** freeze authority, and records `FS_VAULT_MINT_UNFREEZABLE`.
- If the ThruBound program is upgradeable, its upgrade authority can replace the code (A5).
- Anything that breaks A1–A4.
- The owner's `WITHDRAW` is unlimited by design. ThruBound limits **agents**, not the owner.

## 3. What would close KSI-1

1. On a Thru test network, with a test mint and a vault token account owned by a ThruBound vault address, attempt `transfer`, `burn` and `close_account` signed by the owner, the agent and an attacker. All must fail.
2. Attempt `freeze_account` on a mint without a freeze authority. It must fail.
3. Confirm the token program address on that network.
4. Deploy ThruBound finalized (immutable), or document its upgrade authority.

**Result on the alphanet (2026-11-01, `m2/thrubound-alphanet/`):**
1. **PASS for the paths tried.** Direct `transfer` signed by the owner and by the agent, `burn` by the owner and with the vault named as an unsigned authority, and `close_account` were all refused by the real token program. The vault balance stayed unchanged. Not every possible attacker and path has been tried.
2. **PASS.** `freeze_account` on the vault account (mint without a freeze authority) was refused.
3. **PASS.** The token program address used (`taTOKENKR…`) is the one the real transfers went through.
4. **OPEN.** The test deployments are not finalized. A production deployment must be finalized or disclose its authority.

KSI-1 therefore stays **open, with alphanet evidence**: the token program source is not public, and Thru can upgrade it.
