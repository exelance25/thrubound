# ThruBound — build and deployment (updated 2026-11-01)

**State:**
- The local build and tests work.
- The program has been deployed and exercised on the **Thru alphanet** test network by the `alphanet-e2e` GitHub Actions workflow: 42/42 checks, `m2/thrubound-alphanet/EVIDENCE.md`.
- Nothing has been deployed to mainnet, and nothing should be without an independent audit and an explicit owner decision.

## 1. Local checks

Linux x86-64 or WSL2, gcc, Python ≥ 3.10, Node.js ≥ 20. From the repository root:

```bash
bash thru/run_all_tests.sh   # build + every local check (about 4-5 minutes); see docs/DEVELOPER_PACKAGE.md
```

## 2. Program build (official toolchain)

```bash
# official Thru toolchain v0.4.2 and C SDK v0.4.2 (release assets of Unto-Labs/thru)
TOOLCHAIN=<thru-toolchain-Linux-x86_64-v0.4.2> SDK_SRC=<thru-program-sdk-c-v0.4.2> OUT=<empty dir> \
  bash thru/scripts/build_official.sh
# -> <OUT>/program/build/thruvm/bin/flowstate_c.bin
```

The build is reproducible. The current binary's sha256 is `e0843ea2ac3ef917b765df9f7c8d5706a1d9938888a1a0019bc4726809b127a6` (27,616 bytes). The workflow `.github/workflows/alphanet-e2e.yml` checks the release assets' hashes and fails if the binary differs.

## 3. Alphanet (test network)

The easiest route is the workflow:

> GitHub → **Actions** → **alphanet-e2e** → **Run workflow**

In order, it:
1. builds the program with the official toolchain;
2. creates throw-away test keys in memory (never saved or printed);
3. funds them from the official faucet (native THRU);
4. creates a test mint without a freeze authority;
5. deploys with the official `@thru/programs/deploy` workflow;
6. runs the ThruBound flows and the KSI-1 probes, and uploads `alphanet-evidence.json` (public data only).

To run it yourself (Linux with network access): `cd thru/network && npm ci && node alphanet-e2e.mjs <flowstate_c.bin>`.

Things the network requires that a local simulation does not (all handled in `thru/network/harness.mjs`, following the official CLI source):

| Requirement | Symptom if missing |
|---|---|
| One state unit when a transaction creates an account (including a new fee payer) | `-497` FEE_PAYER_ACTIVATION_REQUIRES_STATE_UNIT |
| Explicit compute and memory limits (official CLI: compute 10,000 for account creation, 300,000 for token and faucet calls; memory 10,000) | `-767` VM_FAILED |
| The fee payer never repeated in the account lists | `invalid transaction: duplicate account` |
| Token `initialize_mint` / `initialize_account` take the original seed, not the derived one | token program revert |
| Track the fee-payer nonce locally when sending back-to-back | `-511` NONCE_TOO_LOW |
| A native THRU balance for the fee (the faucet call itself is free) | `-509` INSUFFICIENT_FEE_PAYER_BALANCE |

**Keys.** Use throw-away test keys only. The `thru` CLI keeps keys in `~/.thru/cli/config.yaml`; that file must never be committed, printed or copied into this repository.

## 4. Before any real deployment (not done)

- An independent security audit.
- **Finalize the program** (`thru program finalize …`), or publish who holds the upgrade authority. The alphanet deployments used a throw-away key as authority; it no longer exists, but the programs are not finalized.
- Re-check the token program address on the target network (`FS_TOKEN_PROGRAM_BYTES`).
- Resolve or accept H2 and H3 (`FORMAL_INVARIANTS.md`).
