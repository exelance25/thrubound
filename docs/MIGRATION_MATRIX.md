# Flowstate → ThruBound — migration matrix (2026-10-30)

Legend:

| Label | Meaning |
|---|---|
| **Inherited** | kept as is |
| **Rewritten** | reimplemented for the Thru model |
| **Removed** | not carried to Thru; stays on its original branch |
| **Added** | new |
| **Unverified** | not checked on a Thru VM or network |

Nothing has been deleted: the Arbitrum/EVM implementation remains on `master`, `m1.1`, `m2.0-m2.1` and `mvp-app`.

| Component | Origin (branch / path) | Status on ThruBound | Reason / note | Verified where |
|---|---|---|---|---|
| Solidity vaults `AgentVault` (M1), `AgentVaultP1R2` | `master`, `m2.0-m2.1` `contracts/` | **Removed** from the Thru product; preserved on original branches | Solidity cannot run on Thru (RISC-V) | EVM tests reproduced in the baseline |
| Policy rules: per-tx, daily, budget, threshold, allowlist, nonce, approval binding, revocation epochs (R-1/R-2/R-3), pause and kill | P1R2 design docs | **Rewritten** in C (`thru/program/flowstate_core.c`) | Same semantics, ported to Thru's account model | LOCAL SIMULATION; **Unverified** on Thru |
| Token movement through ERC-20 `transfer` from the vault contract | EVM vault | **Rewritten** as a CPI to the token program `transfer`; the vault PDA owns the token account | Thru has no ERC-20 or approve; one program per transaction | model only; **Unverified** |
| EIP-712 owner approval | EVM | **Rewritten** as an owner-signed transaction carrying the approval struct. **Planned:** Passkey Manager VALIDATE | Passkey Manager already binds the exact payload | simulation; passkey **not integrated** |
| Generic gate / quotas for downstream programs | (new idea in the ThruBound directive) | **Not built**: Thru core Rate Limiter provides it | Avoid recreating core functionality | ABI only |
| Expiry, shared allowlist, pending approval, revocation | Flowstate | **Inherited** into the ThruBound Core extension | Gaps G-1 to G-4 | simulation |
| Python property harness, invariants P1–P11 | `thru/tests` | **Inherited** into the Proof Lab | | PASS (simulation) |
| Independent verifier + mutation tests | `thru/verifier` | **Inherited** into the Proof Lab | | PASS (simulation) |
| Legacy EVM verifiers (`verify` 90/90, `versioned` 360/360) and campaign results (28,800 actions / 30 seeds) | EVM branches | **Inherited as historical evidence only**, labelled historical | Not applicable to Thru code | historical |
| Authority-confinement checker | — | **Added** (planned) | Gap G-5 | — |
| Delegation SDK (TypeScript) | — | **Added** (planned) | Gap G-6 | — |
| Second independent application | — | **Added** (planned) | Proves reusability | — |
| MVP web app (`app/`, Hardhat local chain) | `mvp-app` | **Removed** from the Thru product; preserved | Talks to Hardhat; replaced by the dashboard demo | EVM only |
| Telegram notifier (M2.1) | `m2.0-m2.1` | **Removed** for now; preserved | Not in ThruBound scope | — |
| Findings KSI-1, BF2-2/3/4, R-1 to R-4 | docs | **Inherited**; KSI-1 kept OPEN with its Thru analogue | Directive: keep the EIP-3009 / ERC-1271 finding documented | — |
| Finding CE-1 (`t ≤ L` broke under reconfiguration) | Flowstate-on-Thru traces | **Rewritten**: `SET_AGENT` refuses limits below what is used (D-13) | Owner decision 2026-10-30 | simulation; 2 program mutants caught |
