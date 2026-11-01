# ThruBound — developer onboarding test (2026-10-31)

> **Update 2026-11-01:** the program has since run on the Thru **alphanet** (official-toolchain build, deploy, 42/42 live checks; `m2/thrubound-alphanet/EVIDENCE.md`). Statements below that say "BLOCKED", "not run on a network" or "local simulation only" describe the state on the date of this document.

**Method.**
- A fresh clone of `feature/thrubound`, in an empty directory.
- Only the documentation was followed (README, then `docs/SDK_INTEGRATION_GUIDE.md`), plus the SDK's published TypeScript types.
- A new application was written outside the repository, depending only on `@thrubound/sdk` (`file:` dependency) and `@thru/sdk`.
- Environment: Linux x86-64, Node 22.22, Python 3.13, gcc 13.3.

**Honest caveat.** The test was performed by the same engineer who wrote the code and the documents, so it understates the difficulty for a real newcomer. **A test by an independent developer is still needed.**

## Result

The seven required steps all worked through the public interface, on the second attempt:
1. policy (vault and token binding);
2. agent permission;
3. payment;
4. over-limit payment refused (`PER_TX`);
5. payment waiting for approval, then approved;
6. revoke, after which a payment is refused (`UNKNOWN_AGENT`);
7. state read back, trace written, independent verifier `PASS`.

## Frictions found

| # | Friction | Severity | Status |
|---|---|---|---|
| F1 | The repository README only describes the legacy EVM project; nothing points to ThruBound | high | **Fixed**: README now starts with a pointer to the guide, the status and the example |
| F2 | Prerequisites not listed (gcc, Node 22, Python 3; Linux) | medium | **Fixed** in guide §0 |
| F3 | No explanation of how to get actor addresses in the simulation. A natural guess (`"taOWNER"`) fails with `Must be provided as hex string or ta-address` from `@thru/sdk` | high | **Fixed**: guide shows key generation, and the SDK error now says `not a Thru address: "taOWNER" (expected …)` |
| F4 | Simulation fixtures listed without signatures. The vault token account must be owned by the vault, which needs `Pubkey.from(vault).toBytes()` | medium | **Fixed**: signatures and the owner rule are in guide §5 |
| F5 | Fixtures take bytes while client methods take `ta…` strings, so the address types are mixed | low | **Open**: client methods accept bytes as well; fixtures still need bytes |
| F6 | Plain numbers (`10` instead of `10n`) fail with `Cannot mix BigInt and other types` | high | **Fixed**: SDK validates and says `amount must be a BigInt (for example 10n)`; new SDK test |
| F7 | The authority analysis methods were missing from the guide | medium | **Fixed** in guide §2 |
| F8 | **Windows is not supported natively**: the simulation is a Linux `.so` built with gcc. The project owner works on Windows | high | **Open**: guide says to use WSL; WSL not tested |
| F9 | Running the verifier needs the repository's Python script; there is no `npx` command | low | **Open** |

## What a real external test should measure

1. Time to first payment.
2. Questions asked.
3. Whether the authority report is understood without explanation.
4. Whether the developer would choose ThruBound over the official signing sessions or the Rate Limiter for their own use case.
