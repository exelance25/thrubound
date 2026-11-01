# Likely technical questions — short answers (DRAFT, not posted)

**1. Why not just use the Rate Limiter?**
Thru's official v0.4.3 release (2026-10-30) removed the Rate Limiter from the official SDKs and C headers, so it is no longer an option we can build on. When it existed (v0.4.2 ABI and client), it had no expiry, no pending human approval and no "several recipients, one budget"; revocation didn't cancel queued items, and the policy admin could rewrite the config. ThruBound covers those cases, but only for token transfers. It is not a generic gate for arbitrary program calls.

**2. Has this run on Thru?**
Yes, on the **alphanet** test network, not mainnet. A public GitHub Actions run (`alphanet-e2e`) builds the binary with the official toolchain v0.4.2, checks that it is byte-identical to the pinned hash, and deploys it. It then passes 42/42 checks with real transactions: payments, limits, approval binding, replay, revocation, withdraw, and KSI-1 probes against the real token program. The large test suites still run in a local simulation.

**3. What exactly did you prove?**
z3 proves 9 properties for all u64 inputs (92 obligations) on an **abstract model** of the accounting, under stated assumptions:
- H1: failed transactions are atomic (from the docs);
- H2: serial effect on shared accounts (unverified);
- H3: monotonic time (unverified);
- H4: account ownership (from the docs);
- H5: token-program authority (partly inferred);
- H6: the C code implements the model (tested, not proved).

The link to the C code is testing: 20,000 random conformance trials with 0 disagreements, plus mutation testing (19 of 20 mutants caught, 1 equivalent). It is not a proof of the program and not an audit.

**4. Can a leaked agent key drain the vault?**
Not beyond what the program allows: the agent's remaining per-payment, daily and lifetime limits, only to allowlisted recipients, before expiry, with strict nonces. Above the threshold it needs the owner's approval of that exact request. The open caveat is **KSI-1**: this holds only if the token program lets no one but the vault PDA move, burn or close the vault's token account. On the alphanet, the real token program refused every direct probe we tried: transfer, burn, close and freeze, by the owner or agent key. That is evidence, not a proof, because the token program source is not public. A compromised **owner** key can take everything, by design.

**5. What about the daily limit, concurrency and upgrades?**
- **Daily limit:** it is a UTC calendar day, so up to 2× daily can pass around midnight. This is documented and by design.
- **Concurrency:** requests reserve their amount at request time. Safety assumes transactions on the same accounts are applied serially (H2), which we haven't verified for Thru.
- **Upgrades:** a deployed program must be finalized or its upgrade authority disclosed. The authority analyzer reports a RISK when it can't tell.
