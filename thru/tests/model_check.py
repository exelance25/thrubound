#!/usr/bin/env python3
"""Bounded exhaustive state exploration (explicit-state model checking) of the REAL program code.

WHAT THIS IS: breadth-first search over every sequence of the actions below, up to DEPTH steps,
with duplicate states merged. It uses tiny limits so that every limit can be hit within a few steps.
Each transition executes the actual compiled program (host build, LOCAL SIMULATION of the Thru
runtime and a MODEL of the token program). Every reached state and every transition is checked.

WHAT THIS IS NOT: a proof for unbounded sequences or for all parameter values, and not evidence
about a real Thru VM. See docs/INVARIANT_PROOF_REVIEW.md for how this fits with the other evidence.

Usage: python3 model_check.py [depth]   (default 6). Exit 1 on any violation, printing a counterexample.
"""
import collections
import struct
import sys
import time

import fsclient as F
from fsclient import C, NS_PER_DAY, err_name, key

DEPTH = int(sys.argv[1]) if len(sys.argv) > 1 else 6
PER_TX, DAILY, BUDGET, THRESHOLD, FUNDED, TTL_S = 3, 5, 7, 1, 4, 300   # FUNDED < BUDGET: failed transfers are reachable


class Model:
    def __init__(self):
        w = F.setup_world(funded=FUNDED, per_tx=PER_TX, daily=DAILY, budget=BUDGET, threshold=THRESHOLD, n_recipients=2)
        self.s, self.fs, self.o, self.ag, self.v, self.vt = w["s"], w["fs"], w["owner"], w["agent"], w["vault"], w["vault_token"]
        self.r0, self.r1 = w["recipients"]
        self.fs.set_recipient(self.o, self.v, self.ag, self.r1, False)          # r1: a valid token account, NOT allowlisted
        self.dest = key("owner-dest")
        self.s.put_token_account(self.dest, w["mint"], self.o, 0)
        self.ttl_ns = self.fs.vault(self.v)["ttl_ns"]
        self.addrs = [self.v, self.vt, self.r0, self.r1, self.dest, self.fs.agent_addr(self.v, self.ag)] + \
                     [self.fs.request_addr(self.v, self.ag, n) for n in range(DEPTH + 2)]

    # ---------------------------------------------------------------- state save / restore
    def save(self):
        accts = tuple((a, self.s.account(a)) for a in self.addrs)
        return (self.s.now, accts)

    def load(self, st):
        now, accts = st
        self.s.lib.sim_reset(self.s.program)
        for a, acc in accts:
            if acc is not None:
                self.s.put_account(a, acc[0], acc[1])
        self.s.set_time(now)

    # ---------------------------------------------------------------- views
    def agent(self):
        return self.fs.agent(self.v, self.ag)

    def bal(self, a):
        t = self.s.token(a)
        return t["amount"] if t else 0

    def pending(self):
        ad = self.agent()
        out = []
        for n in range(ad["next_nonce"] if ad else 0):
            r = self.fs.request(self.v, self.ag, n)
            if r and r["status"] == C["FS_REQ_PENDING"]:
                out.append(n)
        return out

    # ---------------------------------------------------------------- actions
    def actions(self):
        acts = [("req", a) for a in (1, 2, 3, 4)] + [("req_r1", 1), ("revoke",), ("regrant",), ("lower",),
                ("pause",), ("unpause",), ("kill",), ("day",), ("past_ttl",), ("past_key_expiry",), ("withdraw", 1),
                ("agent_approves",), ("req_old_nonce", 1)]
        for n in self.pending():
            acts += [("approve", n), ("reject", n), ("expire", n), ("approve_tampered", n)]
        return acts

    def run(self, act):
        fs, s, o, ag, v = self.fs, self.s, self.o, self.ag, self.v
        k = act[0]
        if k == "req":
            return fs.request_payment(ag, v, self.r0, act[1])
        if k == "req_r1":
            return fs.request_payment(ag, v, self.r1, act[1])
        if k == "approve":
            return fs.approve(o, v, ag, act[1])
        if k == "req_old_nonce":     # replay: reuse nonce 0 once it has been consumed
            ad = self.agent()
            return fs.request_payment(ag, v, self.r0, act[1], nonce=0) if ad["next_nonce"] > 0 else (C["FS_ERR_BAD_NONCE"], [])
        if k == "approve_tampered":  # an approval whose amount differs from the request by one unit
            b = fs.approval_for(v, ag, act[1])
            b["amount"] += 1
            return fs.approve(o, v, ag, act[1], approval=b)
        if k == "agent_approves":
            p = self.pending()
            return fs.approve(o, v, ag, p[0], signer=ag) if p else (C["FS_ERR_NO_PENDING"], [])
        if k == "reject":
            return fs.reject(o, v, ag, act[1])
        if k == "expire":
            return fs.expire(key("anyone"), v, ag, act[1])
        if k == "revoke":
            return fs.revoke(o, v, ag)
        if k == "regrant":
            return fs.set_agent(o, v, ag, PER_TX, DAILY, BUDGET, THRESHOLD, s.now + 30 * NS_PER_DAY)
        if k == "lower":    # CE-1 probe: an otherwise valid config with a smaller budget and daily limit
            return fs.set_agent(o, v, ag, 2, 2, 2, 1, s.now + 30 * NS_PER_DAY)
        if k == "pause":
            return fs.set_paused(o, v, True)
        if k == "unpause":
            return fs.set_paused(o, v, False)
        if k == "kill":
            return fs.kill(o, v)
        if k == "withdraw":
            return fs.withdraw(o, v, self.dest, act[1])
        if k == "day":
            s.set_time((s.now // NS_PER_DAY + 1) * NS_PER_DAY + 10**9)
            return (0, [])
        if k == "past_key_expiry":
            s.set_time(self.agent()["valid_until_ns"] + 10**9)
            return (0, [])
        if k == "past_ttl":
            s.set_time(s.now + self.ttl_ns + 10**9)
            return (0, [])
        raise ValueError(k)

    # ---------------------------------------------------------------- checks
    def check_state(self):
        bad = []
        ad, vd = self.agent(), self.fs.vault(self.v)
        if ad["spent"] + ad["reserved"] > ad["budget"]:
            bad.append("S1 spent + reserved > budget")
        if ad["day"] == self.s.now // NS_PER_DAY and ad["daily_used"] > ad["daily"]:
            bad.append("S2 daily_used > daily (same day)")
        pend = sum(self.fs.request(self.v, self.ag, n)["amount"] for n in self.pending()
                   if self.fs.request(self.v, self.ag, n)["epoch"] == ad["epoch"])
        if pend != ad["reserved"]:
            bad.append(f"S3 reserved {ad['reserved']} != open current-epoch requests {pend}")
        if self.bal(self.vt) + self.bal(self.r0) + self.bal(self.r1) + self.bal(self.dest) != FUNDED:
            bad.append("S4 tokens created or destroyed")
        if vd["total_paid"] != ad["spent"]:
            bad.append("S5 vault total_paid != agent spent (single agent)")
        if self.bal(self.r0) != ad["spent"]:
            bad.append("S6 recipient balance != spent")
        if (vd["flags"] & C["FS_VAULT_KILLED"]) and not (vd["flags"] & C["FS_VAULT_PAUSED"]):
            bad.append("S8 a killed vault is not paused")
        if self.bal(self.r1) != 0:
            bad.append("S7 a non-allowlisted recipient received tokens")
        return bad

    def check_transition(self, act, rc, before, after, pre):
        bad = []
        if rc != 0 and act[0] not in ("day", "past_ttl", "past_key_expiry") and before != after:
            bad.append("T1 a failed transaction changed state")
        paid = self.bal(self.r0) - pre["r0"]
        if paid:
            if pre["paused"]:
                bad.append("T2 payment while paused or killed")
            if not pre["active"] and act[0] == "req":
                bad.append("T3 payment requested by an inactive agent")
            if pre["expired"]:
                bad.append("T4 payment with an expired agent key")
            if paid > PER_TX:
                bad.append("T5 payment above the per-transaction limit")
            if act[0] == "req" and act[1] > THRESHOLD:
                bad.append("T6 above-threshold amount paid without approval")
            if act[0] not in ("req", "approve"):
                bad.append(f"T7 tokens reached the recipient through '{act[0]}'")
        if act[0] == "req" and rc == 0 and act[1] > PER_TX:
            bad.append("T10 a request above the per-transaction limit was accepted")
        if act[0] == "req" and rc == 0 and (pre["expired"] or not pre["active"] or pre["paused"]):
            bad.append("T11 a request was accepted from an expired/inactive agent or a paused vault")
        if act[0] == "req_old_nonce" and rc == 0:
            bad.append("T12 a consumed nonce was accepted again")
        if act[0] == "approve_tampered" and rc == 0:
            bad.append("T13 an approval that does not match the request was accepted")
        if act[0] == "agent_approves" and rc == 0:
            bad.append("T8 the agent approved its own request")
        if pre["killed"] and not (self.fs.vault(self.v)["flags"] & C["FS_VAULT_KILLED"]):
            bad.append("T9 kill was undone")
        return bad

    def pre(self):
        ad, vd = self.agent(), self.fs.vault(self.v)
        return {"r0": self.bal(self.r0), "active": ad["active"], "expired": self.s.now >= ad["valid_until_ns"],
                "paused": bool(vd["flags"] & (C["FS_VAULT_PAUSED"] | C["FS_VAULT_KILLED"])),
                "killed": bool(vd["flags"] & C["FS_VAULT_KILLED"])}


def main():
    t0 = time.time()
    m = Model()
    root = m.save()
    seen = {root: None}                              # state -> (parent, action) for counterexamples
    frontier = [root]
    transitions = 0
    outcomes = collections.Counter()
    for depth in range(1, DEPTH + 1):
        nxt = []
        for st in frontier:
            m.load(st)
            for act in m.actions():
                m.load(st)
                pre = m.pre()
                rc, _ = m.run(act)
                after = m.save()
                transitions += 1
                outcomes[f"{act[0]}:{'ok' if rc == 0 else err_name(rc)}"] += 1
                bad = m.check_transition(act, rc, st, after, pre) + m.check_state()
                if bad:
                    path, cur = [act], st
                    while seen.get(cur):
                        cur, a = seen[cur]
                        path.append(a)
                    print("VIOLATION:", bad, "\ncounterexample (from the initial state):", list(reversed(path)))
                    return 1
                if after not in seen:
                    seen[after] = (st, act)
                    nxt.append(after)
        frontier = nxt
        print(f"depth {depth}: {len(seen):>8} distinct states, {transitions:>9} transitions checked")
    print(f"PASS: no violation up to depth {DEPTH} ({len(seen)} states, {transitions} transitions, "
          f"{time.time() - t0:.1f}s). Limits per_tx={PER_TX} daily={DAILY} budget={BUDGET} threshold={THRESHOLD} funded={FUNDED}.")
    print("outcomes:", dict(sorted(outcomes.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
