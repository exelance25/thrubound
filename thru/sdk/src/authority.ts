// ThruBound Proof Lab — authority analysis.
// Answers: "Which authorities, accounts and programs can move (or block) these funds?"
//
// Classification (strict):
//   VERIFIED   every piece of evidence is an official Thru source or real chain data
//   UNVERIFIED something rests on simulated data, ThruBound's own code, or an inference
//   RISK       a condition that can lead to fund movement (or blocking) outside the agent policy,
//              including anything the analysis cannot see. Nothing unseen is assumed safe.
import { Pubkey } from "@thru/sdk";
import { deriveRatelimitAuthorityAddress, parseRatelimitPolicyAccount, RATELIMIT_KEY_ATTESTED, RATELIMIT_POLICY_FLAG_PAUSED } from "@thru/programs/ratelimit";
import { C } from "./abi.generated.js";
import { decodeAgent, decodeRequest, decodeTokenAccount, decodeVault, type Bytes } from "./codec.js";
import type { Transport } from "./transport.js";

export type Status = "VERIFIED" | "UNVERIFIED" | "RISK";
export type EvidenceKind = "official-doc" | "official-abi" | "official-cli" | "official-sdk" | "chain-data"
  | "simulated-chain-data" | "thrubound-code" | "inference";
export interface Evidence { kind: EvidenceKind; ref: string }
export interface Finding { id: string; status: Status; title: string; detail: string; evidence: Evidence[]; toVerify?: string }
export interface Mover { who: string; how: string; upTo: string; bounded: boolean }
export interface AuthorityReport {
  subject: string;
  dataOrigin: Transport["kind"];
  summary: Record<Status, number>;
  movers: Mover[];
  findings: Finding[];
}

// Official sources (read 2026-10-30/31; see docs/AUTHORITY_ANALYSIS.md for the exact passages)
const SRC = {
  docToken: { kind: "official-doc", ref: "thru.org/docs Token Program: burn requires the account authority; freeze/thaw require the mint's freeze authority; mint_to requires the mint authority" },
  docTokenAddr: { kind: "official-doc", ref: "thru.org/docs Token Program: addresses target the upcoming Alphanet reset and do not confirm deployment on the current network" },
  docExec: { kind: "official-doc", ref: "thru.org/docs Transaction Execution: failed executions preserve nonce advancement and fee collection only" },
  docInvoke: { kind: "official-doc", ref: "thru.org/docs invoke syscall: auth accounts must be owned by the calling program (0xBAD0A171)" },
  docPrograms: { kind: "official-doc", ref: "thru.org/docs Programs: programs create accounts they own and write to them" },
  abiToken: { kind: "official-abi", ref: "tn_token_program.abi.yaml v0.1.0: 8 instructions, no approve/delegate/permit; transfer carries no authority field" },
  cliClose: { kind: "official-cli", ref: "thru 0.4.2 `token close-account --help`: AUTHORITY = account authority; remaining balance goes to DESTINATION" },
  sdkAuth: { kind: "official-sdk", ref: "Thru C SDK v0.4.2 tsdk_is_account_authorized_by_idx (fee payer, current program, caller's invoke auth list)" },
  sdkTokenAddr: { kind: "official-sdk", ref: "Thru SDKs v0.4.2: TOKEN_PROGRAM_ADDRESS taTOKENKR… = 4ce28434…" },
  abiRl: { kind: "official-abi", ref: "tn_ratelimit_program.abi.yaml v0.1.0 + @thru/programs 0.4.2 ratelimit client (implementation source not public; not in the official docs)" },
  infOwner: { kind: "inference", ref: "the token account's only authority field is `owner`, so 'account authority' = owner" },
  tbCode: { kind: "thrubound-code", ref: "thru/program (ThruBound program source)" },
} as const satisfies Record<string, Evidence>;

const text = (b: Bytes) => Pubkey.from(b).toThruFmt();
const eq = (a: Bytes, b: Bytes) => a.length === b.length && a.every((x, i) => x === b[i]);
const zero = (b: Bytes) => b.every((x) => x === 0);
const OFFICIAL = new Set<EvidenceKind>(["official-doc", "official-abi", "official-cli", "official-sdk", "chain-data"]);

class Builder {
  findings: Finding[] = [];
  movers: Mover[] = [];
  constructor(private origin: Transport["kind"]) {}
  get data(): Evidence { return this.origin === "local-simulation" ? { kind: "simulated-chain-data", ref: "LOCAL SIMULATION account data (not a Thru network)" } : { kind: "chain-data", ref: "Thru RPC account data" }; }
  add(id: string, risk: boolean, title: string, detail: string, evidence: Evidence[], toVerify?: string) {
    const status: Status = risk ? "RISK" : evidence.every((e) => OFFICIAL.has(e.kind)) ? "VERIFIED" : "UNVERIFIED";
    this.findings.push({ id, status, title, detail, evidence, ...(toVerify ? { toVerify } : {}) });
  }
  report(subject: string): AuthorityReport {
    const summary = { VERIFIED: 0, UNVERIFIED: 0, RISK: 0 } as Record<Status, number>;
    for (const f of this.findings) summary[f.status]++;
    const order = { RISK: 0, UNVERIFIED: 1, VERIFIED: 2 };
    this.findings.sort((a, b) => order[a.status] - order[b.status]);
    return { subject, dataOrigin: this.origin, summary, movers: this.movers, findings: this.findings };
  }
}

/** Facts about a token account and its mint that apply to any holder (ThruBound or not). */
async function tokenFacts(t: Transport, b: Builder, tokenAccount: Bytes) {
  const acc = await t.getAccount(tokenAccount);
  if (!acc) { b.add("token-account", true, "Token account not readable", "The account does not exist or cannot be read; nothing about it can be assumed.", [b.data]); return null; }
  if (!eq(acc.owner, t.tokenProgramAddress) || acc.data.length !== C.FS_TOKEN_ACCOUNT_SZ) {
    b.add("token-program", true, "Not an official token-program account", "The account is not owned by the configured token program or has the wrong size.", [b.data, SRC.sdkTokenAddr]);
    return null;
  }
  const tok = decodeTokenAccount(acc.data);
  b.add("token-program", false, "Held by the official token program address",
    "The account is owned by the token program address published in the official SDKs. Whether that program is deployed at this address on a given network, and how it is implemented, is not confirmed (source not public).",
    [b.data, SRC.sdkTokenAddr, SRC.docTokenAddr], "Read the account on a Thru network and confirm the token program deployment there.");
  b.add("no-delegation", false, "No delegate or allowance can exist",
    "The official token ABI has no approve, delegate or permit instruction, so no third party can hold an allowance over this account.", [SRC.abiToken]);
  b.add("frozen-now", tok.frozen, tok.frozen ? "The token account is frozen" : "The token account is not frozen",
    tok.frozen ? "Nothing can move until the mint's freeze authority thaws it." : "Payments are not blocked by a freeze right now.", [b.data, SRC.docToken]);
  const mint = await t.getAccount(tok.mint);
  if (!mint || mint.data.length !== C.FS_TOKEN_MINT_SZ || !eq(mint.owner, t.tokenProgramAddress)) {
    b.add("freeze-authority", true, "Mint not readable: freeze and mint authorities unknown",
      "Without the mint account, a freeze authority that could block the funds cannot be ruled out.", [b.data, SRC.docToken]);
  } else {
    const d = mint.data, hasFreeze = d[C.FS_MINT_HAS_FREEZE_OFF] !== 0;
    const freezeAuth = d.slice(73, 105), mintAuth = d.slice(41, 73);
    b.add("freeze-authority", hasFreeze, hasFreeze ? `Mint has a freeze authority (${text(freezeAuth)})` : "Mint has no freeze authority",
      hasFreeze ? "That key can freeze this account and block every payment (denial of service; it cannot move the tokens)."
        : "No one can freeze this account through the token program.", [b.data, SRC.docToken]);
    if (hasFreeze) b.movers.push({ who: text(freezeAuth), how: "freeze_account (blocks, does not move)", upTo: "all payments blocked", bounded: false });
    b.add("mint-authority", false, `Mint authority ${text(mintAuth)} can mint new supply`,
      "mint_to credits a destination; per the official docs it does not take tokens from existing accounts. It changes total supply, not this balance.",
      [b.data, SRC.docToken]);
  }
  return tok;
}

/** Analyse a ThruBound vault: who can move its tokens, how much, and on what evidence. */
export async function analyzeVault(t: Transport, vault: Bytes, agents: Bytes[], agentAcct: (a: Bytes) => Bytes,
  requestAcct: (a: Bytes, n: bigint) => Bytes): Promise<AuthorityReport> {
  const b = new Builder(t.kind);
  const vacc = await t.getAccount(vault);
  if (!vacc || !eq(vacc.owner, t.programAddress) || vacc.data.length !== 136) {
    b.add("vault", true, "Vault account not readable or not owned by the ThruBound program", "Nothing can be concluded.", [b.data]);
    return b.report(text(vault));
  }
  const v = decodeVault(vacc.data);
  const tok = await tokenFacts(t, b, v.tokenAccount);
  const balance = tok ? tok.amount : 0n;

  // who holds the token account's own authority
  if (tok) {
    const ownedByVault = eq(tok.owner, vault);
    b.add("account-authority", !ownedByVault,
      ownedByVault ? "Transfer, burn and close authority sits with the vault address" : `Token account owner is ${text(tok.owner)}, not the vault`,
      ownedByVault ? "The vault address is an account owned by the ThruBound program. A program can put only accounts it owns into an invoke authorization, so only the ThruBound program can authorise this account, and it only ever invokes `transfer` from REQUEST, APPROVE and WITHDRAW. That the token program accepts transfer, burn and close only from the owner is an inference (A1)."
        : "That key can transfer, burn or close the account directly, bypassing every ThruBound limit.",
      [b.data, SRC.docToken, SRC.cliClose, SRC.abiToken, SRC.infOwner, SRC.docInvoke, SRC.sdkAuth, SRC.tbCode],
      "On a Thru network: try transfer, burn and close_account on this account signed by the owner key, an agent and a stranger; all must fail.");
    if (!ownedByVault) b.movers.push({ who: text(tok.owner), how: "token transfer / burn / close_account directly", upTo: `${balance} (everything)`, bounded: false });
  }
  b.add("vault-bound-unfreezable", false,
    v.flags & C.FS_VAULT_MINT_UNFREEZABLE ? "Vault recorded that its mint has no freeze authority (checked when the token account was bound)"
      : "Vault did not check the mint at binding time", "Recorded on chain by BIND_TOKEN (flag FS_VAULT_MINT_UNFREEZABLE).", [b.data, SRC.tbCode]);

  // the owner
  b.add("owner-withdraw", true, `Owner ${text(v.owner)} can withdraw everything`,
    "WITHDRAW is the owner's exit and is not limited by agent policies (by design: ThruBound limits agents, not the owner). Losing the owner key means losing the vault.",
    [b.data, SRC.tbCode]);
  b.movers.push({ who: text(v.owner), how: "WITHDRAW (owner)", upTo: `${balance} (everything)`, bounded: false });
  const paused = (v.flags & C.FS_VAULT_PAUSED) !== 0, killed = (v.flags & C.FS_VAULT_KILLED) !== 0;
  b.add("vault-state", false, killed ? "Vault is permanently stopped" : paused ? "Vault is paused" : "Vault is live",
    killed || paused ? "No agent payment or approval can execute; the owner can still withdraw." : "Agents can pay within their limits.", [b.data, SRC.tbCode]);

  // agents
  const now = await t.now();
  if (agents.length < v.agentCount)
    b.add("agents-unlisted", true, `${v.agentCount - agents.length} of ${v.agentCount} agents were not analysed`,
      "The vault has more agents than were given to the analysis; their authority is unknown here.", [b.data],
      "Pass every agent (an indexer can list the program's agent accounts on a network).");
  for (const ag of agents) {
    const a = await t.getAccount(agentAcct(ag));
    if (!a) { b.add(`agent:${text(ag)}`, true, `Agent ${text(ag)}: account not found`, "Cannot tell what this key may do.", [b.data]); continue; }
    const s = decodeAgent(a.data);
    const expired = now >= s.validUntilNs;
    const today = now / BigInt(C.FS_NS_PER_DAY);
    const leftToday = s.daily - (s.day === today ? s.dailyUsed : 0n);
    const leftLife = s.budget - s.spent - s.reserved;
    const live = s.active && !expired && !paused && !killed;
    const min = (...xs: bigint[]) => xs.reduce((x, y) => (y < x ? y : x));
    const todayCap = min(leftToday, leftLife, balance), lifeCap = min(leftLife, balance);
    b.add(`agent:${text(ag)}`, false,
      !s.active ? `Agent ${text(ag)} is revoked` : expired ? `Agent ${text(ag)} has expired` : `Agent ${text(ag)} is active`,
      live ? `Can pay without approval in payments of at most ${s.threshold}: up to ${todayCap} today and ${lifeCap} over its remaining lifetime (per payment ≤ ${s.perTx}; larger payments wait for the owner), only to its ${s.recipients.length} allowlisted recipient(s), until ${new Date(Number(s.validUntilNs / 1_000_000n)).toISOString().slice(0, 10)}.`
        : "Cannot pay: the program refuses requests from revoked or expired agents, and approvals of their pending requests.",
      [b.data, SRC.tbCode]);
    if (live) b.movers.push({ who: text(ag), how: `REQUEST (agent; payments ≤ ${s.threshold} without approval)`, upTo: `${todayCap} today, ${lifeCap} in total`, bounded: true });
    let pend = 0n;
    for (let n = 0n; n < s.nextNonce; n++) {
      const r = await t.getAccount(requestAcct(ag, n));
      if (!r) continue;
      const q = decodeRequest(r.data);
      if (q.status === C.FS_REQ_PENDING && q.epoch === s.epoch && now < q.expiresNs) pend += q.amount;
    }
    if (pend > 0n) b.movers.push({ who: text(v.owner), how: `APPROVE pending requests of ${text(ag)}`, upTo: `${pend}`, bounded: true });
  }

  // code and programs
  const prog = await t.getAccount(t.programAddress);
  b.add("program-upgrade", true, "ThruBound program upgrade authority not determined",
    prog ? "Whoever can upgrade the program can replace every rule above. This analysis cannot read the manager meta account here."
      : "The program account could not be read.", [b.data, SRC.docPrograms],
    "Read the program's manager meta account on the network (`thru program status`), or deploy finalized (immutable).");
  b.add("downstream-programs", false, "ThruBound invokes only the token program, and only `transfer`",
    "The program checks the token program address before every invoke and builds only transfer (tag 2) instructions. Whether the deployed binary is this code is not verified.",
    [SRC.tbCode], "Compare the deployed program image with the reproducible official-toolchain build hash.");
  b.add("atomicity", false, "A failed transaction changes nothing except the fee payer's nonce and fee",
    "So a failed transfer cannot leave budget accounting half-updated.", [SRC.docExec]);
  return b.report(text(vault));
}

/** Analyse any token account; recognises a Rate Limiter authority PDA when its policy is given. */
export async function analyzeTokenAccount(t: Transport, tokenAccount: Bytes, opts: { ratelimitProgram?: Bytes; ratelimitPolicy?: Bytes } = {}): Promise<AuthorityReport> {
  const b = new Builder(t.kind);
  const tok = await tokenFacts(t, b, tokenAccount);
  if (!tok) return b.report(text(tokenAccount));
  if (opts.ratelimitProgram && opts.ratelimitPolicy) {
    const auth = deriveRatelimitAuthorityAddress(opts.ratelimitProgram, opts.ratelimitPolicy).bytes;
    if (!eq(auth, tok.owner)) {
      b.add("rl-authority", true, "Owner is not the given Rate Limiter policy's authority", `Owner ${text(tok.owner)} can move the funds directly.`, [b.data, SRC.abiRl]);
      b.movers.push({ who: text(tok.owner), how: "token transfer / burn / close_account directly", upTo: `${tok.amount}`, bounded: false });
      return b.report(text(tokenAccount));
    }
    const pacc = await t.getAccount(opts.ratelimitPolicy);
    const pol = pacc && eq(pacc.owner, opts.ratelimitProgram) ? parseRatelimitPolicyAccount(pacc.data) : null;
    if (!pol) { b.add("rl-policy", true, "Rate Limiter policy not readable", "The rules that guard the funds cannot be seen.", [b.data, SRC.abiRl]); return b.report(text(tokenAccount)); }
    const cfg = pol.config;
    b.add("rl-authority", false, "Owner is the Rate Limiter policy's authority PDA",
      "Per the Rate Limiter ABI, that PDA is authorised only inside CALL, after the policy matcher and quotas pass. The implementation is not public.", [b.data, SRC.abiRl, SRC.docInvoke],
      "On a network: try to move the funds outside CALL; it must fail.");
    b.add("rl-admin", true, `Policy admin ${pol.admin} can rewrite the rules`,
      "UPDATE_POLICY replaces the whole config (limits, selector, constraints, attester) and SET_ADMIN hands the policy over, so the admin effectively controls the funds.", [b.data, SRC.abiRl]);
    b.movers.push({ who: pol.admin, how: "UPDATE_POLICY, then CALL (admin)", upTo: `${tok.amount} (everything)`, bounded: false });
    const tokenTarget = Pubkey.from(pol.target).toBytes();
    const transferOnly = cfg.selectorSz === 1 && cfg.selectorOffset === 0 && cfg.selectorValue === 2n;
    if (!eq(tokenTarget, t.tokenProgramAddress))
      b.add("rl-target", true, `Policy target is ${pol.target}, not the token program`, "The authority PDA is lent to that program on every CALL.", [b.data, SRC.abiRl]);
    b.add("rl-selector", !transferOnly, transferOnly ? "CALL is restricted to token `transfer` (tag 2)" : "CALL is not restricted to token `transfer`",
      transferOnly ? "burn and close_account cannot be forwarded with the authority." : "A caller may forward burn or close_account (sending the balance anywhere) with the authority PDA.", [b.data, SRC.abiRl, SRC.abiToken]);
    const destPinned = (cfg.constraints ?? []).some((c) => c.idxOffset === 3);
    b.add("rl-recipient", !destPinned, destPinned ? "Destination pinned by a constraint" : "Any destination allowed",
      destPinned ? "Each constraint pins exactly one address; several recipients sharing one budget cannot be expressed in one policy." : "Payments can go to any token account.", [b.data, SRC.abiRl]);
    const attested = cfg.rules.some((r) => r.keyKind === RATELIMIT_KEY_ATTESTED) && !zero(Pubkey.from(cfg.attester ?? new Uint8Array(32)).toBytes());
    b.add("rl-caller", !attested, attested ? `Only the attester ${cfg.attester} can be charged under ATTESTED rules` : "No attested caller: anyone may CALL within the quotas",
      "Per the ABI, the attester must be authorised for ATTESTED rules.", [b.data, SRC.abiRl]);
    const amountRule = cfg.rules.some((r) => r.maxAmount > 0n) || cfg.maxAmountPerCall > 0n;
    b.add("rl-quota", !amountRule || cfg.amountSz === 0, amountRule ? `Amount limited (per call ${cfg.maxAmountPerCall || "unlimited"}; windowed rules ${cfg.rules.map((r) => `${r.maxAmount || "∞"}/${r.window}`).join(", ")})` : "No amount limit",
      "Rate Limiter has no expiry and no pending human approval.", [b.data, SRC.abiRl]);
    if (pol.stateFlags & RATELIMIT_POLICY_FLAG_PAUSED || (cfg.flags ?? 0) & RATELIMIT_POLICY_FLAG_PAUSED)
      b.add("rl-paused", false, "Policy is paused", "CALL is refused while paused.", [b.data, SRC.abiRl]);
    b.movers.push({ who: attested ? `${cfg.attester}` : "anyone", how: "Rate Limiter CALL", upTo: `${cfg.maxAmountPerCall || "per-window quotas"}`, bounded: amountRule });
    return b.report(text(tokenAccount));
  }
  b.add("account-authority", true, `Owner ${text(tok.owner)} controls the funds directly`,
    "Unless the owner is a program-controlled address, that key can transfer, burn or close the account with no policy.", [b.data, SRC.docToken, SRC.infOwner]);
  b.movers.push({ who: text(tok.owner), how: "token transfer / burn / close_account directly", upTo: `${tok.amount} (everything)`, bounded: false });
  return b.report(text(tokenAccount));
}
