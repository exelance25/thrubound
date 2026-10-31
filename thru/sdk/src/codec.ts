// Binary codec for the ThruBound program: instruction encoding, account and event decoding.
// Internal module: applications use the ThruBound client in client.ts, not these functions.
import { createHash } from "node:crypto";
import { deriveProgramAddress } from "@thru/sdk";
import { C, SEED_TAGS } from "./abi.generated.js";

export type Bytes = Uint8Array;

class W {
  private parts: number[] = [];
  u8(v: number) { this.parts.push(v & 0xff); return this; }
  u16(v: number) { this.parts.push(v & 0xff, (v >> 8) & 0xff); return this; }
  u32(v: number) { for (let i = 0; i < 4; i++) this.parts.push((v >>> (8 * i)) & 0xff); return this; }
  u64(v: bigint) {
    if (v < 0n || v > 0xffffffffffffffffn) throw new RangeError("u64 out of range");
    for (let i = 0n; i < 8n; i++) this.parts.push(Number((v >> (8n * i)) & 0xffn));
    return this;
  }
  key(k: Bytes) { if (k.length !== 32) throw new RangeError("key must be 32 bytes"); this.parts.push(...k); return this; }
  done(): Bytes { return Uint8Array.from(this.parts); }
}

class R {
  private o = 0;
  constructor(private b: Bytes) {}
  u8() { return this.b[this.o++]; }
  u16() { const v = this.b[this.o] | (this.b[this.o + 1] << 8); this.o += 2; return v; }
  u32() { const v = new DataView(this.b.buffer, this.b.byteOffset + this.o, 4).getUint32(0, true); this.o += 4; return v; }
  u64() { const v = new DataView(this.b.buffer, this.b.byteOffset + this.o, 8).getBigUint64(0, true); this.o += 8; return v; }
  key() { const k = this.b.slice(this.o, this.o + 32); this.o += 32; return k; }
  skip(n: number) { this.o += n; return this; }
  get offset() { return this.o; }
}

export const sha256 = (...parts: Bytes[]): Bytes => {
  const h = createHash("sha256");
  for (const p of parts) h.update(p);
  return new Uint8Array(h.digest());
};
const u64le = (v: bigint) => new W().u64(v).done();
const tag = (s: string) => new TextEncoder().encode(s);

// Program-defined addresses: the official @thru/sdk derivation sha256(program || 0 || seed).
export function pda(program: Bytes, seed: Bytes): Bytes {
  return deriveProgramAddress({ programAddress: program, seed, ephemeral: false }).bytes;
}
export const vaultSeed = (owner: Bytes, vaultId: bigint) => sha256(tag(SEED_TAGS.FS_SEED_TAG_VAULT), owner, u64le(vaultId));
export const agentSeed = (vault: Bytes, agent: Bytes) => sha256(tag(SEED_TAGS.FS_SEED_TAG_AGENT), vault, agent);
export const requestSeed = (vault: Bytes, agent: Bytes, nonce: bigint) =>
  sha256(tag(SEED_TAGS.FS_SEED_TAG_REQUEST), vault, agent, u64le(nonce));

// ------------------------------------------------------------------ transaction account lists
export interface TxShape { feePayer: Bytes; readWrite: Bytes[]; readOnly: Bytes[] }
const eq = (a: Bytes, b: Bytes) => a.length === b.length && a.every((x, i) => x === b[i]);
const cmp = (a: Bytes, b: Bytes) => { for (let i = 0; i < 32; i++) if (a[i] !== b[i]) return a[i] - b[i]; return 0; };
/** Canonical account lists per the official transaction rule ("Account List Verification"): no duplicate
 *  accounts anywhere, read-write and read-only each sorted ascending, the fee payer only at index 0. */
export function canonical(tx: TxShape): TxShape {
  const uniq = (xs: Bytes[], skip: Bytes[]) => xs.filter((x, i) => !skip.some((s) => eq(s, x)) && xs.findIndex((y) => eq(x, y)) === i);
  const readWrite = uniq(tx.readWrite, [tx.feePayer]).sort(cmp);
  const readOnly = uniq(tx.readOnly, [tx.feePayer, ...readWrite]).sort(cmp);
  return { feePayer: tx.feePayer, readWrite, readOnly };
}
/** Index of an account in a canonical transaction: 0 = fee payer, 1 = program, then read-write, then read-only. */
export function indexer(tx: TxShape) {
  const order: (Bytes | null)[] = [tx.feePayer, null, ...tx.readWrite, ...tx.readOnly];
  return (a: Bytes | null): number => {
    if (a === null) return C.FS_NO_ACCOUNT;
    const i = order.findIndex((x) => x !== null && eq(x, a));
    if (i < 0) throw new Error("account not in transaction");
    return i;
  };
}

// ------------------------------------------------------------------ instructions
export const ix = {
  initVault: (i: (a: Bytes | null) => number, vault: Bytes, owner: Bytes, mint: Bytes, vaultId: bigint, ttlNs: bigint) =>
    new W().u8(C.FS_OP_INIT_VAULT).u16(i(vault)).u16(i(owner)).key(mint).u64(vaultId).u64(ttlNs).u32(0).done(),
  bindToken: (i: (a: Bytes | null) => number, vault: Bytes, owner: Bytes, tokenAcct: Bytes, mint: Bytes | null) =>
    new W().u8(C.FS_OP_BIND_TOKEN).u16(i(vault)).u16(i(owner)).u16(i(tokenAcct)).u16(i(mint)).done(),
  setAgent: (i: (a: Bytes | null) => number, vault: Bytes, owner: Bytes, agentAcct: Bytes, agent: Bytes,
    l: { perTx: bigint; daily: bigint; budget: bigint; threshold: bigint; validUntilNs: bigint }, create: boolean) =>
    new W().u8(C.FS_OP_SET_AGENT).u16(i(vault)).u16(i(owner)).u16(i(agentAcct)).key(agent)
      .u64(l.perTx).u64(l.daily).u64(l.budget).u64(l.threshold).u64(l.validUntilNs).u8(create ? 1 : 0).u32(0).done(),
  revoke: (i: (a: Bytes | null) => number, vault: Bytes, owner: Bytes, agentAcct: Bytes) =>
    new W().u8(C.FS_OP_REVOKE).u16(i(vault)).u16(i(owner)).u16(i(agentAcct)).done(),
  setRecipient: (i: (a: Bytes | null) => number, vault: Bytes, owner: Bytes, agentAcct: Bytes, recipient: Bytes, allowed: boolean) =>
    new W().u8(C.FS_OP_SET_RECIPIENT).u16(i(vault)).u16(i(owner)).u16(i(agentAcct)).key(recipient).u8(allowed ? 1 : 0).done(),
  request: (i: (a: Bytes | null) => number, a: { vault: Bytes; agentAcct: Bytes; agent: Bytes; requestAcct: Bytes | null;
    vaultToken: Bytes; recipientToken: Bytes; tokenProgram: Bytes; nonce: bigint; amount: bigint }) =>
    new W().u8(C.FS_OP_REQUEST).u16(i(a.vault)).u16(i(a.agentAcct)).u16(i(a.agent)).u16(i(a.requestAcct))
      .u16(i(a.vaultToken)).u16(i(a.recipientToken)).u16(i(a.tokenProgram)).u64(a.nonce).u64(a.amount).u32(0).done(),
  approve: (i: (a: Bytes | null) => number, a: { vault: Bytes; owner: Bytes; agentAcct: Bytes; requestAcct: Bytes;
    vaultToken: Bytes; recipientToken: Bytes; tokenProgram: Bytes }, ap: Approval) =>
    new W().u8(C.FS_OP_APPROVE).u16(i(a.vault)).u16(i(a.owner)).u16(i(a.agentAcct)).u16(i(a.requestAcct))
      .u16(i(a.vaultToken)).u16(i(a.recipientToken)).u16(i(a.tokenProgram))
      .key(ap.vault).key(ap.agent).key(ap.recipient).key(ap.mint).u64(ap.amount).u64(ap.nonce).u64(ap.expiresNs).u8(ap.op).done(),
  reject: (i: (a: Bytes | null) => number, vault: Bytes, agentAcct: Bytes, requestAcct: Bytes, actor: Bytes) =>
    new W().u8(C.FS_OP_REJECT).u16(i(vault)).u16(i(agentAcct)).u16(i(requestAcct)).u16(i(actor)).done(),
  expire: (i: (a: Bytes | null) => number, vault: Bytes, agentAcct: Bytes, requestAcct: Bytes) =>
    new W().u8(C.FS_OP_EXPIRE).u16(i(vault)).u16(i(agentAcct)).u16(i(requestAcct)).done(),
  setPaused: (i: (a: Bytes | null) => number, vault: Bytes, owner: Bytes, paused: boolean) =>
    new W().u8(C.FS_OP_SET_PAUSED).u16(i(vault)).u16(i(owner)).u8(paused ? 1 : 0).done(),
  kill: (i: (a: Bytes | null) => number, vault: Bytes, owner: Bytes) =>
    new W().u8(C.FS_OP_KILL).u16(i(vault)).u16(i(owner)).done(),
  withdraw: (i: (a: Bytes | null) => number, vault: Bytes, owner: Bytes, vaultToken: Bytes, dest: Bytes, tokenProgram: Bytes, amount: bigint) =>
    new W().u8(C.FS_OP_WITHDRAW).u16(i(vault)).u16(i(owner)).u16(i(vaultToken)).u16(i(dest)).u16(i(tokenProgram)).u64(amount).done(),
};

// ------------------------------------------------------------------ accounts
export interface Approval { vault: Bytes; agent: Bytes; recipient: Bytes; mint: Bytes; amount: bigint; nonce: bigint; expiresNs: bigint; op: number }

export interface VaultState {
  flags: number; owner: Bytes; mint: Bytes; tokenAccount: Bytes; vaultId: bigint; approvalTtlNs: bigint; totalPaid: bigint; agentCount: number;
}
export function decodeVault(d: Bytes): VaultState {
  if (d.length !== 136) throw new Error("not a vault account");
  const r = new R(d);
  if (r.u32() !== C.FS_VAULT_MAGIC) throw new Error("bad vault magic");
  r.u8(); const flags = r.u8(); r.u16();
  return { flags, owner: r.key(), mint: r.key(), tokenAccount: r.key(), vaultId: r.u64(), approvalTtlNs: r.u64(), totalPaid: r.u64(), agentCount: r.u32() };
}

export interface AgentState {
  active: boolean; vault: Bytes; agent: Bytes; epoch: bigint; perTx: bigint; daily: bigint; budget: bigint; threshold: bigint;
  validUntilNs: bigint; day: bigint; dailyUsed: bigint; spent: bigint; reserved: bigint; nextNonce: bigint; recipients: Bytes[];
}
export function decodeAgent(d: Bytes): AgentState {
  if (d.length !== 416) throw new Error("not an agent account");
  const r = new R(d);
  if (r.u32() !== C.FS_AGENT_MAGIC) throw new Error("bad agent magic");
  r.u8(); const active = r.u8() === 1; const cnt = r.u8(); r.u8();
  const vault = r.key(), agent = r.key();
  const [epoch, perTx, daily, budget, threshold, validUntilNs, day, dailyUsed, spent, reserved, nextNonce] =
    Array.from({ length: 11 }, () => r.u64());
  const recipients = Array.from({ length: cnt }, () => r.key());
  return { active, vault, agent, epoch, perTx, daily, budget, threshold, validUntilNs, day, dailyUsed, spent, reserved, nextNonce, recipients };
}

export interface RequestState {
  status: number; vault: Bytes; agent: Bytes; recipient: Bytes; mint: Bytes; amount: bigint; nonce: bigint; epoch: bigint;
  day: bigint; createdNs: bigint; expiresNs: bigint;
}
export function decodeRequest(d: Bytes): RequestState {
  if (d.length !== 184) throw new Error("not a request account");
  const r = new R(d);
  if (r.u32() !== C.FS_REQ_MAGIC) throw new Error("bad request magic");
  r.u8(); const status = r.u8(); r.u16();
  return { status, vault: r.key(), agent: r.key(), recipient: r.key(), mint: r.key(), amount: r.u64(), nonce: r.u64(),
    epoch: r.u64(), day: r.u64(), createdNs: r.u64(), expiresNs: r.u64() };
}

export interface TokenAccountState { mint: Bytes; owner: Bytes; amount: bigint; frozen: boolean }
export function decodeTokenAccount(d: Bytes): TokenAccountState {
  if (d.length !== C.FS_TOKEN_ACCOUNT_SZ) throw new Error("not a token account");
  const r = new R(d);
  return { mint: r.key(), owner: r.key(), amount: r.u64(), frozen: r.u8() !== 0 };
}

// ------------------------------------------------------------------ events
export type ProgramEvent =
  | { kind: "paid"; agent: Bytes; recipient: Bytes; amount: bigint; nonce: bigint; approved: boolean }
  | { kind: "requested"; agent: Bytes; recipient: Bytes; amount: bigint; nonce: bigint; expiresNs: bigint }
  | { kind: "rejected" | "expired" | "invalidated"; agent: Bytes; nonce: bigint }
  | { kind: "agent_set" | "agent_revoked" | "recipient" | "vault_init" | "token_bound" | "paused" | "killed" | "withdrawn"; raw: Bytes };
export function decodeEvent(d: Bytes): ProgramEvent {
  const r = new R(d);
  const k = r.u8(); r.key(); /* vault */
  switch (k) {
    case C.FS_EV_PAID: { const agent = r.key(), recipient = r.key(); return { kind: "paid", agent, recipient, amount: r.u64(), nonce: r.u64(), approved: r.u8() === 1 }; }
    case C.FS_EV_REQUESTED: { const agent = r.key(), recipient = r.key(); return { kind: "requested", agent, recipient, amount: r.u64(), nonce: r.u64(), expiresNs: r.u64() }; }
    case C.FS_EV_REJECTED: return { kind: "rejected", agent: r.key(), nonce: r.u64() };
    case C.FS_EV_EXPIRED: return { kind: "expired", agent: r.key(), nonce: r.u64() };
    case C.FS_EV_INVALIDATED: return { kind: "invalidated", agent: r.key(), nonce: r.u64() };
    default: {
      const names: Record<number, ProgramEvent["kind"]> = { [C.FS_EV_VAULT_INIT]: "vault_init", [C.FS_EV_TOKEN_BOUND]: "token_bound",
        [C.FS_EV_AGENT_SET]: "agent_set", [C.FS_EV_AGENT_REVOKED]: "agent_revoked", [C.FS_EV_RECIPIENT]: "recipient",
        [C.FS_EV_PAUSED]: "paused", [C.FS_EV_KILLED]: "killed", [C.FS_EV_WITHDRAWN]: "withdrawn" };
      const kind = names[k];
      if (!kind) throw new Error(`unknown event kind ${k}`);
      return { kind, raw: d } as ProgramEvent;
    }
  }
}
