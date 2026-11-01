# ThruBound — pinned evidence (Phase 7, 2026-10-31)

Everything here was produced in a **LOCAL SIMULATION** or by static tools. **Nothing in this folder is a Thru network result**, apart from the read-only health checks in `net-browser.json`. No program was deployed, no transaction was sent, and no wallet, key or token was used.

## 1. Source and build

| Item | Value |
|---|---|
| Branch | `feature/thrubound` |
| Code commit the results were produced on | `78ce2c5057054680ecc416a6b34fb94dad9139b7`. The Phase 7 commit adds only docs, the test runner and evidence; the program, simulation, tests, proof and SDK are unchanged |
| Program sources (sha256) | `flowstate.c` `08bcb8fa…9c71` · `flowstate_core.c` `4ad645bd…899e` · `flowstate_core.h` `6235d966…4bf4a` · `flowstate_abi.h` `d5f0b3bd…0535` |
| ThruVM binary | `flowstate_c.bin`, 27,584 bytes, sha256 `4f49941902c4a1e0161d29280415d9b13d8f23cdc7eeffa94c17703283615e14`. **Rebuilt today from clean with the official toolchain: identical** |
| Official toolchain | `thru-toolchain-Linux-x86_64-v0.4.2`, `riscv64-unknown-elf-gcc (g5115c7e44) 15.2.0`, tarball sha256 `0b07caad88918696…` |
| Official C SDK | `thru-program-sdk-c-v0.4.2`, release asset sha256 `74c9a763bb898df2…`, identical to `thru/vendor/thru-sdk-c/thru-sdk` |
| Official CLI | `thru 0.4.2+e47b2a21` (cloud) and `0.4.2+a058dd8e` (release `.deb`). Local program-image validation accepts the binary (Phase 6) |
| Host simulation compiler | gcc 13.3.0 (Ubuntu 24.04). Compiles the **same** C program for x86-64 together with `thru/sim/sim.c`, a model of the Thru runtime and token program |
| JS SDK | `@thrubound/sdk` 0.1.0 (private, unpublished), depending on `@thru/sdk` 0.4.2, `@thru/programs` 0.4.2, `koffi` 2.16 |
| Runtimes | Node 22.22.0, Python 3.13.16, `z3-solver` 5.3.3 (pip) |

## 2. Test results (re-run 2026-10-31)

| Check | Result | File |
|---|---|---|
| One-command runner `thru/run_all_tests.sh` | **11/11 PASS** in 4 min 38 s | `run_all_tests.log`, `run_all_tests.expected.txt` |
| Python: functional 31, adversarial 30, properties 1, scenarios 13, conformance 1 | **76/76 PASS** | log |
| Independent verifier | **37/37** traces clean; 15/15 tamper tests | log |
| SDK tests | **12/12** | log |
| Example app (7 steps + authority analysis) and its trace | PASS; verifier 1/1 | log |
| Demo API test | 1/1 | log |
| Program mutation | **18 caught + 1 equivalent** (`no_approve_daily`, argued in `INVARIANT_PROOF_REVIEW.md`) | log |
| Bounded model check, depth 6 | **PASS**: 93,536 states, 364,305 transitions, no violation | `model-check-depth6.txt` |
| Model ↔ C conformance | **20,000 trials, 0 disagreements** | `conformance-20000.txt` |
| SMT proofs on the abstract model | **92/92 obligations as expected** | `smt-proofs.txt`; script `thru/proof/inductive_smt.py` sha256 `ff34b3f10bb812c01911742f6c32c20708bfd103fe76855dbd9ce46a9a35b788` |

**Status of everything above: PASS in LOCAL SIMULATION** (as of 2026-10-31). *Update 2026-11-01: the program has since run on the Thru alphanet, 42/42; see `m2/thrubound-alphanet/`.*

## 3. What 92/92 means, and what it does not

**What z3 checked.** It checked a hand-written **abstract model** of ThruBound's accounting: 12 transitions over unbounded-time, u64-ranged integers. For **every** u64 input, each transition preserves the invariant `Inv`, and each of the 9 properties follows. The 92 obligations include:
- non-vacuity: each transition is enabled in some state;
- two deliberate sanity counterexamples, so that "92/92 as expected" includes two expected failures.

**The result holds only under these assumptions** (`docs/FORMAL_INVARIANTS.md` §2):
- **H1**, a failed transaction changes only the fee payer's nonce and fee. Source: official docs.
- **H2**, transactions on the same writable accounts take effect serially. **Unverified.**
- **H3**, block time never decreases. **Unverified.**
- **H4**, only the owning program writes its accounts. Source: official docs and SDK.
- **H5**, the token program's `transfer` moves exactly `amount` or fails, and only the account authority can move, burn or close. Transfer authority is **inferred** (KSI-1).
- **H6**, the C code implements the model. **Tested only** (conformance, mutation), not proved.

**It is not:**
- a proof of the C program;
- a proof of the compiled RISC-V binary;
- a proof of the token program's behaviour;
- a proof about the Thru runtime;
- a formal verification in the audit sense.

The link from model to code is **testing**: 20,000 conformance trials, the mutation campaign and model checking. Testing can miss a disagreement.

## 4. Known vulnerabilities and open risks

From `docs/THREAT_MODEL.md` §4 and `docs/KNOWN_LIMITATIONS.md`:
- **KSI-1 OPEN.** If the real token program allowed any path that moves, burns or closes the vault's token account without ThruBound, the limits would be bypassed. This is the Thru analogue of the historical EVM EIP-3009 / ERC-1271 bypass, which stays documented on the EVM branches.
- **Upgrade authority (T9 / L-15).** A deployed, non-finalized program could have its rules replaced.
- **Owner key.** It can take everything, by design.
- **Midnight double spend (BF2-2 / L-7).** The daily limit is a UTC calendar day, so up to 2× the daily limit can pass around 00:00.
- **Concurrency (H2) and time monotonicity (H3).** Unverified.
- **Account-creation state proofs.** Accepted unchecked by the simulation (L-6).
- **No audit.**

## 5. Claims that are NOT verified

- Anything about execution on a Thru VM: compute units, syscall error codes, real account layouts at runtime.
- That the token program behaves as modelled (KSI-1, H5).
- The Passkey Manager `invoke` approval path. Designed only.
- Composition with the Rate Limiter. Deferred.
- The token, Rate Limiter and Passkey program addresses on the current networks. The docs say they target the upcoming Alphanet reset.
- Demand: no user interviews.
- That an independent developer can set the project up. Only the author has tried.
- WSL setup. Not tested.

## 6. Network diagnosis (read-only)

Files: `net-cloud.txt`, `net-cli-cloud.txt`, `net-device.txt`, `net-browser.json`. All were checked for credentials, and none are present. The full analysis is in `docs/PHASE7_COMMUNITY_VALIDATION.md` §B.
