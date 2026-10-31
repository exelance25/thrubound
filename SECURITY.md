# Security policy

## Status

ThruBound is an **unaudited research prototype**.
- It has **never been deployed** or executed on any Thru network.
- It has been tested only in a local simulation.
- **Do not use it with real funds.** There is no supported production version and no bug bounty.

## Reporting a vulnerability

Please report privately through GitHub: **Security → Report a vulnerability** on this repository (private vulnerability reporting). Do not open a public issue or pull request for an unfixed vulnerability.

Include:
- the affected file or instruction;
- the property that breaks (for example: spending above a limit, replaying a nonce, executing an approval after revocation, moving vault funds without the program);
- a reproduction. Ideally this is a failing test in `thru/tests/` or a sequence for `thru/tests/model_check.py`.

We will acknowledge reports as soon as we can and credit reporters who want credit. This is a small project with no response-time guarantee.

## Known open issues (already public — no need to report)

| ID | Issue |
|---|---|
| KSI-1 | Limits hold only if the token program lets nothing but the vault's program-derived authority move, burn or close the vault's token account. Not confirmed on chain |
| H2 | Assumes transactions on the same writable accounts take effect serially. Unverified |
| H3 | Assumes block time never decreases. Unverified |
| Upgrade authority | A deployed, non-finalized program could have its rules replaced |
| Owner key | A compromised owner key can withdraw everything (by design) |
| Daily limit | UTC calendar day: up to 2× the daily limit can pass around 00:00 UTC (by design) |

Full lists: `docs/THREAT_MODEL.md`, `docs/KNOWN_LIMITATIONS.md`.

## Scope of the existing evidence

The z3 result (92/92 obligations) is a proof about an **abstract model**, under the stated assumptions. It is **not** a proof of the C program or the compiled binary, and it is not an audit (`docs/FORMAL_INVARIANTS.md`).
