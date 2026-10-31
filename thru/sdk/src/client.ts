// ThruBound client: the public developer interface. "Give agents permission, not power."
import { Pubkey } from "@thru/sdk";
import { C } from "./abi.generated.js";
import {
  agentSeed, canonical, decodeAgent, decodeEvent, decodeRequest, decodeTokenAccount, decodeVault, indexer, ix, pda, requestSeed,
  vaultSeed, type AgentState, type Approval, type Bytes, type ProgramEvent,
} from "./codec.js";
import { errorName, predictRequest, remaining, type Decision } from "./policy.js";
import type { Transport } from "./transport.js";
import { analyzeTokenAccount, analyzeVault, type AuthorityReport } from "./authority.js";

/** A Thru address: "ta…" text form, hex, or 32 raw bytes. */
export type Address = string | Uint8Array;
const bytes = (a: Address): Bytes => {
  if (a instanceof Uint8Array) { if (a.length !== 32) throw new TypeError("an address must be 32 bytes"); return a; }
  try { return Pubkey.from(a).toBytes(); }
  catch { throw new TypeError(`not a Thru address: ${JSON.stringify(a)} (expected a "ta…" address, 64 hex characters or 32 bytes)`); }
};
/** Token amounts, ids, nonces and times are u64 values and must be BigInt (e.g. 10n, not 10). */
function u64(name: string, v: unknown): bigint {
  if (typeof v !== "bigint") throw new TypeError(`${name} must be a BigInt (for example 10n), got ${typeof v}`);
  if (v < 0n || v > 0xffffffffffffffffn) throw new RangeError(`${name} must fit in u64 (0 … 2^64-1)`);
  return v;
}
const text = (b: Bytes): string => Pubkey.from(b).toThruFmt();

export interface Limits {
  /** Maximum per payment, in token base units. */
  perTransaction: bigint;
  /** Maximum per UTC day. */
  perDay: bigint;
  /** Maximum over the permission's lifetime (spent + pending). */
  lifetime: bigint;
  /** Payments above this need the owner's approval (0 = every payment needs approval). */
  approvalAbove: bigint;
  /** Permission expiry, Unix time in seconds. */
  expiresAt: bigint;
}

export interface Receipt {
  ok: boolean;
  /** "paid" (instant), "pending" (waiting for owner approval), "approved" (paid after approval), or "refused". */
  outcome: "paid" | "pending" | "approved" | "refused" | "done";
  /** Program error name when refused (e.g. "PER_TX", "DAILY", "RECIPIENT_NOT_ALLOWED"). */
  reason: string | null;
  code: number;
  nonce?: bigint;
  events: ProgramEvent[];
  /** Always "local-simulation" until a network transport exists. Never a real chain transaction. */
  environment: Transport["kind"];
}

export interface Permission {
  vault: string; agent: string; active: boolean; epoch: bigint;
  limits: Limits; recipients: string[];
  spent: bigint; pending: bigint; nextNonce: bigint;
  remaining: { today: bigint; lifetime: bigint; perTransaction: bigint };
}

export interface PendingRequest { nonce: bigint; recipient: string; amount: bigint; expiresAt: bigint; status: string }

const STATUS = ["none", "pending", "executed", "rejected", "expired", "invalidated"];

export class ThruBound {
  constructor(private readonly transport: Transport) {}

  get environment() { return this.transport.kind; }
  get programAddress() { return text(this.transport.programAddress); }

  // ------------------------------------------------------------------ addresses
  vaultAddress(owner: Address, vaultId: bigint): string { return text(this.vaultBytes(owner, vaultId)); }
  permissionAddress(vault: Address, agent: Address): string { return text(this.agentAcct(bytes(vault), bytes(agent))); }
  private vaultBytes(owner: Address, vaultId: bigint) { return pda(this.transport.programAddress, vaultSeed(bytes(owner), vaultId)); }
  private agentAcct(v: Bytes, agent: Bytes) { return pda(this.transport.programAddress, agentSeed(v, agent)); }
  private requestAcct(v: Bytes, agent: Bytes, nonce: bigint) { return pda(this.transport.programAddress, requestSeed(v, agent, nonce)); }

  private async exec(feePayer: Bytes, readWrite: Bytes[], readOnly: Bytes[], build: (i: ReturnType<typeof indexer>) => Bytes,
    label: string, outcome: Receipt["outcome"] = "done", nonce?: bigint): Promise<Receipt> {
    const tx = canonical({ feePayer, readWrite, readOnly });
    const res = await this.transport.send({ ...tx, data: build(indexer(tx)), label });
    const events = res.events.map(decodeEvent);
    const ok = res.code === 0;
    return { ok, outcome: ok ? outcome : "refused", reason: ok ? null : errorName(res.code), code: res.code, nonce, events,
      environment: this.transport.kind };
  }

  // ------------------------------------------------------------------ owner: set up
  /** Create a vault (one token, one owner). Approval requests expire after `approvalTtlSeconds`. */
  async createVault(p: { owner: Address; vaultId: bigint; mint: Address; approvalTtlSeconds?: bigint }) {
    u64("vaultId", p.vaultId); if (p.approvalTtlSeconds !== undefined) u64("approvalTtlSeconds", p.approvalTtlSeconds);
    const owner = bytes(p.owner), v = this.vaultBytes(owner, p.vaultId);
    const r = await this.exec(owner, [v], [], (i) => ix.initVault(i, v, owner, bytes(p.mint), p.vaultId,
      (p.approvalTtlSeconds ?? 86_400n) * 1_000_000_000n), "init_vault");
    return { ...r, vault: text(v) };
  }

  /** Bind the vault's token account (owned by the vault address). Passing `mint` also proves on chain
   *  that the mint has no freeze authority, which closes the freeze path (see KSI-1 trust model). */
  async bindTokenAccount(p: { owner: Address; vault: Address; tokenAccount: Address; mint?: Address }) {
    const owner = bytes(p.owner), v = bytes(p.vault), t = bytes(p.tokenAccount), m = p.mint ? bytes(p.mint) : null;
    return this.exec(owner, [v], m ? [t, m] : [t], (i) => ix.bindToken(i, v, owner, t, m), "bind_token");
  }

  /** Give an agent a bounded permission (creates it, or changes its limits). Limits can never be set
   *  below what the agent has already used (CE-1). */
  async grantAgent(p: { owner: Address; vault: Address; agent: Address; limits: Limits; recipients?: Address[] }) {
    for (const k of ["perTransaction", "perDay", "lifetime", "approvalAbove", "expiresAt"] as const) u64(`limits.${k}`, p.limits?.[k]);
    const owner = bytes(p.owner), v = bytes(p.vault), agent = bytes(p.agent), a = this.agentAcct(v, agent);
    const exists = (await this.transport.getAccount(a)) !== null;
    const l = { perTx: p.limits.perTransaction, daily: p.limits.perDay, budget: p.limits.lifetime,
      threshold: p.limits.approvalAbove, validUntilNs: p.limits.expiresAt * 1_000_000_000n };
    const r = await this.exec(owner, [v, a], [], (i) => ix.setAgent(i, v, owner, a, agent, l, !exists), "set_agent");
    if (!r.ok) return r;
    for (const rec of p.recipients ?? []) {
      const rr = await this.allowRecipient({ owner, vault: v, agent, recipient: rec });
      if (!rr.ok) return rr;
    }
    return r;
  }

  async allowRecipient(p: { owner: Address; vault: Address; agent: Address; recipient: Address; allowed?: boolean }) {
    const owner = bytes(p.owner), v = bytes(p.vault), a = this.agentAcct(v, bytes(p.agent));
    return this.exec(owner, [a], [v], (i) => ix.setRecipient(i, v, owner, a, bytes(p.recipient), p.allowed ?? true), "set_recipient");
  }

  /** Revoke: the agent can no longer request, and every pending request of its current epoch can never execute. */
  async revokeAgent(p: { owner: Address; vault: Address; agent: Address }) {
    const owner = bytes(p.owner), v = bytes(p.vault), a = this.agentAcct(v, bytes(p.agent));
    return this.exec(owner, [a], [v], (i) => ix.revoke(i, v, owner, a), "revoke");
  }
  async pause(p: { owner: Address; vault: Address; paused: boolean }) {
    const owner = bytes(p.owner), v = bytes(p.vault);
    return this.exec(owner, [v], [], (i) => ix.setPaused(i, v, owner, p.paused), "set_paused");
  }
  /** Irreversible emergency stop. The owner can still withdraw. */
  async emergencyStop(p: { owner: Address; vault: Address }) {
    const owner = bytes(p.owner), v = bytes(p.vault);
    return this.exec(owner, [v], [], (i) => ix.kill(i, v, owner), "kill");
  }
  async withdraw(p: { owner: Address; vault: Address; destination: Address; amount: bigint }) {
    u64("amount", p.amount);
    const owner = bytes(p.owner), v = bytes(p.vault), dest = bytes(p.destination);
    const vt = (await this.vaultState(v)).tokenAccount, tp = this.transport.tokenProgramAddress;
    return this.exec(owner, [v, vt, dest], [tp], (i) => ix.withdraw(i, v, owner, vt, dest, tp, p.amount), "withdraw");
  }

  // ------------------------------------------------------------------ agent: act
  /** Ask to pay `amount` to `recipient` (a token account). At or below the approval threshold it is paid
   *  in the same transaction; above it, it waits for the owner. Uses the agent's next nonce by default. */
  async requestPayment(p: { agent: Address; vault: Address; recipient: Address; amount: bigint; nonce?: bigint }): Promise<Receipt> {
    u64("amount", p.amount); if (p.nonce !== undefined) u64("nonce", p.nonce);
    const agent = bytes(p.agent), v = bytes(p.vault), rec = bytes(p.recipient), a = this.agentAcct(v, agent);
    const vs = await this.vaultState(v);
    const as = await this.agentStateOrNull(v, agent);
    const nonce = p.nonce ?? as?.nextNonce ?? 0n;
    const pending = as !== null && p.amount > as.threshold;
    const req = pending ? this.requestAcct(v, agent, nonce) : null;
    const tp = this.transport.tokenProgramAddress;
    const rw = [v, a, vs.tokenAccount, rec, ...(req ? [req] : [])];
    const r = await this.exec(agent, rw, [tp], (i) => ix.request(i, { vault: v, agentAcct: a, agent, requestAcct: req,
      vaultToken: vs.tokenAccount, recipientToken: rec, tokenProgram: tp, nonce, amount: p.amount }), "request",
      pending ? "pending" : "paid", nonce);
    return r;
  }

  // ------------------------------------------------------------------ owner: decide
  /** Approve one pending request. The approval names every field of the request; if anything differs,
   *  the program refuses (APPROVAL_MISMATCH). */
  async approve(p: { owner: Address; vault: Address; agent: Address; nonce: bigint }): Promise<Receipt> {
    u64("nonce", p.nonce);
    const owner = bytes(p.owner), v = bytes(p.vault), agent = bytes(p.agent);
    const a = this.agentAcct(v, agent), reqAcct = this.requestAcct(v, agent, p.nonce);
    const acc = await this.transport.getAccount(reqAcct);
    if (!acc) return { ok: false, outcome: "refused", reason: "NO_PENDING", code: C.FS_ERR_NO_PENDING, nonce: p.nonce, events: [], environment: this.transport.kind };
    const rq = decodeRequest(acc.data);
    const vs = await this.vaultState(v), tp = this.transport.tokenProgramAddress;
    const ap: Approval = { vault: rq.vault, agent: rq.agent, recipient: rq.recipient, mint: rq.mint, amount: rq.amount,
      nonce: rq.nonce, expiresNs: rq.expiresNs, op: C.FS_OP_APPROVE };
    return this.exec(owner, [v, a, reqAcct, vs.tokenAccount, rq.recipient], [tp], (i) => ix.approve(i, { vault: v, owner,
      agentAcct: a, requestAcct: reqAcct, vaultToken: vs.tokenAccount, recipientToken: rq.recipient, tokenProgram: tp }, ap),
      "approve", "approved", p.nonce);
  }
  /** Reject a pending request (the owner, or the agent withdrawing its own request). */
  async reject(p: { actor: Address; vault: Address; agent: Address; nonce: bigint }) {
    const actor = bytes(p.actor), v = bytes(p.vault), agent = bytes(p.agent);
    const a = this.agentAcct(v, agent), req = this.requestAcct(v, agent, p.nonce);
    return this.exec(actor, [a, req], [v], (i) => ix.reject(i, v, a, req, actor), "reject", "done", p.nonce);
  }
  /** Anyone may close a request whose deadline passed, or one made stale by a revocation. */
  async expire(p: { caller: Address; vault: Address; agent: Address; nonce: bigint }) {
    const caller = bytes(p.caller), v = bytes(p.vault), agent = bytes(p.agent);
    const a = this.agentAcct(v, agent), req = this.requestAcct(v, agent, p.nonce);
    return this.exec(caller, [a, req], [v], (i) => ix.expire(i, v, a, req), "expire", "done", p.nonce);
  }

  // ------------------------------------------------------------------ read
  async getPermission(vault: Address, agent: Address): Promise<Permission | null> {
    const v = bytes(vault), as = await this.agentStateOrNull(v, bytes(agent));
    if (!as) return null;
    const now = await this.transport.now();
    return { vault: text(as.vault), agent: text(as.agent), active: as.active, epoch: as.epoch,
      limits: { perTransaction: as.perTx, perDay: as.daily, lifetime: as.budget, approvalAbove: as.threshold,
        expiresAt: as.validUntilNs / 1_000_000_000n },
      recipients: as.recipients.map(text), spent: as.spent, pending: as.reserved, nextNonce: as.nextNonce,
      remaining: remaining(as, now) };
  }
  async getPendingRequests(vault: Address, agent: Address): Promise<PendingRequest[]> {
    const v = bytes(vault), ag = bytes(agent), as = await this.agentStateOrNull(v, ag);
    const out: PendingRequest[] = [];
    for (let n = 0n; as && n < as.nextNonce; n++) {
      const acc = await this.transport.getAccount(this.requestAcct(v, ag, n));
      if (!acc) continue;
      const r = decodeRequest(acc.data);
      out.push({ nonce: r.nonce, recipient: text(r.recipient), amount: r.amount, expiresAt: r.expiresNs / 1_000_000_000n, status: STATUS[r.status] ?? "?" });
    }
    return out;
  }
  async getVault(vault: Address) {
    const vs = await this.vaultState(bytes(vault));
    const tok = await this.transport.getAccount(vs.tokenAccount);
    return { owner: text(vs.owner), mint: text(vs.mint), tokenAccount: vs.tokenAccount.some((b) => b) ? text(vs.tokenAccount) : null,
      balance: tok ? decodeTokenAccount(tok.data).amount : null, totalPaid: vs.totalPaid,
      paused: (vs.flags & C.FS_VAULT_PAUSED) !== 0, stopped: (vs.flags & C.FS_VAULT_KILLED) !== 0,
      mintUnfreezable: (vs.flags & C.FS_VAULT_MINT_UNFREEZABLE) !== 0 };
  }
  async getTokenBalance(tokenAccount: Address) {
    const acc = await this.transport.getAccount(bytes(tokenAccount));
    return acc ? decodeTokenAccount(acc.data).amount : null;
  }

  /** Predict the program's policy decision for a request, without sending anything. Covers the
   *  policy rules only (not signer authorization or token balances); the program stays the authority. */
  async check(p: { vault: Address; agent: Address; recipient: Address; amount: bigint; nonce?: bigint }): Promise<Decision> {
    const v = bytes(p.vault), vs = await this.vaultStateOrNull(v), as = await this.agentStateOrNull(v, bytes(p.agent));
    return predictRequest(vs, as, v, { recipient: bytes(p.recipient), amount: p.amount, nonce: p.nonce ?? as?.nextNonce ?? 0n,
      nowNs: await this.transport.now() });
  }

  /** Proof Lab: read the raw on-chain state of a vault into the snapshot format checked by the
   *  independent verifier (thru/verifier/verify_thru.py). `fundedTotal` is the total ever deposited. */
  async exportProofLabSnapshot(p: { vault: Address; agents: Address[]; tokenAccounts: Address[]; fundedTotal: bigint }) {
    const hex = (b: Bytes) => Buffer.from(b).toString("hex");
    const v = bytes(p.vault), vs = await this.vaultState(v);
    const agents: Record<string, object> = {}, requests: Record<string, Record<string, string>> = {};
    for (const ag of p.agents.map(bytes)) {
      const s = await this.agentStateOrNull(v, ag);
      if (!s) continue;
      agents[hex(ag)] = { spent: s.spent, reserved: s.reserved, next_nonce: s.nextNonce, epoch: s.epoch, active: s.active ? 1 : 0,
        daily_used: s.dailyUsed, day: s.day, budget: s.budget, daily: s.daily, recipients: s.recipients.map(hex) };
      requests[hex(ag)] = {};
      for (let n = 0n; n < s.nextNonce; n++) {
        const acc = await this.transport.getAccount(this.requestAcct(v, ag, n));
        if (acc) requests[hex(ag)][n.toString()] = hex(acc.data);
      }
    }
    const balances: Record<string, bigint> = {};
    for (const t of [vs.tokenAccount, ...p.tokenAccounts.map(bytes)]) {
      const acc = await this.transport.getAccount(t);
      if (acc) balances[hex(t)] = decodeTokenAccount(acc.data).amount;
    }
    return { vault: hex(v), vault_token: hex(vs.tokenAccount), funded: p.fundedTotal, owner: hex(vs.owner),
      vault_state: { flags: vs.flags, total_paid: vs.totalPaid }, vault_token_balance: balances[hex(vs.tokenAccount)],
      agents, requests, token_balances: balances };
  }

  /** Proof Lab: which authorities, accounts and programs can move (or block) this vault's tokens.
   *  Pass every agent of the vault; findings are VERIFIED only on official sources or real chain data. */
  async analyzeAuthorities(p: { vault: Address; agents: Address[] }): Promise<AuthorityReport> {
    const v = bytes(p.vault);
    return analyzeVault(this.transport, v, p.agents.map(bytes), (a) => this.agentAcct(v, a), (a, n) => this.requestAcct(v, a, n));
  }
  /** Proof Lab for any token account (not only ThruBound vaults). Give the Rate Limiter program and
   *  policy if the account is held by a Rate Limiter authority PDA. */
  async analyzeTokenAccount(p: { tokenAccount: Address; ratelimit?: { program: Address; policy: Address } }): Promise<AuthorityReport> {
    return analyzeTokenAccount(this.transport, bytes(p.tokenAccount),
      p.ratelimit ? { ratelimitProgram: bytes(p.ratelimit.program), ratelimitPolicy: bytes(p.ratelimit.policy) } : {});
  }

  // ------------------------------------------------------------------ internal
  private async vaultStateOrNull(v: Bytes) {
    const acc = await this.transport.getAccount(v);
    return acc ? decodeVault(acc.data) : null;
  }
  private async vaultState(v: Bytes) {
    const s = await this.vaultStateOrNull(v);
    if (!s) throw new Error("vault not found");
    return s;
  }
  private async agentStateOrNull(v: Bytes, agent: Bytes): Promise<AgentState | null> {
    const acc = await this.transport.getAccount(this.agentAcct(v, agent));
    return acc ? decodeAgent(acc.data) : null;
  }
}
