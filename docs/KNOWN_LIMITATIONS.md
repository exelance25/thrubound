# ThruBound — known limitations (updated 2026-11-01, after the alphanet test)

| # | Limitation | Effect | Way out |
|---|---|---|---|
| L-1 | ~~Thru network unreachable~~ **resolved 2026-11-01**: the program runs on the alphanet from GitHub Actions (`alphanet-e2e`, 42/42). The original development sandboxes still cannot reach `*.thru.org` | network work goes through the workflow | `.github/workflows/alphanet-e2e.yml` |
| L-2 | No local Thru VM | the large suites run in a local simulation; only the alphanet run executes the RISC-V binary on a real VM (42/42) | run the workflow after every program change |
| L-3 | Token program source not public | the local suites test against a model of `transfer`. On the alphanet, the real program refused direct transfer, burn, close and freeze of the vault account (KSI-1 probes), but untested paths cannot be ruled out | review by Thru engineers |
| L-4 | ~~Toolchain deviation~~ **resolved 2026-10-30**: built with the official toolchain v0.4.2 (gcc 15.2.0) and release SDK, reproducible (`THRU_COMPATIBILITY_EVIDENCE.md`) | the official toolchain needs glibc ≥ 2.38 and was obtained through the linked computer's GitHub access | `thru/scripts/build_official.sh` |
| L-5 | Token program address taken from the SDK header | may differ per network ("freshly bootstrapped networks") | confirm with `thru program status` / the network; override with `-DFS_TOKEN_PROGRAM_BYTES` |
| L-6 | The simulation does not check account-creation state proofs | real proofs were built and accepted on the alphanet (vault, agent, request, mint and token accounts) | — |
| L-7 | Daily limit is a UTC calendar day (BF2-2) | up to 2 × daily can pass around 00:00 UTC | design decision; documented |
| L-8 | Limits cannot be lowered below what is already used (CE-1, D-13) | an owner who wants to stop an agent uses revoke or pause | by design |
| L-9 | Same-block ordering (BF2-4) | not reviewed for Thru | review with Thru block-production docs |
| L-10 | Max 8 recipients per agent | larger allowlists need several agents | capacity constant `FS_MAX_RECIPIENTS` |
| L-11 | One mint per vault | multi-token needs several vaults | by design |
| L-12 | `@thrubound/sdk` has only the local-simulation transport. Network calls exist only in the test harness (`thru/network/harness.mjs`); there is no wallet (passkey) integration and no passkey approval | an app cannot yet use the SDK against a network | network transport + wallet integration (next step) |
| L-13 | No audit, no formal verification | tests and mutation checks are not a security approval | independent review |
| L-14 | KSI-1: alphanet probes passed (transfer, burn, close, freeze refused; balance unchanged); not proven for every path | fund protection still rests on assumptions A1–A5 (`KSI1_THRU_TRUST_MODEL.md`) | review by Thru engineers; repeat after token-program upgrades |
| L-15 | Managed programs stay upgradeable until finalized. The alphanet test deployments are not finalized; their authority was a throw-away key that no longer exists | a production deployment must be finalized or disclose its authority | `thru program finalize` |
| L-16 | Demand unvalidated | product-market fit unknown | feedback from Thru developers |
| L-17 | **Rate Limiter removed from the official SDKs in v0.4.3** (2026-10-30) | the analyzer's Rate Limiter checks target the v0.4.2 ABI (legacy); composition with the Rate Limiter is no longer planned | `@thru/*` pinned to 0.4.2; revisit when Thru documents its replacement |
| L-18 | Official SDK v0.4.3 exists; ThruBound builds against v0.4.2 | v0.4.3 changes are reviewed in `SECURITY_REVIEW.md` (invoke-target check adopted) | upgrade after the alphanet reset |
