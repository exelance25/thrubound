// ThruBound end-to-end test on the Thru ALPHANET test network (Node 22).
//   node alphanet-e2e.mjs <path/to/flowstate_c.bin> [out.json]
// Everything is test-only: fresh throw-away keys held in memory (never printed or saved), native THRU from the
// official faucet, and a test mint created here without a freeze authority. Prints and saves public data only:
// addresses, transaction signatures, execution results, balances.
import { readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import * as H from "./harness.mjs";

const binPath = process.argv[2];
const outPath = process.argv[3] ?? "alphanet-evidence.json";
if (!binPath) { console.error("usage: node alphanet-e2e.mjs <flowstate_c.bin> [out.json]"); process.exit(2); }
const bin = readFileSync(binPath);
const E = { network: "alphanet", rpc: H.RPC, startedAt: new Date().toISOString(),
  programSha256: createHash("sha256").update(bin).digest("hex"), programSize: bin.length, steps: [], checks: [] };
const ERR = { PER_TX: 0x100f, BAD_NONCE: 0x100c, RECIPIENT_NOT_ALLOWED: 0x100e, NOT_AGENT: 0x1004, APPROVAL_MISMATCH: 0x1017,
  NO_PENDING: 0x1013, UNKNOWN_AGENT: 0x100a };
let failures = 0;
const save = () => writeFileSync(outPath, JSON.stringify(E, null, 2));
function step(r) { E.steps.push(r); console.log(`${r.ok ? "ok  " : "FAIL"} ${r.label}  sig=${r.signature ?? "-"}  vmError=${r.vmError} user=${r.userErrorCode}`); save(); return r; }
function check(name, pass, detail) { E.checks.push({ name, pass, detail }); if (!pass) failures++; console.log(`${pass ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`); save(); }
const must = (r) => { step(r); check(r.label + " succeeds", r.ok, `vmError=${r.vmError} user=${r.userErrorCode}`); if (!r.ok) throw new Error("required step failed: " + r.label); return r; };
const refused = (r, code, why) => { step(r); const u = BigInt(r.userErrorCode ?? 0);
  check(`${why} is refused on chain`, !r.ok && (code === undefined || u === BigInt(code)),
    `vmError=${r.vmError} userErrorCode=0x${u.toString(16)}${code !== undefined ? " expected 0x" + code.toString(16) : ""}`); };
const bal = async (label) => (await H.tokenState(label)).amount;

try {
  E.chain = await H.chain(); E.bootstrap = H.bootstrap(); console.log("chain", E.chain);
  E.actors = await H.newKeys(["owner", "agent", "vendor", "stranger"]);
  for (const n of ["owner", "agent", "vendor", "stranger"]) must(await H.createEoa(n));
  for (const n of ["owner", "agent"]) {
    const r = step(await H.faucet(n, 10000n));
    check(`faucet native THRU to ${n}`, r.ok, `vmError=${r.vmError} user=${r.userErrorCode}`);
    E[`${n}Account`] = await H.account(E.actors[n]);
  }

  // test token without a freeze authority
  const m = must(await H.createMint("owner", "thrubound-e2e-" + Date.now().toString(36)));
  const ms = await H.mintState(); E.mint = ms;
  check("test mint has no freeze authority", ms.hasFreezeAuthority === false, JSON.stringify(ms));

  // deploy the program (managed program, upgrade authority = owner test key)
  const seed = "thrubound-e2e-" + Date.now().toString(36);
  const d = await H.deploy("owner", bin.toString("base64"), seed); E.deploy = d; save();
  check("program deployed via official deploy workflow", !!d.program, `program=${d.program} sha256=${d.sha256}`);
  check("deployed image hash equals local build", d.sha256 === E.programSha256, `${d.sha256} vs ${E.programSha256}`);
  E.deployInspection = await H.inspect(seed, "owner");

  E.derived = await H.derive(1n);
  must(await H.tb.initVault());
  for (const [owner, label] of [[E.derived.vault, "vaultToken"], [E.actors.vendor, "vendorToken"], [E.actors.stranger, "strangerToken"], [E.actors.owner, "ownerToken"]])
    must(await H.createTokenAccount("owner", owner, label));
  must(await H.mintTo("owner", "vaultToken", 1000n));
  const bind = must(await H.tb.bindToken(true));
  const now = BigInt(Date.now()) * 1000000n;
  must(await H.tb.setAgent({ perTx: 10n, daily: 50n, budget: 200n, threshold: 5n, validUntilNs: now + 7n * 86400n * 1000000000n }, true));
  must(await H.tb.setRecipient("vendorToken"));

  // agent payments
  must(await H.tb.request("agent pays vendor 5 (instant)", 0n, 5n, "vendorToken"));
  check("vendor received 5", (await bal("vendorToken")) === 5n);
  refused(await H.tb.request("agent tries 11 (> per-payment 10)", 1n, 11n, "vendorToken"), ERR.PER_TX, "over-limit payment");
  refused(await H.tb.request("agent pays a stranger", 1n, 3n, "strangerToken"), ERR.RECIPIENT_NOT_ALLOWED, "payment to a non-allowlisted recipient");
  refused(await H.tb.request("agent replays nonce 0", 0n, 1n, "vendorToken"), ERR.BAD_NONCE, "replayed nonce");
  refused(await H.tb.request("stranger signs as the agent", 1n, 1n, "vendorToken", false, "stranger"), ERR.NOT_AGENT, "request signed by someone else");
  must(await H.tb.request("agent asks 9 (above threshold 5 -> pending)", 1n, 9n, "vendorToken", true));
  refused(await H.tb.approve("owner approves a tampered amount (8)", 1n, { amount: 8n }), ERR.APPROVAL_MISMATCH, "tampered approval");
  must(await H.tb.approve("owner approves exactly the pending request", 1n));
  check("vendor balance 14 after approval", (await bal("vendorToken")) === 14n);
  refused(await H.tb.approve("owner approves the same request again", 1n), ERR.NO_PENDING, "second approval");

  // KSI-1: can anything other than ThruBound move the vault's tokens? (official token program, direct calls)
  const v = "vaultToken";
  refused(await H.tokenRaw("token transfer vault->owner, owner signs", "owner", [H.addresses()[v], H.addresses().ownerToken], [H.addresses().vault],
    (i) => Uint8Array.from([2, ...u16(i(H.addresses()[v])), ...u16(i(H.addresses().ownerToken)), ...u64(1n)])), undefined, "KSI-1 direct transfer by the owner key");
  refused(await H.tokenRaw("token burn vault, vault PDA named as authority (unsigned)", "owner", [H.addresses()[v], H.addresses().mint], [H.addresses().vault],
    (i) => Uint8Array.from([4, ...u16(i(H.addresses()[v])), ...u16(i(H.addresses().mint)), ...u16(i(H.addresses().vault)), ...u64(1n)])), undefined, "KSI-1 burn with the vault as unsigned authority");
  refused(await H.tokenRaw("token burn vault, owner as authority", "owner", [H.addresses()[v], H.addresses().mint], [],
    (i) => Uint8Array.from([4, ...u16(i(H.addresses()[v])), ...u16(i(H.addresses().mint)), ...u16(0), ...u64(1n)])), undefined, "KSI-1 burn by the owner key");
  refused(await H.tokenRaw("token close_account vault -> owner", "owner", [H.addresses()[v], H.addresses().ownerToken], [H.addresses().vault],
    (i) => Uint8Array.from([5, ...u16(i(H.addresses()[v])), ...u16(i(H.addresses().ownerToken)), ...u16(i(H.addresses().vault))])), undefined, "KSI-1 close of the vault token account");
  refused(await H.tokenRaw("token freeze vault (mint has no freeze authority)", "owner", [H.addresses()[v]], [H.addresses().mint],
    (i) => Uint8Array.from([6, ...u16(i(H.addresses()[v])), ...u16(i(H.addresses().mint)), ...u16(0)])), undefined, "KSI-1 freeze of the vault token account");
  refused(await H.tokenRaw("token transfer vault->agent token, agent signs", "agent", [H.addresses()[v], H.addresses().vendorToken], [],
    (i) => Uint8Array.from([2, ...u16(i(H.addresses()[v])), ...u16(i(H.addresses().vendorToken)), ...u64(1n)])), undefined, "KSI-1 direct transfer by the agent key");
  check("vault balance unchanged by the KSI-1 probes (986)", (await bal(v)) === 986n);

  // revoke, then payments are refused; owner withdraws
  must(await H.tb.revoke());
  refused(await H.tb.request("revoked agent tries to pay 1", 2n, 1n, "vendorToken"), ERR.UNKNOWN_AGENT, "payment after revocation");
  must(await H.tb.withdraw(100n, "ownerToken"));
  E.finalBalances = { vault: await bal(v), vendor: await bal("vendorToken"), owner: await bal("ownerToken") };
  check("final balances vault 886 / vendor 14 / owner 100", E.finalBalances.vault === 886n && E.finalBalances.vendor === 14n && E.finalBalances.owner === 100n,
    JSON.stringify(E.finalBalances, (_, x) => (typeof x === "bigint" ? x.toString() : x)));
} catch (e) {
  failures++; E.error = String(e?.stack ?? e).slice(0, 2000); console.error("ERROR", E.error);
}
E.addresses = H.addresses(); E.finishedAt = new Date().toISOString();
E.summary = { checks: E.checks.length, passed: E.checks.filter((c) => c.pass).length, failed: failures };
E.note = "Alphanet test network. Throw-away test keys (never saved), faucet native THRU, test mint without freeze authority. Not mainnet. Not an audit.";
writeFileSync(outPath, JSON.stringify(E, (_, x) => (typeof x === "bigint" ? x.toString() : x), 2));
console.log(JSON.stringify(E.summary));
process.exit(failures ? 1 : 0);

function u16(v) { return [v & 255, (v >> 8) & 255]; }
function u64(v) { const o = []; for (let i = 0n; i < 8n; i++) o.push(Number((v >> (8n * i)) & 255n)); return o; }
