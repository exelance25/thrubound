// SDK tests against the LOCAL SIMULATION (real program code, simulated Thru runtime).
import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as SDK from "../dist/index.js";
import { ThruBound, LocalSimulationTransport } from "../dist/index.js";
import { Pubkey } from "@thru/sdk";

const LIB = process.env.FS_SIM_LIB ?? join(dirname(fileURLToPath(import.meta.url)), "..", "..", "build", "host", "libflowstate_sim.so");
const key = (label) => new Uint8Array(createHash("sha256").update("flowstate-sim-key/" + label).digest());
const ta = (b) => Pubkey.from(b).toThruFmt();
const DAY = 86_400n;

function world(seedLabel = "w") {
  const sim = new LocalSimulationTransport({ library: LIB, programLabel: "sdk-test-" + seedLabel });
  const tb = new ThruBound(sim);
  const owner = key(seedLabel + "owner"), agent = key(seedLabel + "agent"), mint = key(seedLabel + "mint");
  const recipients = [0, 1].map((i) => key(seedLabel + "rec" + i));
  return { sim, tb, owner, agent, mint, recipients };
}
async function setup(w, limits = {}) {
  const { sim, tb, owner, agent, mint, recipients } = w;
  const r = await tb.createVault({ owner: ta(owner), vaultId: 1n, mint: ta(mint) });
  assert.ok(r.ok, r.reason);
  const vt = key("vt-" + r.vault);
  sim.createTestMint(mint, owner);
  sim.createTestTokenAccount(vt, mint, Pubkey.from(r.vault).toBytes(), 1_000_000n);
  for (const rc of recipients) sim.createTestTokenAccount(rc, mint, key("holder"), 0n);
  for (const x of ["stranger", "x"]) sim.createTestTokenAccount(key(x), mint, key("holder"), 0n);   // valid token accounts, NOT allowlisted
  assert.ok((await tb.bindTokenAccount({ owner: ta(owner), vault: r.vault, tokenAccount: ta(vt), mint: ta(mint) })).ok);
  const now = (await sim.now()) / 1_000_000_000n;
  const g = await tb.grantAgent({ owner: ta(owner), vault: r.vault, agent: ta(agent), recipients: recipients.map(ta),
    limits: { perTransaction: 100n, perDay: 300n, lifetime: 1000n, approvalAbove: 50n, expiresAt: now + 7n * DAY, ...limits } });
  assert.ok(g.ok, g.reason);
  return { vault: r.vault, vt };
}

test("public surface exposes only the documented API", () => {
  assert.deepEqual(Object.keys(SDK).sort(), ["LocalSimulationTransport", "ThruBound"]);
});

test("addresses come from the official @thru/sdk derivation and the program accepts them", async () => {
  const w = world("addr");
  const expected = createHash("sha256").update(Buffer.concat([Buffer.from(w.sim.programAddress), Buffer.from([0]),
    createHash("sha256").update(Buffer.concat([Buffer.from("flowstate/vault/v1"), Buffer.from(w.owner), Buffer.from([7, 0, 0, 0, 0, 0, 0, 0])])).digest()])).digest();
  assert.equal(w.tb.vaultAddress(ta(w.owner), 7n), ta(expected));
  const r = await w.tb.createVault({ owner: ta(w.owner), vaultId: 7n, mint: ta(w.mint) });
  assert.ok(r.ok, "the program re-derives the address on chain and would refuse a mismatch (DERIVATION)");
  assert.equal(r.vault.slice(0, 2), "ta");
});

test("full flow: grant, instant pay, pending, approve, refuse, revoke", async () => {
  const w = world("flow"); const { tb, owner, agent, recipients } = w;
  const { vault } = await setup(w);
  assert.equal(tb.environment, "local-simulation");
  const paid = await tb.requestPayment({ agent: ta(agent), vault, recipient: ta(recipients[0]), amount: 40n });
  assert.equal(paid.outcome, "paid"); assert.equal(paid.environment, "local-simulation");
  const pend = await tb.requestPayment({ agent: ta(agent), vault, recipient: ta(recipients[1]), amount: 90n });
  assert.equal(pend.outcome, "pending");
  assert.equal((await tb.getPermission(vault, ta(agent))).pending, 90n);
  const ap = await tb.approve({ owner: ta(owner), vault, agent: ta(agent), nonce: pend.nonce });
  assert.equal(ap.outcome, "approved", ap.reason);
  assert.equal(await tb.getTokenBalance(ta(recipients[1])), 90n);
  const again = await tb.approve({ owner: ta(owner), vault, agent: ta(agent), nonce: pend.nonce });
  assert.equal(again.reason, "NO_PENDING");
  const big = await tb.requestPayment({ agent: ta(agent), vault, recipient: ta(recipients[0]), amount: 101n });
  assert.equal(big.reason, "PER_TX");
  const other = await tb.requestPayment({ agent: ta(agent), vault, recipient: ta(key("stranger")), amount: 1n });
  assert.equal(other.reason, "RECIPIENT_NOT_ALLOWED");
  const p = await tb.getPermission(vault, ta(agent));
  assert.equal(p.spent, 130n); assert.equal(p.remaining.lifetime, 870n); assert.equal(p.remaining.today, 170n);
  assert.ok((await tb.revokeAgent({ owner: ta(owner), vault, agent: ta(agent) })).ok);
  assert.equal((await tb.requestPayment({ agent: ta(agent), vault, recipient: ta(recipients[0]), amount: 1n })).reason, "UNKNOWN_AGENT");
  const v = await tb.getVault(vault);
  assert.equal(v.balance, 1_000_000n - 130n); assert.equal(v.mintUnfreezable, true);
});

test("an agent cannot act as owner and the owner cannot act as agent", async () => {
  const w = world("auth"); const { tb, owner, agent, recipients } = w;
  const { vault } = await setup(w);
  const pend = await tb.requestPayment({ agent: ta(agent), vault, recipient: ta(recipients[0]), amount: 90n });
  assert.equal((await tb.approve({ owner: ta(agent), vault, agent: ta(agent), nonce: pend.nonce })).ok, false);
  assert.equal((await tb.pause({ owner: ta(agent), vault, paused: true })).ok, false);
  assert.equal((await tb.withdraw({ owner: ta(agent), vault, destination: ta(recipients[0]), amount: 1n })).ok, false);
  assert.equal((await tb.grantAgent({ owner: ta(owner), vault, agent: ta(owner), limits: { perTransaction: 1n, perDay: 1n,
    lifetime: 1n, approvalAbove: 0n, expiresAt: 9_999_999_999n } })).reason, "INVALID_CONFIG");
});

test("differential: check() predicts the program's decision for 3,000 random requests", async () => {
  let n = 0, rng = 12345;
  const rnd = (k) => { rng = (rng * 1103515245 + 12345) % 2147483648; return rng % k; };
  for (let world_i = 0; world_i < 20; world_i++) {
    const w = world("diff" + world_i); const { tb, sim, owner, agent, recipients } = w;
    const perTx = 20 + rnd(80);                                     // valid config: threshold <= per-tx <= daily <= lifetime
    const { vault } = await setup(w, { perTransaction: BigInt(perTx), perDay: 200n, lifetime: BigInt(300 + rnd(400)),
      approvalAbove: BigInt(rnd(Math.min(30, perTx) + 1)) });
    for (let i = 0; i < 150; i++) {
      const r = rnd(10);
      if (r === 0) sim.advanceSeconds([60, 3600, 86400][rnd(3)]);
      if (r === 1) await tb.pause({ owner: ta(owner), vault, paused: rnd(3) === 0 });
      const perm = await tb.getPermission(vault, ta(agent));
      const rec = [recipients[0], recipients[1], key("x")][rnd(3)];
      const amount = BigInt([0, 1, 10, 49, 50, 51, 99, 100, 101, 250][rnd(10)]);
      const nonce = rnd(8) === 0 ? perm.nextNonce + 1n : perm.nextNonce;
      const pred = await tb.check({ vault, agent: ta(agent), recipient: ta(rec), amount, nonce });
      const got = await tb.requestPayment({ agent: ta(agent), vault, recipient: ta(rec), amount, nonce });
      const actual = got.ok ? (got.outcome === "paid" ? "instant" : "pending") : got.reason;
      const predicted = pred.outcome === "refused" ? pred.reason : pred.outcome;
      assert.equal(predicted, actual, `world ${world_i} step ${i}: amount ${amount} nonce ${nonce}`);
      if (got.outcome === "pending" && rnd(2)) await tb.approve({ owner: ta(owner), vault, agent: ta(agent), nonce });
      n++;
    }
  }
  assert.equal(n, 3000);
});

test("every transaction follows the official account-list rule (sorted, no duplicates)", async () => {
  const w = world("canon"); const sim = w.sim;
  const sent = []; const orig = sim.send.bind(sim);
  sim.send = async (tx) => { sent.push(tx); return orig(tx); };
  const { vault } = await setup(w);
  await w.tb.requestPayment({ agent: ta(w.agent), vault, recipient: ta(w.recipients[0]), amount: 40n });
  const p = await w.tb.requestPayment({ agent: ta(w.agent), vault, recipient: ta(w.recipients[1]), amount: 90n });
  await w.tb.approve({ owner: ta(w.owner), vault, agent: ta(w.agent), nonce: p.nonce });
  const hex = (b) => Buffer.from(b).toString("hex");
  assert.ok(sent.length >= 6);
  for (const tx of sent) {
    const rw = tx.readWrite.map(hex), ro = tx.readOnly.map(hex), all = [hex(tx.feePayer), ...rw, ...ro];
    assert.deepEqual(rw, [...rw].sort()); assert.deepEqual(ro, [...ro].sort());
    assert.equal(new Set(all).size, all.length, "duplicate account in " + tx.label);
  }
});

test("clear errors for the mistakes a newcomer makes", async () => {
  const w = world("dx");
  await assert.rejects(w.tb.createVault({ owner: ta(w.owner), vaultId: 1, mint: ta(w.mint) }), /vaultId must be a BigInt/);
  await assert.rejects(w.tb.createVault({ owner: "taOWNER", vaultId: 1n, mint: ta(w.mint) }), /not a Thru address/);
  const { vault } = await setup(w);
  await assert.rejects(w.tb.requestPayment({ agent: ta(w.agent), vault, recipient: ta(w.recipients[0]), amount: 5 }), /amount must be a BigInt/);
  await assert.rejects(w.tb.requestPayment({ agent: ta(w.agent), vault, recipient: ta(w.recipients[0]), amount: -1n }), /fit in u64/);
});
