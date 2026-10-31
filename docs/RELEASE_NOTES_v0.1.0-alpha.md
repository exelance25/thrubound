# ThruBound v0.1.0-alpha — release notes (DRAFT, not published)

**Give agents permission, not power.** ThruBound is a Thru-native program and TypeScript SDK. It gives an AI agent a bounded token allowance instead of wallet access.

## ⚠️ Read this first

- **Only the local simulation has been verified.** The program's C code is compiled for x86-64 and run against a local model of the Thru runtime and token program. Every test result in this release comes from that simulation or from static tools.
- **It has not been run on any Thru network.** Nothing has been deployed and no transaction has been sent. The ThruVM binary builds reproducibly with the official toolchain v0.4.2 (sha256 `e0843ea2ac3ef917b765df9f7c8d5706a1d9938888a1a0019bc4726809b127a6`), and the official image validator accepts it. That is compilation, not execution.
- **Internal security review (not an audit):** one critical functional bug was found and fixed before release. Accounts were resized before being made writable, which a real Thru VM rejects; the simulation now enforces the official rule. See `docs/SECURITY_REVIEW.md`.
- **Open security questions:**
  - **KSI-1:** can anything other than the vault's program-derived authority move, burn or close the vault's token account? Not confirmed on chain.
  - **H2:** are transactions on the same writable accounts applied serially? Unverified.
  - **H3:** does block time never decrease? Unverified.
  - **Upgrade authority:** a deployed program must be finalized, or its upgrade authority disclosed. Not yet determined.
- **What 92/92 means.** z3 proves 92 obligations (9 safety properties, plus non-vacuity and two deliberate sanity counterexamples) about an **abstract model** of ThruBound's accounting, for all u64 values, under assumptions H1–H6.
  - It is **not** a proof of the C program, the RISC-V binary, the token program or the Thru runtime.
  - The model is linked to the C code only by testing: 20,000 conformance trials with 0 disagreements, plus mutation testing.
- **Not ready for production.** It is unaudited. **Do not use it with real funds.**

## What's included

- **Program** (`thru/program/`). It provides:
  - vaults bound to one token;
  - per-agent per-payment, daily (UTC day) and lifetime limits;
  - an expiry and an allowlist of up to 8 recipients;
  - an approval threshold, with owner approval bound to vault, agent, recipient, token, amount, nonce, expiry and operation;
  - strict nonces;
  - revocation epochs that cancel pending requests;
  - pause, kill and withdraw;
  - limits that cannot be lowered below what has been used;
  - an optional unfreezable-mint check.
- **SDK** `@thrubound/sdk` 0.1.0 (`thru/sdk/`, not published to npm). It includes:
  - the client and a local-simulation transport;
  - an **authority analyzer** reporting who could move funds in a vault, a token account or a (legacy, v0.4.2) Rate Limiter policy, as VERIFIED / UNVERIFIED / RISK.
- **Demo page** (`thru/demo/`) and **example app** (`examples/subscription-payer/`).
- **Evidence:** `m2/thrubound-phase7/EVIDENCE_MANIFEST.md`, with versions, hashes and full test outputs.

## Results (local simulation)

| Check | Result |
|---|---|
| Python tests (functional, adversarial, property, scenario, conformance) | 77/77 |
| SDK tests | 12/12 |
| Independent verifier | 37/37 traces; 15/15 tamper tests |
| Bounded model check, depth 6 | 93,536 states, no violation |
| Program mutants | 19 caught + 1 equivalent (20 in total) |
| Model ↔ C conformance | 20,000 trials, 0 disagreements |
| z3, abstract model | 92/92 obligations as expected |

## Not included / not a replacement

- **Not a generic call gate.** ThruBound only covers token transfers. Thru's Rate Limiter, the earlier generic gate, was removed from the official SDKs in v0.4.3 (2026-10-30).
- **Not a replacement for Thru's Passkey Manager.** Owner approval through the Passkey Manager is designed but not executed.
- No network transport.
- No native THRU limits.
- No shared cap across agents.
- No scheduler.

## Try it

Linux or WSL2; Windows native is not supported.

```bash
bash thru/run_all_tests.sh   # ends with "ALL CHECKS PASSED", about 4-5 minutes
```

See `docs/DEVELOPER_PACKAGE.md`.

## License

Apache-2.0. The vendored official Thru C SDK keeps its own Apache-2.0 license and NOTICE.
