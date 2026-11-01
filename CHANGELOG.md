# Changelog

All notable changes to ThruBound. The detailed engineering log is in `docs/CHANGELOG.md`.

## [v0.1.0-alpha] — unreleased (prepared 2026-10-31)

First public preview. **Tested on the Thru alphanet (42/42 live checks, 2026-11-01); not on mainnet. Not for production use.**

### Fixed before release (internal security review, `docs/SECURITY_REVIEW.md`)
- **Critical (functional):** accounts were resized before being made writable. The official rule requires writable first, so a real Thru VM would have rejected every account creation. The simulation now enforces the rule.
- Invoke-target check now also requires the token program account to exist and be flagged PROGRAM (official SDK v0.4.3 guidance, UNTO-2328).
- `@thru/sdk` and `@thru/programs` pinned to exactly 0.4.2: version 0.4.3 removed the Rate Limiter client the analyzer imports.

### Added
- **On-chain program** in C, built on the official Thru C SDK v0.4.2. It provides:
  - vaults bound to one token;
  - agent permissions with per-payment, daily and lifetime limits, an expiry, an allowlist of up to 8 recipients, and an approval threshold;
  - strict nonces;
  - owner approval bound to 8 fields;
  - revocation epochs that also cancel pending requests;
  - pause, kill and withdraw;
  - the CE-1 rule: limits cannot be lowered below what has been used;
  - an optional check that the vault's mint has no freeze authority.
- **TypeScript SDK** `@thrubound/sdk` 0.1.0 with a local-simulation transport and an authority analyzer (VERIFIED / UNVERIFIED / RISK).
- **Demo and example:** a demo page (`thru/demo`) and an independent example app (`examples/subscription-payer`).
- **Verification tooling:**
  - local simulation of the Thru runtime and a model of the token program;
  - 77 Python tests;
  - an independent trace verifier;
  - a bounded model checker;
  - a mutation campaign;
  - z3 proofs on an abstract model;
  - a model ↔ C conformance test.
- **Developer tooling:** the one-command runner `thru/run_all_tests.sh`, with its expected output; GitHub Actions `ci` (local checks) and `alphanet-e2e` (manual: official toolchain build, then a live test on the Thru alphanet with throw-away test keys).

### Verified on the alphanet (2026-11-01)
- The official-toolchain build is byte-identical on GitHub. Deploy succeeded, plus 42/42 live checks, including KSI-1 probes against the real token program (`m2/thrubound-alphanet/`).
- The test fixed its own client mistakes on the way: state units for account creation, explicit resource limits, the original (not the derived) seed for token instructions, and fee-payer nonce tracking. These are documented in `thru/network/harness.mjs`. **The ThruBound program needed no change on the network.**

### Known open issues
- KSI-1 is backed by alphanet probes but not proven (the token program source is not public). H2 (serial effect), H3 (monotonic time) and the production upgrade authority are open.
- No network transport and no Passkey Manager approval. The Rate Limiter analysis targets the v0.4.2 ABI; the Rate Limiter was removed from the official SDKs in v0.4.3.
- No audit.

See `docs/RELEASE_NOTES_v0.1.0-alpha.md`.
