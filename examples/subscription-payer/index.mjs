// subscription-payer — an application that knows nothing about ThruBound's internals.
// It uses only the public SDK entry point ("@thrubound/sdk") and the official @thru/sdk for addresses.
// Environment: LOCAL SIMULATION. No network, no real tokens, no signatures. Nothing here is a real transaction.
import { mkdirSync, writeFileSync } from "node:fs";
import { randomBytes } from "node:crypto";
import { ThruBound, LocalSimulationTransport } from "@thrubound/sdk";
import { Pubkey } from "@thru/sdk";

const LIB = process.env.THRUBOUND_SIM_LIB ?? new URL("../../thru/build/host/libflowstate_sim.so", import.meta.url).pathname;
const newKey = () => new Uint8Array(randomBytes(32));
const addr = (b) => Pubkey.from(b).toThruFmt();
const show = (step, what, r) => console.log(`${step.padEnd(4)} ${what.padEnd(48)} -> ${r.ok ? r.outcome : "REFUSED (" + r.reason + ")"}`);
const fail = (msg) => { console.error("DEMO CHECK FAILED: " + msg); process.exit(1); };

const sim = new LocalSimulationTransport({ library: LIB, programLabel: "subscription-payer-demo" });
const tb = new ThruBound(sim);
console.log(`ThruBound demo — environment: ${tb.environment.toUpperCase()} (not a Thru network)\n`);

// Actors (fresh keys each run; in the simulation an "address" stands in for a signer)
const owner = newKey(), agent = newKey(), mint = newKey(), vendor = newKey(), stranger = newKey();
const FUNDED = 1_000n;

// Simulation fixtures: these stand in for the official token program's setup instructions.
sim.createTestMint(mint, owner /* mint authority */, null /* no freeze authority */);

// 1. Register a spending policy: a vault for one test token, with an approval window of 1 hour
const created = await tb.createVault({ owner: addr(owner), vaultId: 1n, mint: addr(mint), approvalTtlSeconds: 3600n });
show("1.", "create vault (policy container)", created);
const vault = created.vault;
const vaultToken = newKey();
sim.createTestTokenAccount(vaultToken, mint, Pubkey.from(vault).toBytes(), FUNDED);
sim.createTestTokenAccount(vendor, mint, newKey(), 0n);
sim.createTestTokenAccount(stranger, mint, newKey(), 0n);
show("1.", "bind vault token account (+ prove mint unfreezable)",
  await tb.bindTokenAccount({ owner: addr(owner), vault, tokenAccount: addr(vaultToken), mint: addr(mint) }));

// 2. Authorize the agent: "pay this vendor up to 10 per payment, 50 per day, 200 in total, for 7 days;
//    anything above 8 needs my approval"
const now = (await sim.now()) / 1_000_000_000n;
show("2.", "grant agent: 10/payment, 50/day, 200 total, 7 days",
  await tb.grantAgent({ owner: addr(owner), vault, agent: addr(agent), recipients: [addr(vendor)],
    limits: { perTransaction: 10n, perDay: 50n, lifetime: 200n, approvalAbove: 8n, expiresAt: now + 7n * 86_400n } }));

// 3. Request a valid action: a 5-unit subscription payment (below the approval threshold: paid at once)
const r3 = await tb.requestPayment({ agent: addr(agent), vault, recipient: addr(vendor), amount: 5n });
show("3.", "agent pays vendor 5", r3);
if (r3.outcome !== "paid") fail("valid payment was not paid");

// 4. Execute through the policy layer with human approval: 9 units is above the threshold
const r4 = await tb.requestPayment({ agent: addr(agent), vault, recipient: addr(vendor), amount: 9n });
show("4.", "agent asks to pay vendor 9 (needs approval)", r4);
const pre = await tb.check({ vault, agent: addr(agent), recipient: addr(vendor), amount: 9n });
console.log(`     policy check for the next 9-unit request (no transaction sent): ${pre.outcome}`);
const r4b = await tb.approve({ owner: addr(owner), vault, agent: addr(agent), nonce: r4.nonce });
show("4.", "owner approves exactly that request", r4b);
if (r4b.outcome !== "approved") fail("approved payment did not execute");
show("4.", "owner approves it a second time", await tb.approve({ owner: addr(owner), vault, agent: addr(agent), nonce: r4.nonce }));

// 5. Invalid actions are rejected by the program
const r5a = await tb.requestPayment({ agent: addr(agent), vault, recipient: addr(vendor), amount: 11n });
show("5.", "agent tries 11 (above 10 per payment)", r5a);
const r5b = await tb.requestPayment({ agent: addr(agent), vault, recipient: addr(stranger), amount: 1n });
show("5.", "agent tries to pay a stranger", r5b);
const r5c = await tb.requestPayment({ agent: addr(agent), vault, recipient: addr(vendor), amount: 1n, nonce: 0n });
show("5.", "agent replays an old nonce", r5c);
const r5d = await tb.approve({ owner: addr(agent), vault, agent: addr(agent), nonce: 1n });
show("5.", "agent tries to approve for the owner", r5d);
if (r5a.ok || r5b.ok || r5c.ok || r5d.ok) fail("an invalid action was accepted");

// 6. Revoke: a request waiting for approval can never execute afterwards
const r6 = await tb.requestPayment({ agent: addr(agent), vault, recipient: addr(vendor), amount: 9n });
show("6.", "agent asks to pay 9 again (pending)", r6);
show("6.", "owner revokes the agent", await tb.revokeAgent({ owner: addr(owner), vault, agent: addr(agent) }));
const r6b = await tb.approve({ owner: addr(owner), vault, agent: addr(agent), nonce: r6.nonce });
show("6.", "owner (by mistake) approves the old request", r6b);
const r6c = await tb.requestPayment({ agent: addr(agent), vault, recipient: addr(vendor), amount: 1n });
show("6.", "revoked agent tries to pay", r6c);
if (r6b.ok || r6c.ok) fail("revocation was bypassed");

// 7. Independently read and verify the resulting state
const perm = await tb.getPermission(vault, addr(agent));
const info = await tb.getVault(vault);
const vendorBalance = await tb.getTokenBalance(addr(vendor));
console.log(`\n7.   read state: agent active=${perm.active} spent=${perm.spent} pending=${perm.pending}; vendor balance=${vendorBalance}; vault balance=${info.balance}; mint unfreezable=${info.mintUnfreezable}`);
if (vendorBalance !== 14n || info.balance !== FUNDED - 14n || perm.spent !== 14n || perm.pending !== 0n || perm.active) fail("state does not add up");
mkdirSync("out", { recursive: true });
const snapshot = await tb.exportProofLabSnapshot({ vault, agents: [addr(agent)], tokenAccounts: [addr(vendor), addr(stranger)], fundedTotal: FUNDED });
sim.saveTrace("out/trace.jsonl", snapshot);
console.log("     trace + on-chain snapshot written to out/trace.jsonl; run `npm run verify` for the independent verifier");
// 8. Who else can move the vault's tokens? (Proof Lab authority analysis)
const report = await tb.analyzeAuthorities({ vault, agents: [addr(agent)] });
console.log(`\n8.   authority analysis: ${report.summary.VERIFIED} VERIFIED, ${report.summary.UNVERIFIED} UNVERIFIED, ${report.summary.RISK} RISK (data: ${report.dataOrigin})`);
for (const f of report.findings.filter((f) => f.status === "RISK")) console.log(`     RISK  ${f.title}`);
for (const m of report.movers) console.log(`     can move: ${m.who.slice(0, 12)}… via ${m.how}, up to ${m.upTo}${m.bounded ? "" : " (not limited by agent policy)"}`);
if (report.findings.some((f) => f.status === "RISK" && !["owner-withdraw", "program-upgrade"].includes(f.id))) fail("unexpected authority risk");
console.log("\nAll demo checks passed (LOCAL SIMULATION).");
