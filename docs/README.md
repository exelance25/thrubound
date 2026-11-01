# Documentation map

## Current — start here

| Document | What it covers |
|---|---|
| [`../README.md`](../README.md) | what ThruBound is, what it is not, current evidence |
| [`DEVELOPER_PACKAGE.md`](DEVELOPER_PACKAGE.md) | install, one-command checks, example app, alphanet workflow |
| [`SDK_INTEGRATION_GUIDE.md`](SDK_INTEGRATION_GUIDE.md) | using `@thrubound/sdk` (local-simulation transport) |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | official-toolchain build, alphanet deployment, network requirements, pre-production checklist |
| [`../m2/thrubound-alphanet/EVIDENCE.md`](../m2/thrubound-alphanet/EVIDENCE.md) | the alphanet run: every transaction and check |
| [`SECURITY_REVIEW.md`](SECURITY_REVIEW.md) | internal review (not an audit) and official-rules conformance |
| [`THREAT_MODEL.md`](THREAT_MODEL.md), [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) | threats, residual risk, limitations |
| [`FORMAL_INVARIANTS.md`](FORMAL_INVARIANTS.md) | the nine properties, assumptions H1–H6, what the SMT result means |
| [`KSI1_THRU_TRUST_MODEL.md`](KSI1_THRU_TRUST_MODEL.md) | who else could move vault funds; alphanet probe results |
| [`AUTHORITY_ANALYSIS.md`](AUTHORITY_ANALYSIS.md) | the authority analyzer |
| [`THRU_ACCOUNT_MODEL.md`](THRU_ACCOUNT_MODEL.md), [`THRU_ARCHITECTURE.md`](THRU_ARCHITECTURE.md) | accounts, layouts, components |
| [`STATUS.md`](STATUS.md) | current status at the top, dated history below |

## Dated records

These describe the project on the date they were written. Each carries an update note where later facts changed.

- **Phase reviews:** `PHASE6_INTEGRATION_REVIEW.md`, `PHASE7_COMMUNITY_VALIDATION.md`, `TEST_REPORT.md`, `INVARIANT_PROOF_REVIEW.md`, `DEVELOPER_ONBOARDING_TEST.md`.
- **Product research:** `COMPETITIVE_ANALYSIS.md`, `COMPETITIVE_GAP_REVIEW.md`, `PRODUCT_DIFFERENTIATION.md`, `PRODUCT_DEMAND_RESEARCH.md`, `THRUBOUND_PRODUCT_SPEC.md`.
- **Migration from the earlier EVM prototype:** `THRU_MIGRATION_BASELINE.md`, `THRU_MIGRATION_DECISIONS.md`, `MIGRATION_MATRIX.md`, `THRU_SECURITY_INVARIANTS.md`, `THRU_COMPATIBILITY_EVIDENCE.md`.
- **Release preparation:** `RELEASE_NOTES_v0.1.0-alpha.md` (draft), `community/` (drafts, not posted), `CHANGELOG.md` (engineering log).
