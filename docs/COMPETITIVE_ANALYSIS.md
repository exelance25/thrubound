# ThruBound — competitive analysis (2026-10-30)

Status words: **PASS · FAIL · BLOCKED · NOT RUN · NOT FOUND**. Every statement below comes from the source linked in its row. "Not documented" means the source does not say; it does not mean the feature is absent. Nothing here was installed or run, except where a row says so.

**Main finding.** Spending limits, allowlists, approval thresholds, expiry and on-chain enforcement for AI agents already exist in several products, including one live on a mainnet (Bursar on Robinhood Chain). On Thru specifically, the core **Rate Limiter** program already acts as a reusable, native policy gate in front of any target program. ThruBound therefore must **not** claim to be the first reusable Thru policy layer (see `PRODUCT_DIFFERENTIATION.md`).

## 1. Thru core programs (official mirror `Unto-Labs/thru` @ `a058dd8`, v0.4.2)

Sources:
- ABI files under `rpc/abi/type-library/`;
- TypeScript clients under `web/packages/programs/src/`;
- the bootstrap address list `web/packages/programs/src/bootstrap-addresses/`.

The C/Rust implementations of these programs are **not in the public mirror**. Behaviour is therefore known only from the ABI descriptions and the clients. It is not verified on a network, because the network is BLOCKED.

### 1.1 Rate Limiter — `thru.program.ratelimit` v0.1.0

**Address:** bootstrap address `taRATE6MTrtFFKY10oyskMcvokJs53iD5nWE8ZyUuGknMA` (source-documented).

**What it does.** The ABI description says it is a "Generic rate limiter that sits in front of a target program". CALL works like this:
1. It checks the forwarded instruction against a policy matcher.
2. It charges one call, plus the extracted amount, to one bucket per policy rule.
3. It invokes the target, with the policy (and optionally the policy's authority PDA) in its invoke authorization.

A target revert reverts the transaction, so quota is consumed only by successful calls.

**Policy:**
- admin, target program, `policy_id`, flags (PAUSED).
- **Matcher:** instruction size range; a selector (1–8 bytes at an offset); up to 4 **constraints** ("u16 account index at `idx_offset` must name account address `expected`").
- **Amount:** extracted from the forwarded instruction (`amount_sz` at `amount_offset`); `max_amount_per_call`.
- **Rules (up to 4):**
  - key kind: GLOBAL, FEE_PAYER, INSTR_ACCOUNT, or ATTESTED;
  - clock: SLOT or UNIX_SECONDS;
  - window, `max_calls`, `max_amount`.

**Accounts:**
- policy, bucket (`window_start`, `calls`, `amount`, `total_calls`, `total_amount`), authority PDA.
- A VERIFIED policy can only be created by the target's manager upgrade authority.

**Other features:**
- **Attester:** "attester must be authorized for ATTESTED rules".
- **Gate:** targets can require that they are called through the rate limiter (`GATE_NOT_RATE_LIMITED`, `tn_ratelimit_gate.h`; header not in the mirror).
- **Already used:** the faucet's withdrawals are "accepted only when the rate limiter invokes the faucet directly under a VERIFIED faucet policy" (`tn_faucet_program.abi.yaml`).

**What it already solves (per its ABI):**
- a reusable, program-level policy gate for any Thru program;
- per-call amount caps;
- periodic amount and call quotas, per caller or per account;
- a lifetime cap, approximable with a window longer than the clock value, since `window_start = now − now % window`;
- recipient pinning through constraints;
- pause; admin rotation;
- program-signed downstream calls through its authority PDA, so funds held by a token account owned by that PDA can move only through CALL;
- atomic quota consumption.

**What it does not demonstrably solve (per its ABI):**
- Permission **expiry**.
- A recipient **allowlist** with OR semantics sharing one budget: constraints are exact-match and ANDed, max 4.
- **Pending human approval** above a threshold, bound to the exact payload.
- Revocation that also invalidates in-flight approvals.
- Strict per-agent nonces.
- Exactly one authorized caller is not stated: whether CALL without an ATTESTED rule is open to anyone is not documented. The faucet use suggests it is.
- No public implementation source.
- No published verification of authority confinement, e.g. a policy without a selector would let the authority PDA call `burn` or `close_account`.

### 1.2 Passkey Manager — `thru.program.passkey_manager` v0.1.0

**Address:** `taPASSIvjIgz2kZ1CIIhvbT00XV9Ve5kZ2I9uDLanzIgbA`.

**What it is.** A smart wallet with up to N authorities:
- an authority is either a passkey (P-256) or a plain public key (the ABI says only "pubkey");
- each authority has `expires_at_block_time_seconds`.

**Instructions:** CREATE, VALIDATE, TRANSFER, ADD_AUTHORITY, REMOVE_AUTHORITY, REGISTER_CREDENTIAL.

**VALIDATE** verifies a WebAuthn signature over:

`SHA256("thru.passkey.validate" ‖ nonce ‖ wallet_idx ‖ auth_idx ‖ account_count ‖ accounts ‖ target_instruction)`

and then executes the target instruction ("validate-then-execute"). The challenge construction is in `passkey-manager/challenge.ts`.

**What it already solves:**
- passkey wallets;
- expiring authorities, i.e. session keys with an end time;
- exact-payload binding of a signed action to a nonce, the account list and the target instruction.

**What it does not solve:** amount limits, periodic budgets, or recipient restrictions per authority. While valid, an authority has the wallet's full power.

### 1.3 Other relevant Thru programs

**Token program** (`taTOKENKRgcl3vO0yVhftATDbXuhgWcfaaxv9xpEEdMdUE`):
- 8 instructions;
- no approve, delegate or permit instruction;
- `burn`, `close_account`, `freeze_account` and `thaw_account` each take an `authority_account_index` whose accepted authority is not documented.

**EOA program:** Ed25519-signed native transfers.

**Multicall:** batches instructions.

**Ecosystem projects outside the core repository: NOT CHECKED.** `thru.org` and its docs are unreachable from this environment (BLOCKED). No third-party Thru agent-payment project was found by web search.

## 2. Comparable products (outside Thru)

| Product | Existing features | Architecture | Solves | Does not demonstrably solve | Our difference | Sources |
|---|---|---|---|---|---|---|
| **Coinbase Agentic Wallets** | "Configurable caps per session and per transaction"; OFAC and KYT screening; email OTP sign-in; CLI and skills | Keys "stay in Coinbase infrastructure" (TEE per Decrypt). Base, Base Sepolia, Polygon, Solana. Launched about 2026-02-11 | Agent never holds the key; custodial guardrails; screening | Where limits are enforced (server vs. chain) is not documented; no allowlists documented; trust in Coinbase infrastructure; not on Thru | Enforcement in a Thru program anyone can verify; no custodian | [CDP docs](https://docs.cdp.coinbase.com/agentic-wallet/cli/welcome), [Decrypt](https://decrypt.co/357813/coinbase-launches-wallet-ai-agents-built-in-guardrails) |
| **Bursar** (bursar-world) | Mandates: per call / day / month / lifetime, expiry, provider allowlist and capabilities, approval threshold; SDK, MCP server, x402 facilitator, console; escrow and disputes | Contracts on **Robinhood Chain mainnet** (chain 4663), USDG; "a payment that exceeds them reverts there" | Nearly the full agent-mandate feature set, on chain, live with real funds (low caps) | Not on Thru; audit status deferred to SECURITY.md (not read); packages not on npm | Thru-native; authority-confinement verification; reproducible proof reports | [GitHub](https://github.com/bursar-world/bursar), [AgentKit PR #1554](https://github.com/coinbase/agentkit/pull/1554) |
| **Bursar** (Dami904, unrelated project with the same name) | Job budgets shared by agent teams, scoped keys with delegated sub-limits, 12 ordered checks, EIP-712 owner approval above a threshold, hash-chained audit log anchored on chain | Arc testnet; JobVault + AuditAnchor; per-agent rules **in the API**, job-wide rules on chain | Team budgets, approvals, tamper-evident log | Per-agent limits are off chain (stated); testnet only | All limits on chain; Thru-native | [GitHub](https://github.com/Dami904/bursar) |
| **PayGuard** | Natural-language one-time and recurring USDC payments; scheduler; dashboard | Python/Streamlit/LangGraph agent; Arbitrum Sepolia; no contracts described | Payment automation UX | No spending limits, allowlists or approvals documented; key handling not documented; hackathon | Program-enforced limits | [HackQuest](https://hackquest.io/en/projects/PayGuard), [GitHub](https://github.com/Ubaibe/PayGuard) |
| **Accord Protocol** | Per-owner, per-token spending limits over a window, checked at proposal creation and execution (issue #761, closed as completed in PR #866) | Rust contract (`contracts/accord/src/lib.rs`); the "Stellar Wave" label suggests Stellar, not confirmed | Multi-owner proposal flow with spend windows | Repository page not reachable (allowlist), so features beyond the issue are unknown | Thru-native; agent delegation | [Issue #761](https://github.com/Ac0rdP/AccordProtocol/issues/761) |
| **PolicyVault** | `withdraw` (agent-only, allowlisted recipients, daily cap), `setFrozen`, `emergencyWithdraw` (owner, bypasses limits) | Solidity, Base Sepolia, native ETH only; x402 hackathon | Single-agent on-chain vault with daily cap and allowlist | No per-transaction limit; UTC-day clustering (documented); owner bypass by design; testnet | Per-tx, period and lifetime limits; approvals; Thru | [Docs](https://www.mintlify.com/Aypp23/x402-hackathon/contracts/policy-vault) |
| **Fiscus** | **NOT FOUND**: searches returned unrelated projects named Fiscus (a financial research assistant, household finance, and fiscusai.org "human-in-the-loop finance automation", whose site could not be fetched). No agent-spending product named Fiscus was identified | — | — | — | — | [Fiscus-AI org](https://github.com/Fiscus-AI/.github), [workflow fixtures](https://github.com/hakkiyuvanc/fiscus-ai-financial-workflow-fixtures). The intended product's link is needed |

Also seen but not analysed: [Fireblocks x402 spending controls](https://developers.fireblocks.com/docs/x402-agent-spending-controls), [Circle agent wallets](https://developers.circle.com/agent-stack/agent-wallets.md), [Biconomy policies](https://docs.biconomy.io/agents-automation/policies), [PolicyLayer](https://policylayer.com/docs/reference/policy-controls), [ERC-8196](https://ercs.ethereum.org/ERCS/erc-8196), [AWS AgentCore payments](https://aws.amazon.com/blogs/machine-learning/enable-safe-agentic-payments-with-built-in-guardrails-using-amazon-bedrock-agentcore-payments/).

## 3. Feature matrix (✔ documented · ✘ documented absent · ? not documented)

| | Per-tx | Period | Lifetime | Expiry | Recipient allowlist | Human approval | On-chain | Thru | Public verification of confinement |
|---|---|---|---|---|---|---|---|---|---|
| Coinbase Agentic Wallets | ✔ | ✔ (session) | ? | ? | ? | ? | ? | ✘ | ? |
| Bursar (bursar-world) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✘ | ? |
| Bursar (Dami904) | ✔ | ✔ | ? | ? | ✔ | ✔ | partly | ✘ | ? |
| PolicyVault | ✘ | ✔ | ? | ✘ | ✔ | ✘ | ✔ | ✘ | ? |
| Thru Rate Limiter | ✔ | ✔ | ≈ (long window) | ✘ | one exact recipient per constraint | ✘ | ✔ | ✔ | ✘ |
| Thru Passkey Manager | ✘ | ✘ | ✘ | ✔ (per authority) | ✘ | ✔ (passkey signs exact payload) | ✔ | ✔ | ✘ |
| Flowstate on Thru (this repo) | ✔ | ✔ | ✔ | ✔ | ✔ (8, shared budget) | ✔ | ✔ (simulation only) | ✔ (not deployed) | partial (simulation) |

## 4. Name check — "ThruBound" (provisional)

| Check | Result |
|---|---|
| npm `thrubound`, `@thrubound/sdk`, `thru-bound` | **free** (404 from registry.npmjs.org, 2026-10-30) |
| GitHub `thrubound/thrubound`, `ThruBound/ThruBound` | no public repository found (git ls-remote asked for credentials, which GitHub does for non-existent repositories) |
| Web search "ThruBound" | no product found |
| Domain, trademark | **NOT RUN**: cannot be checked from this environment |
