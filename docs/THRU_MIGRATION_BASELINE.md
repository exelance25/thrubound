# Flowstate on Thru — migration baseline (PHASE 0)

> **Update 2026-11-01:** the program has since run on the Thru **alphanet** (official-toolchain build, deploy, 42/42 live checks; `m2/thrubound-alphanet/EVIDENCE.md`). Statements below that say "BLOCKED", "not run on a network" or "local simulation only" describe the state on the date of this document.

Recorded 2026-10-30. Status words: **PASS · FAIL · BLOCKED · NOT RUN · NOT REVIEWED**. Historical numbers are labelled *historical*; only the results in §4 were reproduced for this baseline.

## 1. Repository location and selection

| Candidate | State | Decision |
|---|---|---|
| Work repository `/home/claude/agentvault` (cloud workspace) | full history; branches `master` d64673d, `m1.1` b248c50, `m2.0-m2.1` b75807f, `p1-review` bcb7ae2, `mvp-app` 14f1bf1; working tree clean | **selected** |
| User copy `C:\Users\<user>\Projects\agentvault` | same branches, HEAD `14f1bf1`; `git status` lists 730 files, but **all are mode-only** changes (100644→100755 from the Windows mount); with `core.fileMode=false` it shows 0 changes. No `node_modules` (app never installed there) | identical content; **left untouched** |
| Archives | 7 zip files (`m1`, `m1.1`, `m2.0-m2.1`, `m2.2-readiness`, `p1r2-gate`, `bf2`, `mvp`), sha256 in `m2/thru-baseline/archives-sha256.txt` | preserved, not modified; all older than or equal to the selected HEAD |
| Other folders in `Projects` | unrelated projects (collecto, edeed, …) | not touched, not merged |

**Starting point:** branch `mvp-app` @ `14f1bf194fcd7b9133cbc0d03cf43e8eebfd29f1`, clean.
- `b75807f` (latest M2.0–M2.1) is an ancestor, so nothing of it is lost.
- `mvp-app` adds the verified local app and its evidence.

**Migration branch:** `feature/thru-native-migration`, created from `14f1bf1`. Legacy branches are not modified.

Deviation from the directive's preference (base exactly on `b75807f`): `mvp-app` is the newest verified state, it descends from `b75807f`, and its three extra commits are app, evidence and documentation only. `contracts/AgentVault.sol` is identical to `d64673d` (gate-tested).

## 2. Completed features (legacy EVM implementation, inherited as reference)

| Feature | Where | Evidence level |
|---|---|---|
| Per-agent keys; per-tx, daily (UTC day), lifetime budget; expiry; recipient allowlist; approval threshold with reservation; idempotent payment ids; pause; irreversible kill | `contracts/AgentVault.sol` (M1, frozen) | tested |
| Approval-time re-checks, authority generation (epoch), reservation release on revoke, ownership cancel | `contracts/proposed/AgentVaultP1R2.sol` (proposal, local research only — BF-2) | tested (Hardhat, Foundry, mutation) |
| Independent verifiers (Python, raw events), version-specific rules | `verifier/` | tested |
| Adversarial fuzzing (colony vs random), invariant campaign | `test/colony.fuzz.js`, `experiments/`, `forge/` | tested |
| Safe 1.4.1 ownership review | `M2_0_PERMISSION_REVIEW.md`, `test/m2_0.safe.test.js` | tested locally |
| Telegram notifier (read-only, dry run) | `notifier/` | mock / dry run only |
| Local MVP panel (in-memory Hardhat chain) | `app/` | tested locally |

## 3. Incomplete / never done (legacy)

- Network verification on Arbitrum One / Sepolia: **BLOCKED** (proxy 403).
- Independent security review: **NOT REVIEWED**.
- Formal / symbolic verification: **NOT RUN** (SMTChecker ran out of memory).
- Real Telegram delivery, iExec TDX guardian, confidential payments: not built.
- App on Windows: **NOT RUN**.

## 4. Results reproduced for this baseline

Clean clone of `14f1bf1`, 2026-10-30T17:26:08Z, Node 22.22.0, npm 10.9.4, Python 3.13.16. Raw outputs: `m2/thru-baseline/`.

| Command | Result |
|---|---|
| `npm ci`, `hardhat compile`, `node --check` | PASS |
| `npm run test:all` | **PASS 320/320** |
| `npm run test:app` | PASS 27/27 |
| `npm run test:p1r2-regress` | PASS 77/77 |
| `npm run test:p1-regress` | 73 + 3 intended failures (historical record, unchanged) |
| `npm run test:dryrun` | PASS 10/10 |
| `verify`, `verify:selftest`, `verify:p1`, `verify:p1r2`, `verify:versioned` | PASS (90/90, OK, 0 findings, 90/90, 360/360) |
| `npm run test:forge` (Foundry 1.3.5) | PASS |
| `npm run check:network` | **BLOCKED** / **BLOCKED** |
| App smoke (`npm run app`) | PASS |
| M1 deployed bytecode sha256 (full) | `241ea9ee41bbfa0cb51eca8dac304c046f3bb3a1bff351d21bdddc46979d4a60` (unchanged) |

Historical results, **not** re-run as such and **not** evidence for Thru:
- *28,800 randomized actions, 30 seeds × 3 modes × 320, 0 oracle violations* (`RESULTS.md`, M1);
- *colony ≈ random* (`M1_1_EXPERIMENT.md`);
- *319/319* (BF-2 run; the current suite is 320).

## 5. Known security findings carried into the migration

| ID | Finding | Status | Relevance on Thru |
|---|---|---|---|
| KSI-1 | EIP-3009 / ERC-1271: a valid contract signature does not prove the budget or daily limits are enforced; a token-level authorization path bypasses vault accounting | OPEN (EVM) | **The class of risk transfers.** Any token-program path that can move the vault's tokens without going through the Flowstate program bypasses its limits. To be tested on Thru: token-account authority, delegate or approve-style instructions, direct account writes |
| BF2-2 | daily limit = UTC calendar day; 2 × daily around 00:00 UTC | OPEN | design choice to carry over or change |
| BF2-3 | lock-ups after lowering limits / revoking; recovery needs an actor | OPEN | same logic, re-test |
| BF2-4 | same-block ordering decided by the sequencer | OPEN | Thru block production differs; re-assess |
| R-1/R-2/R-3 | M1 approval-time gaps | OPEN on M1; closed in P1R2 | the Thru program must start from P1R2 semantics |
| R-4 | withdrawal can starve a pending request | accepted | re-assess |

## 6. Migration risks (initial)

1. **Thru network unreachable from both work environments.** `rpc.alphanet.thru.org`, `rpc.betanet.thru.org`, `thru.org` and `scan.thru.org` are all refused, from the cloud workspace (proxy 403 / DNS) and from the linked computer's shell. Without a network: no deployment, no on-chain execution, no faucet and no testnet evidence. → **BLOCKED** until the allowlist changes or another machine is used.
2. **No local Thru node or VM in the public repository.** The mirror ships SDKs, CLI, ABI tools and web packages, but no runnable Thru VM. Program logic can therefore only be **host-tested**; the RISC-V binary cannot be executed locally.
3. **The official toolchain binaries cannot be downloaded:** the GitHub API and release assets are blocked. A distribution cross-compiler (Ubuntu `gcc-riscv64-unknown-elf` 13.2, picolibc 1.8.6) differs from the official pins (riscv-gnu-toolchain 2026.01.23, picolibc 1.8.9), so artifacts are not reproducible against the official toolchain.
4. **Signer model:** Thru transactions currently carry **only the fee payer's signature** (thru CLI source, `token.rs`). Owner, agent and approver authentication must be designed around that, or around the passkey manager program.
5. **Documented program addresses** (thru CLI defaults, e.g. token program `taTOKENKRgcl3vO0yVhftATDbXuhgWcfaaxv9xpEEdMdUE`) come from the CLI's documentation and defaults only; they are **not verified on chain**.
6. **Scope:** a native rewrite in C — not a port — plus a new React frontend. The legacy EVM test evidence does not transfer.

## 7. Incident during this phase (recorded, resolved)

On first use the `thru` CLI auto-generated a development key into `~/.thru/cli/config.yaml`. My redaction pattern missed that line, so the key appeared once in a tool log of the cloud workspace. It was never written to the repository, never committed and never funded. The file was destroyed immediately and the key is treated as compromised and unused. From now on the CLI is only run in a way that never prints key fields.
