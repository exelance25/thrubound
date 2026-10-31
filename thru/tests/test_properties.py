"""C. Property / invariant tests — random operation sequences against the LOCAL SIMULATION
(host build of the real program code, not the Thru VM). Fixed seeds; every run writes a trace
to thru/build/traces/ for the independent verifier (thru/verifier/verify_thru.py).

Invariants checked after EVERY transaction:
  P1  a failed transaction changes no account and emits no event
  P2  after a successful commit/approval: spent + reserved <= budget  (current limits)
  P3  after a successful commit/approval: daily_used <= daily        (UTC day window)
  P4  no executed payment exceeds per_tx at the moment it executes
  P5  successful requests of an agent carry nonces 0,1,2,... with no repeat
  P6  nothing executes while paused, killed, revoked or with an expired key
  P7  every payment has exactly one accounting effect (recipient +x, vault -x, spent +x, total_paid +x)
  P8  reserved == sum of pending requests of the agent's current epoch
  P9  vault token balance == funded - paid - withdrawn
  P10 direct token-program transfers out of the vault never succeed
  P11 an approval executes only with all bound fields equal to the request
  P12 (CE-1, owner decision 2026-10-30) in EVERY reachable state, not only after payments:
      spent + reserved <= budget, and daily_used <= daily while the counter's day is today
Coverage gates: each risky path must actually be reached (non-vacuous)."""
import collections
import os
import random
import struct
import unittest

import fsclient as F
from fsclient import C, NS_PER_DAY, err_name, key

SEEDS = int(os.environ.get("FS_PROP_SEEDS", "30"))
STEPS = int(os.environ.get("FS_PROP_STEPS", "300"))
TRACE_DIR = os.path.join(F.ROOT, "build", "traces")


class World:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.seed = seed
        w = F.setup_world(n_recipients=2, funded=500_000_000)
        self.s, self.fs = w["s"], w["fs"]
        self.o, self.x, self.v, self.vt, self.mint = w["owner"], w["attacker"], w["vault"], w["vault_token"], w["mint"]
        self.funded = 500_000_000
        self.agents = [w["agent"], key("agent-b")]
        self.recips = list(w["recipients"])
        self.r_unlisted = key("prop-unlisted")
        self.s.put_token_account(self.r_unlisted, self.mint, key("u"), 0)
        self.r_wrongmint = key("prop-wrongmint")
        self.s.put_token_account(self.r_wrongmint, key("other-mint"), key("w"), 0)
        assert self.fs.set_agent(self.o, self.v, self.agents[1], 20_000_000, 60_000_000, 150_000_000, 5_000_000, self.s.now + 3 * NS_PER_DAY)[0] == 0
        for r in self.recips + [self.r_wrongmint]:
            assert self.fs.set_recipient(self.o, self.v, self.agents[1], r, True)[0] == 0
        self.used_nonces = collections.defaultdict(list)
        self.paid = 0
        self.withdrawn = 0
        self.cov = collections.Counter()
        self.violations = []

    # ------------------------------------------------------------- state snapshot
    def snapshot(self):
        snap = {"vault": self.s.account(self.v)}
        for a in self.agents:
            snap["agent", a] = self.s.account(self.fs.agent_addr(self.v, a))
            ad = self.fs.agent(self.v, a)
            if ad:
                for n in range(ad["next_nonce"] + 2):
                    snap["req", a, n] = self.s.account(self.fs.request_addr(self.v, a, n))
        for t in self.recips + [self.vt, self.r_unlisted, self.r_wrongmint, key("owner-dest")]:
            snap["tok", t] = self.s.account(t)
        return snap

    def bad(self, msg):
        self.violations.append(f"seed {self.seed} step {self.step}: {msg}")

    # ------------------------------------------------------------- actions
    def act(self):
        r = self.rng.random
        choice = self.rng.choices(
            ["request", "approve", "approve_tampered", "reject", "expire", "set_agent", "revoke", "recipient",
             "pause", "kill", "withdraw", "time", "direct", "unauth", "stale_scenario", "boundary",
             "budget_scenario", "lower_below"],
            weights=[30, 16, 4, 5, 5, 6, 2, 3, 3, 0.02, 2, 10, 3, 4, 3, 6, 3, 3])[0]
        a = self.rng.choice(self.agents)
        ad = self.fs.agent(self.v, a)
        if choice == "request":
            rec = self.rng.choice(self.recips + [self.r_unlisted, self.r_wrongmint] if r() < 0.15 else self.recips)
            per = ad["per_tx"] if ad else 1
            amt = self.rng.choice([1, per // 3 + 1, per // 2, per, per + 1, ad["threshold"] if ad else 1, self.rng.randint(1, max(1, per))])
            nonce = None if r() < 0.9 else self.rng.randint(0, (ad["next_nonce"] + 2) if ad else 2)
            pending = None if r() < 0.95 else (r() < 0.5)
            return "request", (a, rec, amt, nonce, pending), lambda: self.fs.request_payment(a, self.v, rec, amt, nonce=nonce, pending=pending)
        if choice in ("approve", "approve_tampered", "reject", "expire") and ad:
            pending = [n for n in range(ad["next_nonce"]) if (self.fs.request(self.v, a, n) or {}).get("status") == C["FS_REQ_PENDING"]]
            n = self.rng.choice(pending) if pending and self.rng.random() < 0.85 else self.rng.randint(0, max(0, ad["next_nonce"] - 1))
            req = self.fs.request(self.v, a, n)
            if not req:
                return None
            if choice == "approve":
                return "approve", (a, n), lambda: self.fs.approve(self.o, self.v, a, n)
            if choice == "approve_tampered":
                b = self.fs.approval_for(self.v, a, n)
                f = self.rng.choice(["amount", "nonce", "expires_ns", "recipient"])
                b[f] = (b[f] + 1) if isinstance(b[f], int) else self.rng.choice([x for x in self.recips if x != b[f]] or [key("zz")])
                return "approve_tampered", (a, n), lambda: self.fs.approve(self.o, self.v, a, n, approval=b, recipient_token=req["recipient"])
            if choice == "reject":
                who = self.rng.choice([self.o, a, self.x])
                return "reject", (a, n, who), lambda: self.fs.reject(who, self.v, a, n)
            return "expire", (a, n), lambda: self.fs.expire(self.x, self.v, a, n)
        if choice == "boundary" and ad:
            # boundary values: exactly the remaining daily / lifetime allowance, and one above it
            today = self.s.now // NS_PER_DAY
            rem_d = ad["daily"] - (ad["daily_used"] if ad["day"] == today else 0)
            rem_l = ad["budget"] - ad["spent"] - ad["reserved"]
            cands = [x for x in (rem_d, rem_d + 1, rem_l, rem_l + 1) if 1 <= x <= ad["per_tx"]]
            amt = self.rng.choice(cands) if cands else max(1, min(rem_d, rem_l) + 1)
            rec = self.rng.choice(self.recips)
            return "request", (a, rec, amt, None, None), lambda: self.fs.request_payment(a, self.v, rec, amt)
        if choice == "budget_scenario" and ad and ad["active"]:
            # valid reconfiguration: budget just above what is committed, then ask one unit past it
            committed = ad["spent"] + ad["reserved"]
            nb = max(committed + self.rng.randint(1, ad["per_tx"]), ad["daily"])
            r_set = self.fs.set_agent(self.o, self.v, a, ad["per_tx"], ad["daily"], nb, ad["threshold"], ad["valid_until_ns"])
            if r_set[0] != 0:
                return None
            ad2 = self.fs.agent(self.v, a)
            amt = min(ad2["per_tx"], ad2["budget"] - ad2["spent"] - ad2["reserved"] + 1)
            rec = self.rng.choice(self.recips)
            return "request", (a, rec, amt, None, None), lambda: self.fs.request_payment(a, self.v, rec, amt)
        if choice == "lower_below" and ad:
            # CE-1: an otherwise valid config whose budget (or today's daily) is below what is already used
            committed = ad["spent"] + ad["reserved"]
            today = self.s.now // NS_PER_DAY
            vu = self.s.now + 2 * NS_PER_DAY
            if ad["day"] == today and ad["daily_used"] >= 2 and r() < 0.5:
                d = ad["daily_used"] - 1
                cfg = (min(ad["per_tx"], d), d, max(ad["budget"], committed, d), min(ad["threshold"], min(ad["per_tx"], d)), vu)
            elif committed >= 2:
                b = committed - 1
                pt = min(ad["per_tx"], b)
                cfg = (pt, pt, b, min(ad["threshold"], pt), vu)
            else:
                return None
            return "lower_below", (a,) + cfg, lambda: self.fs.set_agent(self.o, self.v, a, *cfg)
        if choice == "set_agent":
            base = self.rng.choice([(50_000_000, 200_000_000, 1_000_000_000, 10_000_000), (20_000_000, 60_000_000, 150_000_000, 5_000_000),
                                    (10_000_000, 15_000_000, 40_000_000, 10_000_000), (60_000_000, 50_000_000, 100_000_000, 1)])  # last one invalid
            vu = self.s.now + self.rng.choice([3600, 6 * 3600, 2 * 86400, 10 * 86400]) * 10**9
            return "set_agent", (a,), lambda: self.fs.set_agent(self.o, self.v, a, *base, vu)
        if choice == "revoke":
            return "revoke", (a,), lambda: self.fs.revoke(self.o, self.v, a)
        if choice == "recipient":
            rec = self.rng.choice(self.recips + [self.r_unlisted])
            on = r() < 0.6
            return "recipient", (a, rec, on), lambda: self.fs.set_recipient(self.o, self.v, a, rec, on)
        if choice == "stale_scenario" and ad:
            # revoke -> re-add -> try to approve a request from the old generation
            pending = [n for n in range(ad["next_nonce"]) if (self.fs.request(self.v, a, n) or {}).get("status") == C["FS_REQ_PENDING"]]
            if not pending:
                return None
            n = pending[0]
            self.fs.revoke(self.o, self.v, a)
            self.fs.set_agent(self.o, self.v, a, ad["per_tx"], ad["daily"], ad["budget"], ad["threshold"], self.s.now + 2 * NS_PER_DAY)
            return "approve_stale", (a, n), lambda: self.fs.approve(self.o, self.v, a, n)
        if choice == "pause":
            p = r() < 0.25
            return "pause", (p,), lambda: self.fs.set_paused(self.o, self.v, p)
        if choice == "kill":
            return "kill", (), lambda: self.fs.kill(self.o, self.v)
        if choice == "withdraw":
            dest = key("owner-dest")
            if not self.s.account(dest):
                self.s.put_token_account(dest, self.mint, self.o, 0)
            amt = self.rng.randint(1, 3_000_000)
            return "withdraw", (amt,), lambda: self.fs.withdraw(self.o, self.v, dest, amt)
        if choice == "time":
            dt = self.rng.choice([60, 3600, 6 * 3600, 86_400, 2 * 86_400])
            if r() < 0.3:   # land just before or after a UTC midnight
                mid = (self.s.now // NS_PER_DAY + 1) * NS_PER_DAY
                self.s.set_time(mid + self.rng.choice([-2, 1]) * 10**9)
            else:
                self.s.advance(dt)
            return None
        if choice == "direct":
            who = self.rng.choice([self.x, a, self.o])
            return "direct", (who,), lambda: F.direct_transfer(self.s, who, self.vt, self.recips[0], 1)
        if choice == "unauth":
            k = self.rng.randint(0, 2)
            if k == 0:
                return "unauth", (), lambda: self.fs.set_paused(self.o, self.v, True, signer=self.x)
            if k == 1:
                return "unauth", (), lambda: self.fs.request_payment(a, self.v, self.recips[0], 1, signer=self.x)
            return "unauth", (), lambda: self.fs.withdraw(self.o, self.v, self.recips[0], 1, signer=self.x)
        return None

    # ------------------------------------------------------------- one step
    def step_once(self, i):
        self.step = i
        planned = self.act()
        if not planned:
            return
        kind, args, run = planned
        vd0 = self.fs.vault(self.v)
        ag0 = {a: self.fs.agent(self.v, a) for a in self.agents}
        snap0 = self.snapshot()
        bal0 = {t: (self.s.token(t) or {}).get("amount") for t in self.recips + [self.vt, self.r_unlisted, self.r_wrongmint, key("owner-dest")]}
        rc, ev = run()
        self.cov[kind + (":ok" if rc == 0 else ":fail")] += 1
        if rc != 0:
            self.cov["err:" + err_name(rc)] += 1
            if snap0 != self.snapshot():
                self.bad(f"P1 failed {kind} changed state ({err_name(rc)})")
            if ev:
                self.bad(f"P1 failed {kind} emitted events")
            return
        vd1 = self.fs.vault(self.v)
        paid_events = [e for p, e in ev if e[0] == C["FS_EV_PAID"]]
        if kind == "direct":
            self.bad("P10 direct token transfer out of the vault succeeded")
        if kind in ("unauth", "approve_tampered", "approve_stale"):
            self.bad(f"{'P11' if kind == 'approve_tampered' else 'P6'} {kind} succeeded")
        if kind in ("request", "approve"):
            a = args[0]
            a0, a1 = ag0[a], self.fs.agent(self.v, a)
            if vd0["flags"] & (C["FS_VAULT_PAUSED"] | C["FS_VAULT_KILLED"]) or not a0["active"] or self.s.now >= a0["valid_until_ns"]:
                self.bad(f"P6 {kind} succeeded while paused/killed/revoked/expired")
            if a1["spent"] + a1["reserved"] > a1["budget"]:
                self.bad("P2 budget exceeded")
            if a1["daily_used"] > a1["daily"]:
                self.bad("P3 daily exceeded")
            if kind == "request":
                n = a0["next_nonce"]
                if args[3] is not None and args[3] != n:
                    self.bad("P5 a non-next nonce was accepted")
                if n in self.used_nonces[a]:
                    self.bad("P5 nonce reused")
                self.used_nonces[a].append(n)
        for e in paid_events:
            agent, recipient = e[33:65], e[65:97]
            amount, nonce = struct.unpack("<QQ", e[97:113])
            a0, a1 = ag0[agent], self.fs.agent(self.v, agent)
            if amount > a0["per_tx"] and amount > a1["per_tx"]:
                self.bad("P4 payment above per_tx")
            d_rec = self.s.token(recipient)["amount"] - bal0[recipient]
            d_vault = bal0[self.vt] - self.s.token(self.vt)["amount"]
            if (d_rec, d_vault, a1["spent"] - a0["spent"], vd1["total_paid"] - vd0["total_paid"]) != (amount, amount, amount, amount):
                self.bad(f"P7 accounting effect mismatch for payment {amount}")
            self.paid += amount
            self.cov["paid:approved" if e[-1] else "paid:instant"] += 1
        if kind == "withdraw":
            self.withdrawn += args[0]
        if kind == "approve":
            self.cov["approve:executed"] += 1

    def check_global(self):
        for a in self.agents:
            ad = self.fs.agent(self.v, a)
            if not ad:
                continue
            pend = 0
            for n in range(ad["next_nonce"]):
                r = self.fs.request(self.v, a, n)
                if r and r["status"] == C["FS_REQ_PENDING"] and r["epoch"] == ad["epoch"]:
                    pend += r["amount"]
            if pend != ad["reserved"]:
                self.bad(f"P8 reserved {ad['reserved']} != pending {pend}")
            if ad["spent"] + ad["reserved"] > ad["budget"]:
                self.bad(f"P12 spent {ad['spent']} + reserved {ad['reserved']} > budget {ad['budget']}")
            if ad["day"] == self.s.now // NS_PER_DAY and ad["daily_used"] > ad["daily"]:
                self.bad(f"P12 daily_used {ad['daily_used']} > daily {ad['daily']}")
        if self.s.token(self.vt)["amount"] != self.funded - self.paid - self.withdrawn:
            self.bad("P9 vault token balance != funded - paid - withdrawn")


class PropertyCampaign(unittest.TestCase):
    def test_random_sequences_hold_all_invariants(self):
        os.makedirs(TRACE_DIR, exist_ok=True)
        total = collections.Counter()
        violations = []
        for seed in range(1, SEEDS + 1):
            w = World(seed)
            for i in range(STEPS):
                w.step_once(i)
                w.check_global()          # after every step: P8, P9, P12
            w.check_global()
            violations += w.violations
            total.update(w.cov)
            agents = {a.hex(): w.fs.agent(w.v, a) for a in w.agents}
            snap = {"vault": w.v.hex(), "vault_token": w.vt.hex(), "funded": w.funded, "owner": w.o.hex(),
                    "vault_state": {k: (v.hex() if isinstance(v, bytes) else v) for k, v in w.fs.vault(w.v).items()},
                    "vault_token_balance": w.s.token(w.vt)["amount"],
                    "agents": {k: {kk: (vv.hex() if isinstance(vv, bytes) else [x.hex() for x in vv] if isinstance(vv, list) else vv) for kk, vv in v.items() if kk != "recipients_raw"} for k, v in agents.items() if v},
                    # raw request-account bytes, decoded independently by the verifier
                    "requests": {a.hex(): {str(n): w.s.account(w.fs.request_addr(w.v, a, n))[1].hex()
                                           for n in range(w.fs.agent(w.v, a)["next_nonce"])
                                           if w.s.account(w.fs.request_addr(w.v, a, n))}
                                 for a in w.agents if w.fs.agent(w.v, a)},
                    "token_balances": {t.hex(): w.s.token(t)["amount"] for t in w.recips + [w.vt, w.r_unlisted, key("owner-dest")] if w.s.account(t)}}
            w.s.save_trace(os.path.join(TRACE_DIR, f"seed-{seed:02d}.jsonl"), snapshot=snap)
        self.__class__.coverage = total
        print("\n  coverage:", dict(sorted(total.items())))
        self.assertEqual(violations, [], "\n".join(violations[:20]))
        # coverage gates: every risky path must actually have been exercised
        gates = {
            "instant payments": total["paid:instant"], "approved payments": total["paid:approved"],
            "per_tx blocks": total["err:FS_ERR_PER_TX"], "daily blocks": total["err:FS_ERR_DAILY"],
            "budget blocks": total["err:FS_ERR_BUDGET"], "bad nonce": total["err:FS_ERR_BAD_NONCE"],
            "stale approvals blocked": total["err:FS_ERR_STALE_REQUEST"], "expired-key blocks": total["err:FS_ERR_AGENT_EXPIRED"],
            "paused blocks": total["err:FS_ERR_PAUSED"], "allowlist blocks": total["err:FS_ERR_RECIPIENT_NOT_ALLOWED"],
            "wrong token": total["err:FS_ERR_WRONG_TOKEN"], "approval mismatch": total["err:FS_ERR_APPROVAL_MISMATCH"],
            "unauthorized": total["err:FS_ERR_UNAUTHORIZED"], "direct transfers refused by token AUTH": total["err:0x2006"],
            "expired/stale closes": total["expire:ok"], "rejections": total["reject:ok"],
            "CE-1 lowering refused": total["lower_below:fail"],
        }
        # CE-1: lowering a limit below what is already used must never succeed
        self.assertEqual(total["lower_below:ok"], 0, "CE-1: a limit was lowered below the amount already used")
        thin = {k: n for k, n in gates.items() if n < 20}
        self.assertEqual(thin, {}, f"too thin (< 20 hits over all seeds): {thin}")


if __name__ == "__main__":
    unittest.main()
