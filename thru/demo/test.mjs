// Demo smoke test: starts the server on a free port and drives the API (LOCAL SIMULATION).
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

test("demo server: grant, pay, approve, refuse, revoke, verify", async () => {
  const port = 3200 + Math.floor(Math.random() * 500);
  const srv = spawn(process.execPath, [fileURLToPath(new URL("server.mjs", import.meta.url))], { env: { ...process.env, PORT: String(port) } });
  try {
    await new Promise((res, rej) => { srv.stdout.on("data", (d) => String(d).includes("http://") && res()); srv.on("exit", rej); });
    const post = async (p, b = {}) => (await fetch(`http://127.0.0.1:${port}${p}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(b) })).json();
    const html = await (await fetch(`http://127.0.0.1:${port}/`)).text();
    assert.match(html, /LOCAL SIMULATION/);
    let s = await post("/api/grant", { perTransaction: 10, perDay: 50, lifetime: 200, approvalAbove: 8, days: 7 });
    assert.equal(s.permission.active, true);
    s = await post("/api/pay", { amount: 5, to: "vendor" }); assert.equal(s.log[0].result, "paid");
    s = await post("/api/pay", { amount: 9, to: "vendor" }); assert.equal(s.log[0].result, "pending");
    s = await post("/api/agent-approves", { nonce: 1 }); assert.equal(s.log[0].result, "refused");
    s = await post("/api/approve", { nonce: 1 }); assert.equal(s.log[0].result, "approved");
    s = await post("/api/pay", { amount: 11, to: "vendor" }); assert.equal(s.log[0].reason, "PER_TX");
    s = await post("/api/pay", { amount: 1, to: "stranger" }); assert.equal(s.log[0].reason, "RECIPIENT_NOT_ALLOWED");
    assert.equal((await post("/api/grant", { perTransaction: 1, perDay: 1, lifetime: 1, approvalAbove: 0, days: 7 })).log[0].reason, "INVALID_CONFIG");
    s = await post("/api/revoke"); assert.equal(s.permission.active, false);
    s = await post("/api/pay", { amount: 1, to: "vendor" }); assert.equal(s.log[0].reason, "UNKNOWN_AGENT");
    assert.equal(s.balances.vendor, "14"); assert.equal(s.vaultInfo.balance, "986");
    const v = await post("/api/verify"); assert.equal(v.pass, true, v.report);
    const a = await post("/api/authority"); assert.equal(a.dataOrigin, "local-simulation");
    assert.deepEqual(a.findings.filter((f) => f.status === "RISK").map((f) => f.id).sort(), ["owner-withdraw", "program-upgrade"]);
  } finally { srv.kill(); }
});
