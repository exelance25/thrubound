# ThruBound — independent developer package

This page is for a developer who has never seen the project. Following it, you should be able to run every check and the example app. **Everything runs locally, in a simulation of the Thru runtime.** You need no network access to Thru, no wallet, no keys and no tokens.

## Platform support

| Platform | Status |
|---|---|
| Linux x86-64 (Ubuntu 24.04) | **Tested** (author only) |
| Windows via WSL2 + Ubuntu 24.04 | **Expected to work, not tested** |
| Windows (native) | **Not supported.** The simulation is a Linux shared library built with gcc |
| macOS | **Not tested.** `build_host.sh` produces a Linux `.so`; macOS would need changes |
| Linux arm64 | **Not tested** |

## 1. Linux (Ubuntu 24.04)

```bash
sudo apt update && sudo apt install -y build-essential git python3 python3-pip curl
# Node.js 22 (any method; nvm shown)
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash && . ~/.nvm/nvm.sh && nvm install 22
# optional, only for the SMT proofs:
pip install --user z3-solver        # on Ubuntu 24.04 add --break-system-packages, or use a venv

git clone https://github.com/exelance25/thrubound.git && cd thrubound
bash thru/run_all_tests.sh
```


## 2. Windows with WSL2 (not tested)

1. In PowerShell as administrator, run `wsl --install -d Ubuntu-24.04`, then restart and create a Linux user.
2. Open the Ubuntu terminal and follow section 1 **inside WSL**.
   - Clone into the Linux file system (`~/thrubound`), **not** under `/mnt/c/...`. File-system speed and permissions there differ, and npm installs are much slower.
3. The demo page (`npm start` in `thru/demo`) listens on `127.0.0.1:3100`. WSL2 normally forwards that port, so it opens in a Windows browser at `http://localhost:3100`.

## 3. One command

```bash
bash thru/run_all_tests.sh        # all 11 checks, about 4-5 minutes
QUICK=1 bash thru/run_all_tests.sh  # skips the mutation check
```

The script:
- checks the prerequisites;
- builds the simulation library;
- runs the Python suites, the verifier, a bounded model check and the SMT proofs (if z3 is present);
- installs and tests the SDK, the example app and the demo.

It prints one PASS, FAIL or SKIP line per check. The exit code is 0 if everything passes, 1 if anything fails and 2 if a prerequisite is missing. The full output goes to `thru/build/run_all_tests.log`.

**Expected output:** `thru/run_all_tests.expected.txt`. Your timings and compiler string will differ; the counts should not:
- 77 Python tests;
- 37/37 traces;
- 15 tamper tests;
- 12 SDK tests;
- 92/92 SMT obligations;
- 19 caught + 1 equivalent mutant (20 in total).

## 4. Example application

`examples/subscription-payer` is a separate app that uses only the public `@thrubound/sdk` API. In it, an AI agent pays a vendor subscription. It needs the simulation library and the built SDK, so run `run_all_tests.sh` once first (or the first two lines below).

```bash
cd thru && bash build_host.sh && (cd sdk && npm ci && npm run build) && cd ..
cd examples/subscription-payer && npm install
npm start          # steps 1-8, ends with "All demo checks passed (LOCAL SIMULATION)."
npm run verify     # independent verifier over out/trace.jsonl, ends with "PASS: 1/1 traces clean"
```

The eight steps:
1. Create a vault and bind its token account, proving the mint cannot be frozen.
2. Give the agent a permission: 10 per payment, 50 per day, 200 in total, valid 7 days.
3. Pay 5.
4. A payment of 9 waits for approval. The owner approves it once; a second approval is refused (`NO_PENDING`).
5. Refusals: above the per-payment limit (`PER_TX`), a stranger as recipient (`RECIPIENT_NOT_ALLOWED`), an old nonce (`BAD_NONCE`), the agent approving for the owner (`NOT_OWNER`).
6. Revoke while a request is pending. Approving the old request, or a new payment, is refused (`UNKNOWN_AGENT`).
7. Read the state back.
8. Run the authority analysis. Expected: 2 VERIFIED, 9 UNVERIFIED, 2 RISK, because simulated data is never VERIFIED as chain fact.

To write your own app, follow `docs/SDK_INTEGRATION_GUIDE.md`.

## 5. Demo page

```bash
cd thru/demo && npm install && npm start   # http://127.0.0.1:3100
```

## 6. Live test on the Thru alphanet (GitHub Actions)

The workflow `.github/workflows/alphanet-e2e.yml` (manual trigger) downloads the official toolchain v0.4.2, checks its pinned hashes, builds the program and checks that it is byte-identical to the pinned hash. It then runs `thru/network/alphanet-e2e.mjs` against the alphanet:
- throw-away test keys, held in memory only;
- native THRU from the official faucet;
- a test mint without a freeze authority;
- deploy, the ThruBound flows, and direct token-program probes for KSI-1.

It uploads `alphanet-evidence.json` (public data only). To run it locally on Linux with network access: `cd thru/network && npm ci && node alphanet-e2e.mjs <flowstate_c.bin>`.

## 7. What this package does not give you

- **No Thru network transport.** The SDK can only talk to the local simulation, and every receipt says `environment: "local-simulation"`.
- **No local Thru VM.** The local checks run the program's C code in a simulation. Real execution on a Thru VM happens only in the alphanet workflow (§6), which builds with the official toolchain and deploys to the alphanet.
- **No npm package.** `@thrubound/sdk` is used through a `file:` dependency.

## 8. Feedback we would like from you

1. How long did it take until `ALL CHECKS PASSED`, and where did you get stuck?
2. Was anything in the README or the guide wrong or unclear?
3. Is the authority report (`examples/subscription-payer` step 8) understandable without explanation?
4. For your own use case, would you pick ThruBound, an official wallet signing session, or the Rate Limiter? Why?
