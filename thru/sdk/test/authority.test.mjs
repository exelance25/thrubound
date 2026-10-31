// Authority analysis (Proof Lab) against the LOCAL SIMULATION.
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { ThruBound, LocalSimulationTransport } from "../dist/index.js";
import { Pubkey } from "@thru/sdk";
import { encodeRatelimitConfig, deriveRatelimitAuthorityAddress, RATELIMIT_POLICY_MAGIC, RATELIMIT_KEY_ATTESTED, RATELIMIT_KEY_GLOBAL } from "@thru/programs/ratelimit";

const LIB = process.env.FS_SIM_LIB ?? join(dirname(fileURLToPath(import.meta.url)), "..", "..", "build", "host", "libflowstate_sim.so");
const key = (l) => new Uint8Array(createHash("sha256").update("flowstate-sim-key/" + l).digest());
const ta = (b) => Pubkey.from(b).toThruFmt();
const OFFICIAL = new Set(["official-doc", "official-abi", "official-cli", "official-sdk", "chain-data"]);
const byId = (r, id) => r.findings.find((f) => f.id === id);

async function vaultWorld(label, { freeze = false } = {}) {
  const sim = new LocalSimulationTransport({ library: LIB, programLabel: "auth-" + label });
  const tb = new ThruBound(sim);
  const owner = key(label + "o"), mint = key(label + "m"), vt = key(label + "vt"), rec = key(label + "r");
  const agents = [key(label + "a1"), key(label + "a2")];
  sim.createTestMint(mint, owner, freeze ? key(label + "freezer") : null);
  const { vault } = await tb.createVault({ owner: ta(owner), vaultId: 1n, mint: ta(mint) });
  sim.createTestTokenAccount(vt, mint, Pubkey.from(vault).toBytes(), 1000n);
  sim.createTestTokenAccount(rec, mint, key("holder"), 0n);
  assert.ok((await tb.bindTokenAccount({ owner: ta(owner), vault, tokenAccount: ta(vt), ...(freeze ? {} : { mint: ta(mint) }) })).ok);
  const now = (await sim.now()) / 1_000_000_000n;
  for (const a of agents)
    assert.ok((await tb.grantAgent({ owner: ta(owner), vault, agent: ta(a), recipients: [ta(rec)],
      limits: { perTransaction: 50n, perDay: 100n, lifetime: 300n, approvalAbove: 20n, expiresAt: now + 86_400n } })).ok);
  return { sim, tb, owner, mint, vt, rec, agents, vault };
}

test("well-formed vault: no policy-bypassing key except the owner, and simulated facts are never VERIFIED", async () => {
  const w = await vaultWorld("good");
  const r = await w.tb.analyzeAuthorities({ vault: w.vault, agents: w.agents.map(ta) });
  assert.equal(r.dataOrigin, "local-simulation");
  for (const f of r.findings) if (f.status === "VERIFIED") assert.ok(f.evidence.every((e) => OFFICIAL.has(e.kind)), f.id);
  assert.ok(r.findings.every((f) => f.status !== "VERIFIED" || !f.evidence.some((e) => e.kind === "simulated-chain-data")));
  assert.equal(byId(r, "account-authority").status, "UNVERIFIED");        // correct, but simulated + inference
  assert.equal(byId(r, "freeze-authority").status, "UNVERIFIED");
  assert.equal(byId(r, "no-delegation").status, "VERIFIED");               // official ABI only
  assert.equal(byId(r, "atomicity").status, "VERIFIED");                   // official docs only
  const risks = r.findings.filter((f) => f.status === "RISK").map((f) => f.id).sort();
  assert.deepEqual(risks, ["owner-withdraw", "program-upgrade"]);         // the honest residue
  const unbounded = r.movers.filter((m) => !m.bounded).map((m) => m.how);
  assert.deepEqual(unbounded, ["WITHDRAW (owner)"]);
  assert.equal(r.movers.filter((m) => m.how.startsWith("REQUEST")).length, 2);
  assert.match(r.movers.find((m) => m.how.startsWith("REQUEST")).upTo, /^20 today|^100 today/);
});

test("freezable mint, foreign owner, unlisted and revoked agents are reported", async () => {
  const w = await vaultWorld("bad", { freeze: true });
  let r = await w.tb.analyzeAuthorities({ vault: w.vault, agents: [ta(w.agents[0])] });
  assert.equal(byId(r, "freeze-authority").status, "RISK");
  assert.equal(byId(r, "agents-unlisted").status, "RISK");
  assert.ok(r.movers.some((m) => m.how.startsWith("freeze_account")));
  await w.tb.revokeAgent({ owner: ta(w.owner), vault: w.vault, agent: ta(w.agents[0]) });
  w.sim.advanceSeconds(2 * 86_400);                                       // agent 2 expires
  r = await w.tb.analyzeAuthorities({ vault: w.vault, agents: w.agents.map(ta) });
  assert.match(byId(r, `agent:${ta(w.agents[0])}`).title, /revoked/);
  assert.match(byId(r, `agent:${ta(w.agents[1])}`).title, /expired/);
  assert.equal(r.movers.filter((m) => m.how.startsWith("REQUEST")).length, 0);
  // the token account's owner field no longer points at the vault (state forced by a fixture)
  w.sim.createTestTokenAccount(w.vt, w.mint, key("someone"), 1000n);
  r = await w.tb.analyzeAuthorities({ vault: w.vault, agents: w.agents.map(ta) });
  assert.equal(byId(r, "account-authority").status, "RISK");
  assert.ok(r.movers.some((m) => m.who === ta(key("someone")) && !m.bounded));
});

test("unreadable things are RISK, never assumed safe", async () => {
  const w = await vaultWorld("gone");
  w.sim.createRawAccount(w.mint, key("not-token-program"), new Uint8Array(115));   // mint no longer readable as a mint
  const r = await w.tb.analyzeAuthorities({ vault: w.vault, agents: w.agents.map(ta) });
  assert.equal(byId(r, "freeze-authority").status, "RISK");
  const r2 = await w.tb.analyzeTokenAccount({ tokenAccount: ta(key("does-not-exist")) });
  assert.equal(r2.findings[0].status, "RISK");
});

test("plain token account: its owner key can move everything", async () => {
  const w = await vaultWorld("plain");
  const r = await w.tb.analyzeTokenAccount({ tokenAccount: ta(w.rec) });
  assert.equal(byId(r, "account-authority").status, "RISK");
  assert.ok(r.movers.some((m) => m.who === ta(key("holder")) && !m.bounded));
});

function rlWorld(sim, label, cfg) {
  const rlProgram = key(label + "rl-program"), policy = key(label + "rl-policy"), admin = key(label + "rl-admin");
  const head = Buffer.alloc(8 + 32 + 32 + 8 + 1);
  head.writeBigUInt64LE(RATELIMIT_POLICY_MAGIC, 0); Buffer.from(admin).copy(head, 8);
  Buffer.from(sim.tokenProgramAddress).copy(head, 40); head.writeBigUInt64LE(1n, 72); head[80] = 0;
  sim.createRawAccount(policy, rlProgram, Buffer.concat([head, Buffer.from(encodeRatelimitConfig(cfg))]));
  const authority = deriveRatelimitAuthorityAddress(rlProgram, policy).bytes;
  return { rlProgram, policy, admin, authority };
}

test("Rate Limiter custody: safe and unsafe policies, parsed with the official @thru/programs client", async () => {
  const w = await vaultWorld("rl");
  const vendor = w.rec, agent = key("rl-agent");
  const safe = { selectorSz: 1, selectorOffset: 0, selectorValue: 2n, instrSzMin: 13, instrSzMax: 13, amountSz: 8, amountOffset: 5,
    maxAmountPerCall: 10n, attester: agent, constraints: [{ idxOffset: 3, expected: vendor }],
    rules: [{ keyKind: RATELIMIT_KEY_ATTESTED, clock: 1, window: 86_400n, maxCalls: 0n, maxAmount: 50n }] };
  let rl = rlWorld(w.sim, "safe", safe);
  const held = key("rl-held");
  w.sim.createTestTokenAccount(held, w.mint, rl.authority, 500n);
  let r = await w.tb.analyzeTokenAccount({ tokenAccount: ta(held), ratelimit: { program: ta(rl.rlProgram), policy: ta(rl.policy) } });
  const risks = r.findings.filter((f) => f.status === "RISK").map((f) => f.id).sort();
  assert.deepEqual(risks, ["rl-admin"]);                                    // the admin can always rewrite the rules
  assert.equal(byId(r, "rl-selector").status, "UNVERIFIED");
  const unsafe = { ...safe, selectorSz: 0, selectorValue: 0n, constraints: [], attester: undefined,
    rules: [{ keyKind: RATELIMIT_KEY_GLOBAL, clock: 1, window: 86_400n, maxCalls: 0n, maxAmount: 0n }], maxAmountPerCall: 0n, amountSz: 0 };
  rl = rlWorld(w.sim, "unsafe", unsafe);
  w.sim.createTestTokenAccount(held, w.mint, rl.authority, 500n);
  r = await w.tb.analyzeTokenAccount({ tokenAccount: ta(held), ratelimit: { program: ta(rl.rlProgram), policy: ta(rl.policy) } });
  for (const id of ["rl-admin", "rl-selector", "rl-recipient", "rl-caller", "rl-quota"]) assert.equal(byId(r, id).status, "RISK", id);
  // wrong policy for this account
  r = await w.tb.analyzeTokenAccount({ tokenAccount: ta(held), ratelimit: { program: ta(rl.rlProgram), policy: ta(key("other-policy")) } });
  assert.equal(byId(r, "rl-authority").status, "RISK");
});
