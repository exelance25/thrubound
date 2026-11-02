# Community intro — DRAFT (not sent)

> **Draft only.** Nothing has been posted anywhere. The owner decides whether, where and when to post.
>
> Repository: https://github.com/exelance25/thrubound (Apache-2.0).
>
> Suggested place: the Thru developer Discord / forum "show your project" channel, or a GitHub discussion on `Unto-Labs/thru`. Check the channel rules first.

---

**ThruBound: bounded token allowances for agents on Thru (early prototype, looking for feedback)**

Hi all. I've been building a small Thru-native program and want feedback from people who know the runtime better than I do before going further.

**The problem.** Official wallet signing sessions let an app or agent act repeatedly, but as far as I can tell from the docs a session key can sign any intent until it expires. There is no amount, recipient or program limit. For an AI agent paying for APIs or subscriptions, I'd rather give it an allowance than the wallet.

**What ThruBound does.** An owner funds a vault (one token-program token). Each agent key gets:
- per-payment, daily and lifetime limits;
- an expiry;
- a recipient allowlist;
- an approval threshold. Above it, the payment is reserved until the owner approves that exact request: vault, agent, recipient, token, amount, nonce, expiry and operation are all bound.

Revoking an agent also kills its pending requests. All checks are in the program; the TypeScript SDK is just a client. There is also an authority analyzer that reports who else could move the funds in a vault, a token account or a (legacy v0.4.2) Rate Limiter policy. It labels each finding VERIFIED / UNVERIFIED / RISK.

**What it is not.**
- It's not a generic gate for arbitrary program calls. ThruBound only covers token transfers. (The Rate Limiter that used to fill that role was removed from the official SDKs in v0.4.3.)
- It's not a wallet. The plan is for a passkey wallet to be the owner and approve through the Wallet program's `validate` + target-instruction flow (v0.4.3 marks the old `invoke` as legacy). I haven't built that yet.

**Where it actually stands — please read this part:**
- Built in C against the official C SDK v0.4.2. It compiles reproducibly with the official toolchain (gcc 15.2.0), and the official program-image validator accepts it.
- An internal review against the official C-program rules caught one critical bug before release (accounts were resized before being made writable, which the official SDK reference says the VM rejects); the simulation now enforces that rule.
- **It runs on the alphanet.** A public GitHub Actions run builds it with the official toolchain (byte-identical binary) and deploys it. It passes 42/42 live checks with throw-away test keys and test tokens: payments, limits, approvals, replay, revocation, withdraw, and direct token-program attacks on the vault. The heavier suites below run in a local simulation.
- Results:
  - 77 tests;
  - bounded model check to depth 6;
  - mutation testing;
  - an independent trace verifier;
  - z3 proofs of 9 safety properties on an abstract model, linked to the C code by 20,000 conformance trials.
  
  That last item is **not** a proof of the C code, and none of it is an audit.
- The biggest open question is the token program itself. My limits only hold if nothing but the account authority (the vault PDA) can transfer, burn or close the vault's token account. On the alphanet, the real token program refused direct transfer, burn, close and freeze of the vault account by the owner and agent keys. I'd still love a second pair of eyes, since the token program source isn't public.

**What I'd love help with:**
1. Is there any token-program path (delegation, close, burn, freeze, a feature I missed) that can move a PDA-owned token account without the PDA signing?
2. Are transactions touching the same writable accounts always applied serially, and is block time monotonic?
3. Would you use something like this instead of a signing session for agent payments? What would stop you?

Code, one-command test run (Linux/WSL) and an example app: https://github.com/exelance25/thrubound. The README lists every limitation I know of.

Thanks — critical feedback especially welcome.
