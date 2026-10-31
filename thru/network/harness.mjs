// ThruBound network harness (browser). Runs ONLY against the Thru ALPHANET test network.
// Test keys are generated in the page, live only in this closure, and are never returned, exported or logged.
// Only test assets are used: native THRU from the official faucet and a test mint created here.
import { createThruClient } from "@thru/sdk/client";
import { decodeAddress, encodeAddress } from "@thru/sdk/helpers";
import { StateProofType } from "@thru/sdk/proto";
import * as boot from "@thru/programs/bootstrap-addresses";
import * as token from "@thru/programs/token";
import { createFaucetWithdrawInstruction } from "@thru/programs/faucet";
import { deployProgram, inspectProgramDeployment } from "@thru/programs/deploy";

export const RPC = "https://rpc.alphanet.thru.org";
const thru = createThruClient({ baseUrl: RPC });
const P = boot.BOOTSTRAP_PROGRAM_ADDRESSES;
const TOKEN = P.token;

const K = {};                 // name -> { address, publicKey, privateKey }  (private keys never leave)
const A = {};                 // name -> address string (public)
const LOG = [];
const hex = (b) => [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
const json = (v) => JSON.parse(JSON.stringify(v, (_, x) => (typeof x === "bigint" ? x.toString() : x instanceof Uint8Array ? "0x" + hex(x) : x)));
const sigStr = (s) => (typeof s === "string" ? s : s?.toThruFmt?.() ?? s?.toString?.() ?? String(s));

// ------------------------------------------------------------------ keys and accounts
export async function newKeys(names) {
  for (const n of names) {
    const kp = await thru.keys.generateKeyPair();
    K[n] = kp; A[n] = kp.address;
  }
  return json(A);
}
export const addresses = () => json(A);

async function track(wire) {
  let last = null;
  for await (const u of thru.transactions.sendAndTrack(wire, { timeoutMs: 60000 })) {
    last = u;
    if (u.executionResult) break;
  }
  return last;
}
function summarize(label, signature, u) {
  const r = u?.executionResult;
  const out = { label, signature: sigStr(signature), status: u?.status, vmError: r?.vmError, userErrorCode: r?.userErrorCode,
    computeUnits: r?.consumedComputeUnits, ok: !!r && r.vmError === 0 && (r.userErrorCode ?? 0n) === 0n };
  LOG.push(json(out));
  return json(out);
}

export async function createEoa(name) {
  const tx = await thru.accounts.create({ publicKey: K[name].publicKey });
  const sig = await tx.sign(K[name].privateKey);
  const u = await track(tx.toWire());
  return summarize(`create EOA ${name}`, sig, u);
}

/** Build, sign (fee payer = signer) and send one instruction; data(ctx) gets the official account ordering. */
export async function send(label, signer, program, readWrite, readOnly, data, header) {
  const built = await thru.transactions.buildAndSign({
    feePayer: { publicKey: K[signer].publicKey, privateKey: K[signer].privateKey },
    program, accounts: { readWrite, readOnly }, instructionData: data, header,
  });
  const u = await track(built.rawTransaction);
  return summarize(label, built.signature, u);
}

export async function faucet(name, amount = 10000n, fee = 0n) {
  const vault = boot.BOOTSTRAP_FAUCET_VAULT_ADDRESS;
  return send(`faucet native ${amount} -> ${name} (fee ${fee})`, name, P.faucet, [vault, A[name]], [],
    createFaucetWithdrawInstruction({ vault, recipient: A[name], amount: BigInt(amount) }), { fee: BigInt(fee) });
}

export async function account(addr) {
  try {
    const a = await thru.accounts.get(addr);
    return json({ addr, exists: true, owner: a.meta?.owner?.toThruFmt?.() ?? null, size: a.meta?.dataSize,
      balance: a.meta?.balance, nonce: a.meta?.nonce, flags: a.meta?.flags, data: a.data?.data ? hex(a.data.data) : null });
  } catch (e) { return { addr, exists: false, err: String(e?.message ?? e).slice(0, 200) }; }
}
async function creatingProof(addr) {
  return thru.proofs.generate({ address: decodeAddress(addr), proofType: StateProofType.CREATING });
}

// ------------------------------------------------------------------ test token (no freeze authority)
export async function createMint(authorityName, seedLabel = "thrubound-test") {
  const seedHex = hex(new TextEncoder().encode(seedLabel.padEnd(32, "\0")).slice(0, 32));
  const m = token.deriveMintAddress(thru, A[authorityName], seedHex, TOKEN);
  A.mint = m.address;
  const proof = await creatingProof(m.address);
  const r = await send("token initialize_mint (no freeze authority)", authorityName, TOKEN, [m.address], [],
    token.createInitializeMintInstruction({ mintAccountBytes: m.bytes, decimals: 0, mintAuthorityBytes: decodeAddress(A[authorityName]),
      ticker: "TBTEST", seedHex: hex(m.derivedSeed), stateProof: proof.proof }), { startSlot: proof.slot });
  return { ...r, mint: m.address };
}
export async function createTokenAccount(payer, ownerAddr, label) {
  const t = token.deriveTokenAccountAddress(thru, ownerAddr, A.mint, TOKEN);
  A[label] = t.address;
  const proof = await creatingProof(t.address);
  const r = await send(`token initialize_account ${label}`, payer, TOKEN, [t.address], [A.mint, ownerAddr].filter((x) => x !== A[payer]),
    token.createInitializeAccountInstruction({ tokenAccountBytes: t.bytes, mintAccountBytes: decodeAddress(A.mint),
      ownerAccountBytes: decodeAddress(ownerAddr), seedBytes: t.derivedSeed, stateProof: proof.proof }), { startSlot: proof.slot });
  return { ...r, tokenAccount: t.address };
}
export async function mintTo(authorityName, destLabel, amount) {
  return send(`token mint_to ${amount} -> ${destLabel}`, authorityName, TOKEN, [A.mint, A[destLabel]], [],
    token.createMintToInstruction({ mintAccountBytes: decodeAddress(A.mint), destinationAccountBytes: decodeAddress(A[destLabel]),
      authorityAccountBytes: decodeAddress(A[authorityName]), amount: BigInt(amount) }));
}
/** Raw token instruction by tag, for KSI-1 probes: [tag u8][payload]. */
export async function tokenRaw(label, signer, readWrite, readOnly, build) {
  return send(label, signer, TOKEN, readWrite, readOnly, async (ctx) => build((a) => ctx.getAccountIndex(decodeAddress(a))));
}
export async function tokenState(label) {
  const a = await thru.accounts.get(A[label]);
  return json(token.parseTokenAccountData(a));
}
export async function mintState() { return json(token.parseMintAccountData(await thru.accounts.get(A.mint))); }

// ------------------------------------------------------------------ program deployment
export async function deploy(signer, programB64, seed) {
  const bytes = Uint8Array.from(atob(programB64), (c) => c.charCodeAt(0));
  const events = [];
  const res = await deployProgram({ seed, signer: { address: A[signer], privateKey: K[signer].privateKey }, client: thru,
    program: bytes, onProgress: (e) => events.push(`${e.phase}:${e.status}${e.uploadStep ? ":" + e.uploadStep : ""}${e.signature ? ":" + e.signature : ""}`) });
  A.program = res.programAccountAddress; A.programMeta = res.programMetaAccountAddress;
  const out = json({ label: "deploy ThruBound program", program: res.programAccountAddress, meta: res.programMetaAccountAddress,
    authority: res.authorityAddress, version: res.programVersion, size: res.programSize, sha256: res.programUpload?.sha256,
    signature: res.transactionSignature, uploadSignatures: res.programUpload?.transactionSignatures, warnings: res.warnings, events });
  LOG.push(out);
  return out;
}
export async function inspect(seed, authority) {
  return json(await inspectProgramDeployment({ client: thru, seed, authorityAddress: A[authority] }));
}

// ------------------------------------------------------------------ ThruBound instructions (layout: thru/program/flowstate_abi.h)
class W { constructor() { this.p = []; } u8(v) { this.p.push(v & 255); return this; } u16(v) { this.p.push(v & 255, (v >> 8) & 255); return this; }
  u32(v) { for (let i = 0; i < 4; i++) this.p.push((v >>> (8 * i)) & 255); return this; }
  u64(v) { v = BigInt(v); for (let i = 0n; i < 8n; i++) this.p.push(Number((v >> (8n * i)) & 255n)); return this; }
  key(k) { if (k.length !== 32) throw new Error("key"); this.p.push(...k); return this; } bytes(b) { this.p.push(...b); return this; }
  done() { return Uint8Array.from(this.p); } }
const enc = new TextEncoder();
async function sha(...parts) { const n = parts.reduce((s, p) => s + p.length, 0); const b = new Uint8Array(n); let o = 0; for (const p of parts) { b.set(p, o); o += p.length; }
  return new Uint8Array(await crypto.subtle.digest("SHA-256", b)); }
const u64le = (v) => new W().u64(v).done();
export async function pda(seed) { return thru.helpers.deriveProgramAddress({ programAddress: A.program, seed, ephemeral: false }); }
export async function derive(vaultId = 1n) {
  const owner = decodeAddress(A.owner), agent = decodeAddress(A.agent);
  const vs = await sha(enc.encode("flowstate/vault/v1"), owner, u64le(vaultId));
  const v = await pda(vs); A.vault = v.address;
  const as = await sha(enc.encode("flowstate/agent/v1"), v.bytes, agent);
  const ag = await pda(as); A.agentAcct = ag.address;
  return json({ vault: A.vault, agentAcct: A.agentAcct });
}
export async function requestAddr(nonce) {
  const rs = await sha(enc.encode("flowstate/request/v1"), decodeAddress(A.vault), decodeAddress(A.agent), u64le(nonce));
  const r = await pda(rs); A[`req${nonce}`] = r.address; return r.address;
}
const I = (ctx) => (name) => (name === null ? 0xffff : ctx.getAccountIndex(decodeAddress(A[name] ?? name)));
const withProof = (w, proof) => w.u32(proof ? proof.length : 0).bytes(proof ?? new Uint8Array()).done();

export const tb = {
  async initVault(vaultId = 1n, ttlNs = 3600n * 1000000000n) {
    const proof = await creatingProof(A.vault);
    return send("ThruBound INIT_VAULT", "owner", A.program, [A.vault], [], async (ctx) => { const i = I(ctx);
      return withProof(new W().u8(0).u16(i("vault")).u16(i("owner")).key(decodeAddress(A.mint)).u64(vaultId).u64(ttlNs), proof.proof); },
      { startSlot: proof.slot });
  },
  bindToken(withMint = true) {
    return send("ThruBound BIND_TOKEN (+ mint unfreezable check)", "owner", A.program, [A.vault], [A.vaultToken, A.mint], async (ctx) => { const i = I(ctx);
      return new W().u8(1).u16(i("vault")).u16(i("owner")).u16(i("vaultToken")).u16(withMint ? i("mint") : 0xffff).done(); });
  },
  async setAgent(l, create) {
    const proof = create ? await creatingProof(A.agentAcct) : null;
    return send(`ThruBound SET_AGENT (${create ? "create" : "update"})`, "owner", A.program, [A.agentAcct, A.vault], [], async (ctx) => { const i = I(ctx);
      return withProof(new W().u8(2).u16(i("vault")).u16(i("owner")).u16(i("agentAcct")).key(decodeAddress(A.agent))
        .u64(l.perTx).u64(l.daily).u64(l.budget).u64(l.threshold).u64(l.validUntilNs).u8(create ? 1 : 0), proof?.proof); },
      proof ? { startSlot: proof.slot } : undefined);
  },
  setRecipient(recipientLabel, allowed = true) {
    return send(`ThruBound SET_RECIPIENT ${recipientLabel}`, "owner", A.program, [A.agentAcct], [A.vault], async (ctx) => { const i = I(ctx);
      return new W().u8(4).u16(i("vault")).u16(i("owner")).u16(i("agentAcct")).key(decodeAddress(A[recipientLabel])).u8(allowed ? 1 : 0).done(); });
  },
  async request(label, nonce, amount, recipientLabel, pending = false, signer = "agent") {
    const req = pending ? await requestAddr(nonce) : null;
    const proof = pending ? await creatingProof(req) : null;
    const rw = [A.agentAcct, A.vault, A.vaultToken, A[recipientLabel], ...(req ? [req] : [])];
    return send(label, signer, A.program, rw, [TOKEN], async (ctx) => { const i = I(ctx);
      return withProof(new W().u8(5).u16(i("vault")).u16(i("agentAcct")).u16(i(signer)).u16(req ? i(req) : 0xffff)
        .u16(i("vaultToken")).u16(i(recipientLabel)).u16(i(TOKEN)).u64(nonce).u64(amount), proof?.proof); },
      proof ? { startSlot: proof.slot } : undefined);
  },
  async approve(label, nonce, tamper = {}) {
    const r = await thru.accounts.get(A[`req${nonce}`]);
    const d = r.data.data; const dv = new DataView(d.buffer, d.byteOffset);
    const rec = { vault: d.slice(8, 40), agent: d.slice(40, 72), recipient: d.slice(72, 104), mint: d.slice(104, 136),
      amount: dv.getBigUint64(136, true), nonce: dv.getBigUint64(144, true), expires: dv.getBigUint64(176, true) };
    const recipientAddr = encodeAddress(rec.recipient);
    const amount = tamper.amount ?? rec.amount;
    return send(label, "owner", A.program, [A.agentAcct, A[`req${nonce}`], A.vault, A.vaultToken, recipientAddr], [TOKEN], async (ctx) => { const i = I(ctx);
      return new W().u8(6).u16(i("vault")).u16(i("owner")).u16(i("agentAcct")).u16(i(A[`req${nonce}`])).u16(i("vaultToken"))
        .u16(i(recipientAddr)).u16(i(TOKEN)).key(rec.vault).key(rec.agent).key(rec.recipient).key(rec.mint)
        .u64(amount).u64(rec.nonce).u64(rec.expires).u8(6).done(); });
  },
  revoke() {
    return send("ThruBound REVOKE", "owner", A.program, [A.agentAcct], [A.vault], async (ctx) => { const i = I(ctx);
      return new W().u8(3).u16(i("vault")).u16(i("owner")).u16(i("agentAcct")).done(); });
  },
  withdraw(amount, destLabel) {
    return send(`ThruBound WITHDRAW ${amount}`, "owner", A.program, [A.vaultToken, A[destLabel]], [A.vault, TOKEN], async (ctx) => { const i = I(ctx);
      return new W().u8(11).u16(i("vault")).u16(i("owner")).u16(i("vaultToken")).u16(i(destLabel)).u16(i(TOKEN)).u64(amount).done(); });
  },
};

export async function chain() {
  return json({ height: await thru.blocks.getBlockHeight(), chainId: await thru.chain.getChainId() });
}
export async function nowNs() {
  const b = await thru.blocks.get({ slot: (await thru.blocks.getBlockHeight()).finalized ?? undefined }).catch(() => null);
  return json(b?.header?.blockTime ?? b?.header ?? null);
}
export const log = () => LOG;
export const bootstrap = () => json({ token: TOKEN, faucet: P.faucet, faucetVault: boot.BOOTSTRAP_FAUCET_VAULT_ADDRESS, eoa: P.eoa });
