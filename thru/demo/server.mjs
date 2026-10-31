// ThruBound demo server: LOCAL SIMULATION only. Binds to 127.0.0.1. No keys, no network, no real tokens.
import { createServer } from "node:http";
import { readFileSync, mkdirSync } from "node:fs";
import { randomBytes } from "node:crypto";
import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { ThruBound, LocalSimulationTransport } from "@thrubound/sdk";
import { Pubkey } from "@thru/sdk";

const here = dirname(fileURLToPath(import.meta.url));
const LIB = process.env.THRUBOUND_SIM_LIB ?? join(here, "..", "build", "host", "libflowstate_sim.so");
const VERIFIER = join(here, "..", "verifier", "verify_thru.py");
const PORT = Number(process.env.PORT ?? 3100);
const FUNDED = 1_000n;
const addr = (b) => Pubkey.from(b).toThruFmt();
const k = () => new Uint8Array(randomBytes(32));

let S = null;   // the whole simulated world for this demo session
async function reset() {
  const sim = new LocalSimulationTransport({ library: LIB, programLabel: "thrubound-demo-" + Date.now() });
  const tb = new ThruBound(sim);
  const keys = { owner: k(), agent: k(), mint: k(), vaultToken: k(), vendor: k(), stranger: k() };
  sim.createTestMint(keys.mint, keys.owner, null);
  const { vault } = await tb.createVault({ owner: addr(keys.owner), vaultId: 1n, mint: addr(keys.mint), approvalTtlSeconds: 3600n });
  sim.createTestTokenAccount(keys.vaultToken, keys.mint, Pubkey.from(vault).toBytes(), FUNDED);
  sim.createTestTokenAccount(keys.vendor, keys.mint, k(), 0n);
  sim.createTestTokenAccount(keys.stranger, keys.mint, k(), 0n);
  await tb.bindTokenAccount({ owner: addr(keys.owner), vault, tokenAccount: addr(keys.vaultToken), mint: addr(keys.mint) });
  S = { sim, tb, keys, vault, log: [], granted: false };
}

const who = () => ({ owner: addr(S.keys.owner), agent: addr(S.keys.agent), vendor: addr(S.keys.vendor), stranger: addr(S.keys.stranger) });
const big = (o) => JSON.parse(JSON.stringify(o, (_k, v) => (typeof v === "bigint" ? v.toString() : v)));
const log = (entry) => { S.log.unshift({ t: new Date().toISOString().slice(11, 19), ...entry }); S.log = S.log.slice(0, 40); };

async function state() {
  const w = who();
  return big({
    environment: S.tb.environment, program: S.tb.programAddress, vault: S.vault, actors: w, granted: S.granted,
    vaultInfo: await S.tb.getVault(S.vault),
    permission: await S.tb.getPermission(S.vault, w.agent),
    pending: (await S.tb.getPendingRequests(S.vault, w.agent)).filter((p) => p.status === "pending"),
    balances: { vendor: await S.tb.getTokenBalance(w.vendor), stranger: await S.tb.getTokenBalance(w.stranger) },
    log: S.log,
  });
}

const routes = {
  "POST /api/reset": async () => { await reset(); return state(); },
  "POST /api/grant": async (b) => {
    const now = (await S.sim.now()) / 1_000_000_000n, w = who();
    const r = await S.tb.grantAgent({ owner: w.owner, vault: S.vault, agent: w.agent, recipients: [w.vendor],
      limits: { perTransaction: BigInt(b.perTransaction), perDay: BigInt(b.perDay), lifetime: BigInt(b.lifetime),
        approvalAbove: BigInt(b.approvalAbove), expiresAt: now + BigInt(b.days) * 86_400n } });
    if (r.ok) S.granted = true;
    log({ actor: "owner", action: `grant: ${b.perTransaction}/payment, ${b.perDay}/day, ${b.lifetime} total, approval above ${b.approvalAbove}, ${b.days} days`, result: r.ok ? "done" : "refused", reason: r.reason });
    return state();
  },
  "POST /api/check": async (b) => big(await S.tb.check({ vault: S.vault, agent: who().agent, recipient: who()[b.to], amount: BigInt(b.amount) })),
  "POST /api/pay": async (b) => {
    const r = await S.tb.requestPayment({ agent: who().agent, vault: S.vault, recipient: who()[b.to], amount: BigInt(b.amount) });
    log({ actor: "agent", action: `pay ${b.amount} to ${b.to}`, result: r.ok ? r.outcome : "refused", reason: r.reason, nonce: r.nonce?.toString() });
    return state();
  },
  "POST /api/approve": async (b) => {
    const r = await S.tb.approve({ owner: who().owner, vault: S.vault, agent: who().agent, nonce: BigInt(b.nonce) });
    log({ actor: "owner", action: `approve request #${b.nonce}`, result: r.ok ? "approved" : "refused", reason: r.reason });
    return state();
  },
  "POST /api/reject": async (b) => {
    const r = await S.tb.reject({ actor: who().owner, vault: S.vault, agent: who().agent, nonce: BigInt(b.nonce) });
    log({ actor: "owner", action: `reject request #${b.nonce}`, result: r.ok ? "rejected" : "refused", reason: r.reason });
    return state();
  },
  "POST /api/agent-approves": async (b) => {
    const r = await S.tb.approve({ owner: who().agent, vault: S.vault, agent: who().agent, nonce: BigInt(b.nonce) });
    log({ actor: "agent", action: `tries to approve its own request #${b.nonce}`, result: r.ok ? "approved" : "refused", reason: r.reason });
    return state();
  },
  "POST /api/revoke": async () => {
    const r = await S.tb.revokeAgent({ owner: who().owner, vault: S.vault, agent: who().agent });
    log({ actor: "owner", action: "revoke the agent", result: r.ok ? "done" : "refused", reason: r.reason });
    return state();
  },
  "POST /api/pause": async (b) => {
    const r = await S.tb.pause({ owner: who().owner, vault: S.vault, paused: !!b.paused });
    log({ actor: "owner", action: b.paused ? "pause the vault" : "resume the vault", result: r.ok ? "done" : "refused", reason: r.reason });
    return state();
  },
  "POST /api/next-day": async () => { S.sim.advanceSeconds(86_400); log({ actor: "clock", action: "one day later", result: "done" }); return state(); },
  "POST /api/authority": async () => big(await S.tb.analyzeAuthorities({ vault: S.vault, agents: [who().agent] })),
  "POST /api/verify": async () => {
    mkdirSync(join(here, "out"), { recursive: true });
    const w = who(), path = join(here, "out", "trace.jsonl");
    const snap = await S.tb.exportProofLabSnapshot({ vault: S.vault, agents: [w.agent], tokenAccounts: [w.vendor, w.stranger], fundedTotal: FUNDED });
    S.sim.saveTrace(path, snap);
    const out = await new Promise((res) => execFile("python3", ["-I", VERIFIER, path], { timeout: 60_000 },
      (err, stdout, stderr) => res({ code: err ? err.code ?? 1 : 0, text: (stdout + stderr).trim() })));
    return { pass: out.code === 0, report: out.text };
  },
};

createServer(async (req, res) => {
  try {
    if (req.method === "GET" && (req.url === "/" || req.url === "/index.html")) {
      res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
      return res.end(readFileSync(join(here, "public", "index.html")));
    }
    if (req.method === "GET" && req.url === "/api/state") { res.writeHead(200, { "content-type": "application/json" }); return res.end(JSON.stringify(await state())); }
    const h = routes[`${req.method} ${req.url}`];
    if (!h) { res.writeHead(404); return res.end("not found"); }
    let body = ""; for await (const c of req) { body += c; if (body.length > 10_000) throw new Error("body too large"); }
    const data = await h(body ? JSON.parse(body) : {});
    res.writeHead(200, { "content-type": "application/json" }); res.end(JSON.stringify(data));
  } catch (e) {
    res.writeHead(400, { "content-type": "application/json" }); res.end(JSON.stringify({ error: String(e.message ?? e) }));
  }
}).listen(PORT, "127.0.0.1", async () => {
  await reset();
  console.log(`ThruBound demo (LOCAL SIMULATION) on http://127.0.0.1:${PORT}`);
});
