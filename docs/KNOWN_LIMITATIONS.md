# ThruBound (Flowstate on Thru) — known limitations (updated 2026-10-30, Phase 5 gate)

| # | Limitation | Effect | Way out |
|---|---|---|---|
| L-1 | Thru network unreachable from both available environments | no deployment, faucet, wallet, real transactions or indexer; acceptance criteria 6, 12, 13 unmet | an environment that can reach `*.thru.org` |
| L-2 | ~~No Thru VM~~ **ran on the alphanet VM 2026-11-01 (42/42)**; still no local VM | the RISC-V binary has never been executed; compute limits, syscall error codes and account-proof handling are untested | run on a Thru network or a released VM |
| L-3 | Token program source not public | `transfer` is tested against a model; `burn`, `close_account`, `freeze_account` authority rules known only from the official CLI help (KSI-1 stays OPEN) | test against the real token program on testnet |
| L-4 | ~~Toolchain deviation~~ **resolved 2026-10-30**: built with the official toolchain v0.4.2 (gcc 15.2.0) and release SDK, reproducible (`THRU_COMPATIBILITY_EVIDENCE.md`) | the official toolchain needs glibc ≥ 2.38 and was obtained through the linked computer's GitHub access | `thru/scripts/build_official.sh` |
| L-5 | Token program address taken from the SDK header | may differ per network ("freshly bootstrapped networks") | confirm with `thru program status` / the network; override with `-DFS_TOKEN_PROGRAM_BYTES` |
| L-6 | Account-creation state proofs are accepted unchecked in the simulation | proof construction in the client is untested | real network |
| L-7 | Daily limit is a UTC calendar day (BF2-2) | up to 2 × daily can pass around 00:00 UTC | design decision; documented |
| L-8 | Limits cannot be lowered below what is already used (CE-1, D-13) | an owner who wants to stop an agent uses revoke or pause | by design |
| L-9 | Same-block ordering (BF2-4) | not reviewed for Thru | review with Thru block-production docs |
| L-10 | Max 8 recipients per agent | larger allowlists need several agents | capacity constant `FS_MAX_RECIPIENTS` |
| L-11 | One mint per vault | multi-token needs several vaults | by design |
| L-12 | SDK has only the LOCAL SIMULATION transport; no network transport, no passkey approval, no Rate Limiter composition | an independent app can integrate only in simulation | needs a reachable Thru network |
| L-13 | No audit, no formal verification | tests and mutation checks are not a security approval | independent review |
| L-14 | KSI-1 open: token `burn` / `close_account` / `freeze` authority is documented only by the official CLI help, not verified on chain | fund protection holds only under assumptions A1–A5 (`KSI1_THRU_TRUST_MODEL.md`) | four network checks |
| L-15 | Thru program deployment would be upgradeable unless finalized | the upgrade authority could replace the code | deploy with `thru program finalize` or document the authority |
| L-16 | Demand unvalidated; Thru ecosystem not inspectable from here | product-market fit unknown | user interviews, ecosystem review |
| L-17 | **Rate Limiter removed from the official SDKs in v0.4.3** (2026-10-30) | the analyzer's Rate Limiter checks target the v0.4.2 ABI (legacy); composition with the Rate Limiter is no longer planned | `@thru/*` pinned to 0.4.2; revisit when Thru documents its replacement |
| L-18 | Official SDK v0.4.3 exists; ThruBound builds against v0.4.2 | v0.4.3 changes are reviewed in `SECURITY_REVIEW.md` (invoke-target check adopted) | upgrade after the alphanet reset |
