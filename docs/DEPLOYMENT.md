# Flowstate on Thru — build and deployment

**State: local build and tests work. Testnet deployment is BLOCKED (Thru RPC unreachable) and has never been run.** Steps marked *not yet executed* use commands that exist in `thru` CLI 0.4.2 (`thru <cmd> --help` was read), but their output on a real network has not been seen. Mainnet deployment is out of scope without explicit owner approval.

## 1. Local (works today)

Requirements: Linux, Python ≥ 3.10, gcc. From the repository root:

```bash
cd thru
bash build_host.sh                                   # host library for the LOCAL SIMULATION
cd tests && python3 -m unittest test_functional test_adversarial test_properties
cd .. && bash tests/mutation_check.sh                # 16 mutants, all must be caught
python3 verifier/verify_thru.py                      # independent verifier over build/traces/
cd verifier && python3 -m unittest test_verifier
```

## 2. RISC-V program build

Official route (BLOCKED here because GitHub release downloads are refused):

```bash
npm i -g thru            # CLI 0.4.2
thru dev toolchain install
cd thru/program && make THRU_C_SDK_DIR=<path to thru-sdk>
```

Substitute used in this project (Ubuntu 24.04): `apt install gcc-riscv64-unknown-elf picolibc-riscv64-unknown-elf`, build blst at revision `6d960cd05d6fe2b5bc9ba161edf0c1a131b87c4c` with the SDK's flags, lay the toolchain out as the SDK expects, then

```bash
cd thru/program
RISCV_TOOLCHAIN_ROOT=<toolchain root> make THRU_C_SDK_DIR=<sdk dir>
# -> build/thruvm/bin/flowstate_c.bin
```

Recorded hash (substitute toolchain, after CE-1): `0bdd043fb5d373dd5d6f0f73267b660785bb2ce9b327e121be39e44f4c6b704e`.

## 3. Testnet (not yet executed — BLOCKED)

Keys: the CLI keeps keys in `~/.thru/cli/config.yaml`. **That file must never be committed, printed or copied into this repository.** Use a fresh test-only key.

1. Pick a network profile: `thru network add …` / `thru network use …` (alphanet or betanet; their state and program addresses are not assumed to be identical).
2. Get test THRU for fees: `thru faucet withdraw …`.
3. Confirm the token program address on that network (`thru program status`, `thru token … --help`). If it differs from the SDK header value, rebuild with `-DFS_TOKEN_PROGRAM_BYTES=…`.
4. Create a test mint whose authority is the test owner: `thru token initialize-mint …`. No USDC or other real token is used.
5. Deploy: `thru program create build/thruvm/bin/flowstate_c.bin`. Record the program address.
6. Create the vault, derive its token account owner = vault address, `thru token initialize-account …`, `BIND_TOKEN`, `thru token mint-to …` test tokens.
7. Run the agent flows; save every transaction signature; verify balances independently with `thru token balance …` and the verifier.

Each step's real output, signatures and balances go into `m2/thru-testnet/` and `docs/TEST_REPORT.md`. Nothing is reported as successful until the network shows it.

## 4. Configuration

Copy `.env.example` to `.env` (git-ignored). It holds no secrets.
