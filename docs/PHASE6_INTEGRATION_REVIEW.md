# ThruBound — Phase 6: integration and trust review (2026-10-31)

> **Update 2026-11-01:** the program has since run on the Thru **alphanet** (official-toolchain build, deploy, 42/42 live checks; `m2/thrubound-alphanet/EVIDENCE.md`). Statements below that say "BLOCKED", "not run on a network" or "local simulation only" describe the state on the date of this document.

Branch `feature/thrubound`. No testnet deployment, no real funds, no transactions on any network. Historical branches are untouched.

## 0. Access gate

| Environment | `rpc.alphanet` / `rpc.betanet` / `thru.org` / `docs.thru.org` | Use |
|---|---|---|
| Cloud workspace | refused (one attempt each, `m2/thrubound-phase6/access-cloud.txt`) | — |
| Linked computer's shell | refused (one attempt each) | GitHub API and releases reachable (used for the official toolchain in Phase 5) |
| **Linked computer's built-in browser** | **`thru.org/docs` reachable** (`docs.thru.org` redirects there). RPC endpoints not tried from the browser; no transaction, no deployment | Official documentation read in full text (`/docs/llms-full.txt`, 21,057 lines) |

The official docs became a new primary source in this phase. No access route to a Thru RPC was used or found. **Testnet remains BLOCKED**; nothing was uploaded.

## 1. Findings from the official documentation

| # | Finding | Effect | Evidence |
|---|---|---|---|
| 1 | Transactions must list accounts **without duplicates**, read-write and read-only each **sorted ascending** ("Account List Verification") | **Real bug, fixed.** Both clients produced unsorted lists, so every transaction would have been invalid on a real node. The simulation now enforces the rule (0xB006/7/8). Several direct-transfer attack tests could have passed for the wrong reason and now assert the token AUTH refusal | docs: Transactions; commit `d7b271c` |
| 2 | Invoked programs receive `a0` = instruction address and `a1` = length ("invoke" syscall). The C doc examples read the instruction through `tsdk_get_txn()` | Our `start(data, size)` convention is the documented CPI convention and matches the official `thru dev init` template and the Rust SDK entry. `tsdk_get_txn()` would return the outer transaction's data when ThruBound is called by Passkey Manager. **No change** | docs: invoke, Headers and Entry Points; SDK `entrypoint.S`; Rust SDK macros |
| 3 | A failed execution keeps only the fee payer's nonce advance and fee | Assumption H1 (atomicity) is now officially documented | docs: Transaction Execution |
| 4 | Token program: `burn` needs the **account authority**; `freeze`/`thaw` need the mint's **freeze authority**; `mint_to` needs the mint authority. The published addresses "target the upcoming Alphanet reset" and "do not confirm deployment on the current network" | KSI-1 evidence upgraded from CLI help to official docs. Deployment of the token program at the published address remains unconfirmed | docs: Token Program |
| 5 | Passkey Manager has an **`invoke`** instruction: "have the managed wallet call another program". It uses validate-then-execute over `nonce ‖ ordered accounts ‖ trailing instruction` | **Passkey approval needs no program change.** If the vault owner is a passkey wallet, VALIDATE + `invoke` → ThruBound `APPROVE` authorises the owner through the invoke auth list, which ThruBound's `require_signer` accepts. Designed, **not executed** (no Passkey Manager in the simulation) | docs: Passkey Manager Program; SDK auth rule |
| 6 | The official wallet's **signing sessions** are temporary, revocable session keys that "sign the same intent as `wallet.signTransaction`", meant for "a narrow app flow" with repeated actions. Nothing documents limits on amount, recipient or program. Revocation "removes the local SDK descriptor and asks the wallet to delete its session key" | Strongest evidence of the gap: Thru's own pattern for repeated automated actions gives full wallet power until expiry. ThruBound offers the bounded alternative. Whether revocation also removes the on-chain authority is **not documented** | docs: Signing Sessions |
| 7 | **Rate Limiter is not mentioned in the official docs** (one unrelated hit). It exists only as an ABI and an npm client (`@thru/programs` 0.4.2) | Its behaviour remains ABI-level knowledge | docs search |

## 2. Rate Limiter integration: what is direct, what needs ThruBound

Sources: `tn_ratelimit_program.abi.yaml` v0.1.0 and the `@thru/programs` 0.4.2 ratelimit client (published on npm). The **implementation is not public**, and nothing has run on a network.

| Need (directive §1) | Rate Limiter alone (per ABI) | ThruBound | Decision |
|---|---|---|---|
| Hold and spend funds | Token account owned by the policy's **authority PDA** (`"tn_ratelimit_authority_v1" ‖ policy`); `CALL` lends the PDA to the target after the matcher and quotas pass | Token account owned by the **vault PDA**; only `REQUEST` / `APPROVE` / `WITHDRAW` transfer | Both are valid custody models; both rely on the program-owned-PDA rule (official SDK/docs) |
| Ownership and alternative paths | The **admin** can replace the whole config (selector, constraints, quotas, attester) or hand over the policy → effectively controls the funds. Without a selector pinned to `transfer`, `CALL` can forward `burn` / `close_account` | No admin over agents' limits except the vault owner, whose `WITHDRAW` is explicit and unlimited by design | The analyzer flags both (`rl-admin`, `rl-selector`, `owner-withdraw`) |
| Several recipients, one budget | Not expressible in one policy: constraints pin exactly one address (ANDed, max 4); a GLOBAL bucket with no destination constraint allows **any** recipient | Allowlist of 8 sharing one per-day and lifetime budget | **ThruBound** |
| Expiry | No expiry field | `valid_until` checked at request and at approval | **ThruBound** |
| Revocation | Admin pauses or rewrites the policy | `REVOKE`: epoch bump; every pending request becomes unexecutable (SMT-proved on the model) | **ThruBound** (revocation semantics) |
| Pending human approval | None | Pending request with reservation; approval binds 8 fields; passkey path via finding 5 | **ThruBound** |
| Approval cannot execute after revocation | n/a | Proved on the abstract model (property 7) and tested against the C code | **ThruBound** |
| Windowed quotas per caller, call counts, arbitrary target programs | **Yes** (per fee payer, account, attested caller; slot or unix clock) | Only token transfers; per-agent day and lifetime | **Rate Limiter**. ThruBound must not reimplement it |
| Authority boundary between them | — | Planned composition: ThruBound vault PDA as the policy's **attester and admin**, so only ThruBound can CALL or reconfigure. Depends on (a) whether a program PDA satisfies "attester must be authorised" (ABI) and (b) the undocumented implementation | **Deferred** until behaviour can be checked on a network or in published source |

**Conclusion.** ThruBound uses the Rate Limiter today through **analysis**: `analyzeTokenAccount(..., {ratelimit})` reads a policy with the official client and reports admin, selector, recipient, caller and quota risks. It does **not** yet compose on chain, because the decisive behaviours are undocumented.

**Important limitation found while researching demand:** ThruBound only authorises **token transfers**. Agent actions that call other programs (AMM or CLOB trades, NFT purchases, registrar renewals) are outside its scope. For those, the Rate Limiter's arbitrary-target model is the right base.

## 3. Work done in this phase

| Item | Where | Result |
|---|---|---|
| Account-list rule enforced and clients fixed | sim, `fsclient.tx_index`, SDK `canonical` | Python 75/75, SDK tests |
| Authority analysis (Proof Lab) | `thru/sdk/src/authority.ts`, `docs/AUTHORITY_ANALYSIS.md` | 5 tests; example step 8; demo panel |
| SMT-checked inductive proofs (abstract model) | `thru/proof/inductive_smt.py`, `docs/FORMAL_INVARIANTS.md` | 92/92 obligations as expected |
| Model conformance (C core vs model) | `thru/tests/test_model_conformance.py` | 3,000 trials by default, 20,000 in evidence, 0 disagreements; catches 5/5 targeted C mutants |
| Mutation check including conformance and scenarios | `thru/tests/mutation_check.sh` | 18 caught + 1 equivalent |
| Developer onboarding test | `docs/DEVELOPER_ONBOARDING_TEST.md` | 9 frictions; 6 fixed in docs/SDK, 3 open |
| Product demand research | `docs/PRODUCT_DEMAND_RESEARCH.md` | 12 use cases; demand **not validated** |
| Threat model | `docs/THREAT_MODEL.md` | — |

## 4. Every claim, classified

| Claim | Verified on a real Thru network | Verified with the official compiler/tools | Verified in the local simulation | Justified mathematically | Not yet verified |
|---|---|---|---|---|---|
| Program compiles for ThruVM, reproducibly; image format accepted by the official CLI | | ✔ (toolchain v0.4.2, CLI 0.4.2) | | | Execution on ThruVM |
| Spent / reserved never exceed the budget | | | ✔ (tests, model check depth 6, property, verifier) | ✔ SMT on the abstract model; conformance-tested against C | On chain |
| Nonce used once; revoked or expired cannot act; approval binds the exact request; pending dies on revocation | | | ✔ | ✔ SMT | On chain |
| Agents sharing a vault cannot exceed what was funded; accounting moves with the balance | | | ✔ (scenarios, verifier conservation) | ✔ SMT (atomicity H1 now officially documented) | On chain |
| Failed transfer leaves accounting consistent | | | ✔ (scenarios, model check: 936 failed transfers) | ✔ (H1 per official docs) | On chain |
| Account lists valid for a real node | | ✔ (rule from official docs) | ✔ (simulation enforces it) | | Real submission |
| No one but ThruBound can move the vault's tokens (KSI-1) | | official docs and CLI document the authorities | ✔ (token **model** only) | | **Open**: real token program behaviour |
| Passkey approval works through Passkey Manager `invoke` | | documented instruction | | | **Not executed** |
| Rate Limiter composition | | ABI and official client | analysis only | | **Deferred** |
| An independent developer can integrate the SDK | | | ✔ (newcomer app, example app) | | By a real external developer |
| There is demand | | | | | **Not validated** |

## 5. Differentiation verdict

**Defensible, but narrower than "policy kernel".**

| Strength | Concrete differentiator | Evidence |
|---|---|---|
| Strongest | The **authority analyzer**: "who can move these funds, on what evidence". It works for ThruBound vaults, plain token accounts and Rate Limiter custody, and classifies strictly between official evidence, unverified evidence and risk | No comparable tool found in the Thru repository, the docs, or the products reviewed |
| Second | The **bounded allowance** (expiry + shared allowlist budget + pending approval + revocation that kills pending) for token transfers | Fills the gap left by the official signing sessions (finding 6) and the Rate Limiter (§2) |

Without validated demand, ThruBound should not be grown with more features. The next valuable step is evidence:
- a testnet run of the KSI-1 and Rate Limiter checks;
- conversations with Thru application developers who use signing sessions.

Both need the user's decision and network access.
