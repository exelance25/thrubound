# ThruBound — threat model (2026-10-31)

**Scope.** The ThruBound program, its SDK, and a vault holding one token on Thru. Evidence levels follow `PHASE6_INTEGRATION_REVIEW.md` §4. Nothing here has been observed on a Thru network.

## 1. Assets

- **Vault tokens** (primary).
- Each agent's remaining allowance.
- The integrity of approvals.
- The availability of payments.
- The truthfulness of reports (the authority analysis and the verifier).

## 2. Actors and trust

| Actor | Trusted for | Not trusted for |
|---|---|---|
| Vault owner | everything about the vault (WITHDRAW is unlimited) | — |
| Agent (AI or service key) | nothing beyond its policy | anything; may be compromised or prompt-injected |
| Stranger | nothing | anything |
| Mint authority / freeze authority | supply; freeze (if present) | moving vault tokens |
| ThruBound program upgrade authority | the code itself | — (must be finalized or trusted; currently undetermined) |
| Token program, runtime | H1, H4, H5 | — (implementation not public; KSI-1) |
| Rate Limiter admin (if used) | the policy | — |
| SDK, demo, any client | nothing: the program re-checks everything | — |

## 3. Threats

| # | Threat | Mitigation | Evidence level |
|---|---|---|---|
| T1 | Compromised agent drains the vault | Per-payment, per-day and lifetime limits; allowlist; expiry; nonce; approval above threshold | proved on the model, conformance-tested, model-checked; simulated |
| T2 | Agent replays or skips nonces | Strict `nonce == next_nonce` | same |
| T3 | Agent approves its own request | Approval requires the owner's authorization | tests, model check T8; simulated |
| T4 | Approval reused or altered (amount, recipient, …) | 8-field binding; executed requests never reopen | proved on the model; tests |
| T5 | Revoked agent's pending request executed later | Epoch bump; approval requires the current epoch | proved on the model; tests |
| T6 | Owner lowers limits below what is used, creating impossible states | CE-1: refused | proved (the sanity check shows the counterexample without it) |
| T7 | Direct token transfer, burn or close of the vault account (KSI-1) | Vault PDA owns the token account; only ThruBound authorises it | official docs and CLI for authorities; **token behaviour unverified** |
| T8 | Mint freeze authority blocks payments | `BIND_TOKEN` with the mint: only unfreezable mints; the analyzer reports RISK otherwise | simulated; rule in official docs |
| T9 | Program upgrade replaces the rules | Deploy finalized, or disclose the authority; the analyzer reports RISK | **open** (nothing deployed) |
| T10 | Account substitution (forged vault, agent or request accounts) | Owner, size and derived-address checks | tests and mutants; simulated |
| T11 | Malformed transactions (unsorted or duplicate accounts) | Clients canonicalise; the simulation enforces the official rule | official docs; simulated |
| T12 | Partial failure (transfer fails after accounting) | Atomic transaction | **official docs** (H1); simulated |
| T13 | Concurrent requests overspend | Reservation at request time; serial effect assumed | simulated; **H2 unverified** |
| T14 | Midnight double-spend of the daily limit (BF2-2) | Documented; not prevented (calendar day) | documented |
| T15 | Owner key loss or compromise | Out of scope; recommend the passkey wallet as owner (`invoke` path) | design only |
| T16 | Misleading report (the analysis says "safe" while it is not) | Strict classification; anything unreadable is RISK; simulated data is never VERIFIED | tests |
| T17 | Rate Limiter admin, or a missing selector, drains RL-held funds | Analyzer flags `rl-admin`, `rl-selector` and others | ABI-level; simulated |
| T18 | Session key of the official wallet used for unlimited actions | Use a ThruBound allowance instead | design argument (official docs: sessions sign any intent) |

## 4. Residual risk (what a user must accept today)

- The owner key can take everything (by design).
- The upgrade authority of the program is undetermined.
- The token program's real authority rules are unverified (KSI-1).
- Concurrency (H2) and time monotonicity (H3) are unverified.
- No audit. The on-chain test so far is one alphanet run (42/42), not mainnet.
