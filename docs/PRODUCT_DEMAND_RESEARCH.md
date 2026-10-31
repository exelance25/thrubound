# ThruBound — product demand research (2026-10-31)

> **No user interviews were conducted. Demand is NOT validated.**

Everything below comes from public sources, the official Thru repository and docs, and Thru's GitHub issue tracker. A use case marked "fits" means ThruBound's design could serve it, **not** that anyone has asked for it.

## 1. Signals checked

| Signal | Finding | Source |
|---|---|---|
| Thru stage | Alphanet. The team leads "with native applications". No third-party teams building on Thru are named. The only community project found is an explorer (ThruScan) | [Quanta Lab: Introduction to Thru](https://greyy.substack.com/p/thru) |
| Funding and positioning | Unto Labs raised $14.4M; a general-purpose RISC-V L1 for mainstream developers | [Fortune](https://fortune.com/crypto/2025/04/29/unto-labs-fundraising-framework-ventures-electric-capital/), [NFTgators](https://www.nftgators.com/unto-labs-raises-14-4-million-for-new-layer-1-blockchain-thru/) |
| Developer requests | 77 issues and PRs in `Unto-Labs/thru` (read through the GitHub API, 2026-10-31). **None** asks for agent permissions, spending limits, delegation or allowances. Wallet-related items concern signing sessions (expiry validation, docs) and key hardening | [Unto-Labs/thru issues](https://github.com/Unto-Labs/thru/issues), e.g. [#71](https://github.com/Unto-Labs/thru/issues/71) |
| Official pattern for repeated automated actions | Wallet **signing sessions**: temporary session keys that sign any transaction intent for the wallet. They are revocable, and no amount, recipient or program limit is documented | thru.org/docs, Signing Sessions |
| Market outside Thru | Agent spending caps are becoming standard elsewhere: Coinbase Agentic Wallets, Bursar, Squads, Turnkey, ZeroDev; Cloudflare Wallets (announced 2026-08-04) gives agents a total cap, a merchant allowlist and a per-transaction maximum, enforced at the network layer | `COMPETITIVE_ANALYSIS.md`, `COMPETITIVE_GAP_REVIEW.md`, [ai2.work on Cloudflare Wallets](https://ai2.work/blog/cloudflare-wallets-give-ai-agents-spending-caps-and-payment-id) |

## 2. Use cases (12)

| # | Potential user / project | What they need | Today | ThruBound fit |
|---|---|---|---|---|
| 1 | Thru app using **wallet signing sessions** for repeated actions | Let an app or agent act repeatedly without giving full wallet power | Session key with full power until expiry | **Fits**: a bounded allowance instead of an unbounded session (token payments only) |
| 2 | AI agent paying APIs or vendors in a Thru token | Per-payment, daily and total caps, vendor allowlist, human above a threshold | No Thru-native product found | **Fits** (the core design) |
| 3 | Team treasury or payroll automation with approval above a threshold | Bot pays listed recipients; humans approve large items | Manual, or a custom program | **Fits** |
| 4 | Passkey-wallet users granting an app limited spending | Owner approves with a passkey | Passkey Manager: authorities have expiry but no limits | **Fits** via Passkey Manager `invoke` (designed, not executed) |
| 5 | Subscription or recurring payments to a fixed merchant | Recurring transfer within a cap | Session key or manual | **Partly**: caps fit; ThruBound has no scheduler (the agent triggers) |
| 6 | **Faucet** (official) | Per-identity, per-interval withdrawal caps | **Rate Limiter** (VERIFIED faucet policy) | **No added value**: already solved |
| 7 | Trading bots on the official **AMM / CLOB** | Limit what a bot can trade per window | Rate Limiter (arbitrary targets) or nothing | **Does not fit**: ThruBound only authorises token transfers, not calls to other programs |
| 8 | **NFT market** purchases by an agent | Spend caps on purchases | — | **Does not fit** (needs calling the NFT market program) |
| 9 | **Registrar / name-service** renewals by automation | Renew leases within a budget | — | **Does not fit** as-is (registrar instruction, not a token transfer) |
| 10 | Spending **native THRU** (fees, EOA transfers) | Caps on native balance | — | **Does not fit**: ThruBound covers token-program tokens only |
| 11 | Developers or auditors of any Thru custody setup | "Who can move these funds?" before depositing | Manual reading of ABIs | **Fits**: the **authority analyzer** works for ThruBound vaults, plain token accounts and Rate Limiter custody |
| 12 | Rate Limiter users | Check that a policy is not dangerously configured (no selector, no destination constraint, unrestricted callers, admin key) | Manual | **Fits** (analyzer; ABI-level, implementation not public) |

## 3. Answers

**Who has the problem?**
- Thru application developers who automate payments: use cases 1–5.
- Anyone holding funds under a program or policy on Thru: use cases 11–12.

We could not find any such developer who has publicly stated the problem.

**How do they solve it today?**
- Wallet signing sessions, which have no limits.
- Passkey Manager authorities with expiry.
- The Rate Limiter, which is generic but low-level, and undocumented in the official docs.
- Custom programs.
- Off Thru: custodial or enclave policy engines and on-chain mandates.

**What cost or risk does ThruBound reduce?**
- **Blast radius:** a leaked agent or session key can lose at most its remaining allowance, instead of the wallet.
- **Review cost:** the authority report replaces reading ABIs to learn who else can move the funds, and it labels unverifiable assumptions explicitly.
- **Approval risk:** an approval cannot be replayed, altered, or executed after revocation (proved on the model).

**Why is the Rate Limiter alone not enough?**
- No expiry.
- No pending human approval.
- No several-recipients-one-budget.
- Revocation does not cancel queued items.
- The admin can rewrite everything.
- Configuring it safely needs byte offsets and selectors.

It is, however, **better than ThruBound for arbitrary program calls and windowed quotas** (use cases 7–9), and **already serves the faucet**.

**Which feature would make another developer integrate ThruBound?**

The evidence points to two features:
1. a **bounded replacement for signing sessions**: give an agent an allowance, not the wallet;
2. the **authority analyzer**, which is useful even to developers who never use ThruBound's program.

## 4. Verdict

- **Problem real:** plausible. Thru's own docs recommend unbounded session keys for repeated actions.
- **Demand:** not validated. No requests in the Thru tracker, an early ecosystem, and no interviews.
- **Scope:** ThruBound's program fits token-payment use cases only. Most other agent actions on Thru need arbitrary program calls, where the Rate Limiter is the right base.
- **Recommendation:**
  - Do **not** add features.
  - Present the analyzer and the bounded allowance to Thru developers (Unto Labs, the Thru community) and ask the questions in `DEVELOPER_ONBOARDING_TEST.md` §"What a real external test should measure".
  - Run the network checks once access exists.
