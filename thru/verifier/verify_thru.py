#!/usr/bin/env python3
"""Independent verifier for Flowstate-on-Thru execution traces.

INDEPENDENCE: this file does not import the test client (thru/tests/fsclient.py) or the program.
It decodes the raw event bytes with its own hand-written layouts (transcribed from the packed
structs documented in thru/program/flowstate_abi.h), replays them through its own shadow state
machine, and checks the safety rules against that shadow, then against the final snapshot.

SCOPE / HONESTY: the traces come from the LOCAL SIMULATION (host build of the real program code
against a modelled Thru runtime and a modelled token program). Passing this verifier says the
recorded behaviour is consistent with the rules below. It is NOT evidence of anything on a Thru
network, and it is not an audit or formal verification.

Usage:  python3 verify_thru.py [trace.jsonl ...]     (default: thru/build/traces/*.jsonl)
Exit 0 = every trace PASS, 1 = at least one violation.
"""
import glob
import json
import os
import struct
import sys

NS_PER_DAY = 86_400 * 1_000_000_000

# op codes (first instruction byte)
OP = dict(INIT_VAULT=0, BIND_TOKEN=1, SET_AGENT=2, REVOKE=3, SET_RECIPIENT=4, REQUEST=5, APPROVE=6,
          REJECT=7, EXPIRE=8, SET_PAUSED=9, KILL=10, WITHDRAW=11)
# event kinds and their packed little-endian layouts
EV = {
    1: ("VAULT_INIT", "<B32s32s32s", ("kind", "vault", "owner", "mint")),
    2: ("TOKEN_BOUND", "<B32s32sB", ("kind", "vault", "token_account", "mint_unfreezable")),
    3: ("AGENT_SET", "<B32s32sQQQQQQ", ("kind", "vault", "agent", "per_tx", "daily", "budget", "threshold",
                                        "valid_until_ns", "epoch")),
    4: ("AGENT_REVOKED", "<B32s32sQ", ("kind", "vault", "agent", "new_epoch")),
    5: ("RECIPIENT", "<B32s32s32sB", ("kind", "vault", "agent", "recipient", "allowed")),
    6: ("PAID", "<B32s32s32sQQB", ("kind", "vault", "agent", "recipient", "amount", "nonce", "approved")),
    7: ("REQUESTED", "<B32s32s32sQQQ", ("kind", "vault", "agent", "recipient", "amount", "nonce", "expires_ns")),
    8: ("REJECTED", "<B32s32sQ", ("kind", "vault", "agent", "nonce")),
    9: ("EXPIRED", "<B32s32sQ", ("kind", "vault", "agent", "nonce")),
    10: ("INVALIDATED", "<B32s32sQ", ("kind", "vault", "agent", "nonce")),
    11: ("PAUSED", "<B32sB", ("kind", "vault", "flag")),
    12: ("KILLED", "<B32sB", ("kind", "vault", "flag")),
    13: ("WITHDRAWN", "<B32s32sQ", ("kind", "vault", "dest", "amount")),
}
# which event kinds a successful instruction may emit (exactly one event per success)
ALLOWED = {OP["INIT_VAULT"]: {"VAULT_INIT"}, OP["BIND_TOKEN"]: {"TOKEN_BOUND"}, OP["SET_AGENT"]: {"AGENT_SET"},
           OP["REVOKE"]: {"AGENT_REVOKED"}, OP["SET_RECIPIENT"]: {"RECIPIENT"},
           OP["REQUEST"]: {"PAID", "REQUESTED"}, OP["APPROVE"]: {"PAID"}, OP["REJECT"]: {"REJECTED"},
           OP["EXPIRE"]: {"EXPIRED", "INVALIDATED"}, OP["SET_PAUSED"]: {"PAUSED"}, OP["KILL"]: {"KILLED"},
           OP["WITHDRAW"]: {"WITHDRAWN"}}
OWNER_OPS = {OP[k] for k in ("BIND_TOKEN", "SET_AGENT", "REVOKE", "SET_RECIPIENT", "APPROVE",
                             "SET_PAUSED", "KILL", "WITHDRAW")}
# REJECT: the owner or the request's own agent (an agent may withdraw its own request). EXPIRE: anyone,
# but only once the deadline passed or the request is stale (checked in close()).


def decode_event(hexdata):
    raw = bytes.fromhex(hexdata)
    if not raw or raw[0] not in EV:
        raise ValueError(f"unknown event kind {raw[:1].hex()}")
    name, fmt, fields = EV[raw[0]]
    if len(raw) != struct.calcsize(fmt):
        raise ValueError(f"{name}: size {len(raw)} != {struct.calcsize(fmt)}")
    d = dict(zip(fields, struct.unpack(fmt, raw)))
    d["name"] = name
    return d


class Agent:
    def __init__(self):
        self.active = False
        self.cfg = None              # (per_tx, daily, budget, threshold, valid_until_ns)
        self.epoch = 0
        self.next_nonce = 0
        self.spent = 0
        self.reserved = 0
        self.day = 0
        self.daily_used = 0
        self.recipients = set()


class Verifier:
    def __init__(self, records, name="trace"):
        self.records = records
        self.name = name
        self.violations = []
        self.stats = dict(tx=0, ok=0, failed=0, paid_instant=0, paid_approved=0, requested=0, closed=0)

    def bad(self, i, msg):
        self.violations.append(f"{self.name} tx#{i}: {msg}")

    # ------------------------------------------------------------------ replay
    def run(self):
        recs = self.records
        if not recs or "snapshot" not in recs[-1]:
            self.violations.append(f"{self.name}: missing final snapshot")
            return self
        txs, snap = recs[:-1], recs[-1]["snapshot"]
        self.program = None
        self.vault = None
        self.owner = None
        self.mint = None
        self.flags = set()
        self.agents = {}
        self.pending = {}            # (agent, nonce) -> dict(recipient, amount, expires_ns, epoch, day)
        self.closed = {}             # (agent, nonce) -> EXECUTED / REJECTED / EXPIRED / INVALIDATED
        self.paid_total = 0
        self.withdrawn_total = 0
        self.inflow = {}             # token account hex -> received
        self.paid_keys = set()       # (agent, nonce) of every payment: at most one each
        self.paid_by_agent = {}      # aggregate, independent of the shadow counters
        last_t = 0
        for i, t in enumerate(txs):
            self.stats["tx"] += 1
            if t["time_ns"] < last_t:
                self.bad(i, "clock went backwards")
            last_t = t["time_ns"]
            if self.program is None and t["rc"] == 0 and t["events"]:
                self.program = t["program"]
            evs = t["events"]
            if t["rc"] != 0:
                self.stats["failed"] += 1
                if evs:
                    self.bad(i, f"failed transaction (rc={t['rc']:#x}) still emitted {len(evs)} event(s)")
                continue
            self.stats["ok"] += 1
            if t["program"] != self.program:
                self.bad(i, "successful transaction of a program other than Flowstate (no other program should "
                            "succeed in these traces: direct token transfers must fail)")
                continue
            op = bytes.fromhex(t["instr"])[0] if t["instr"] else None
            if op not in ALLOWED:
                self.bad(i, f"unknown op {op}")
                continue
            if len(evs) != 1:
                self.bad(i, f"op {op} succeeded with {len(evs)} events (expected exactly 1)")
                continue
            if evs[0]["program"] != self.program:
                self.bad(i, "event emitted by a foreign program")
                continue
            try:
                ev = decode_event(evs[0]["data"])
            except ValueError as e:
                self.bad(i, f"undecodable event: {e}")
                continue
            if ev["name"] not in ALLOWED[op]:
                self.bad(i, f"op {op} emitted {ev['name']}")
                continue
            if self.vault is not None and ev["vault"].hex() != self.vault:
                self.bad(i, "event names a different vault")
                continue
            if op in OWNER_OPS and self.owner is not None and t["fee_payer"] != self.owner:
                self.bad(i, f"owner-only op {op} signed by {t['fee_payer'][:12]}… (not the owner)")
            getattr(self, "on_" + ev["name"].lower())(i, t, ev)
        self.check_final(snap)
        return self

    # ------------------------------------------------------------------ events
    def agent_of(self, i, ev):
        a = self.agents.get(ev["agent"].hex())
        if a is None:
            self.bad(i, f"{ev['name']} for an unknown agent")
        return a

    def live(self, i, what):
        if "killed" in self.flags:
            self.bad(i, f"{what} after the vault was killed")
            return False
        if "paused" in self.flags:
            self.bad(i, f"{what} while the vault was paused")
            return False
        return True

    def on_vault_init(self, i, t, ev):
        if self.vault is not None:
            self.bad(i, "vault initialised twice")
        self.vault, self.owner, self.mint = ev["vault"].hex(), ev["owner"].hex(), ev["mint"].hex()
        if t["fee_payer"] != self.owner:
            self.bad(i, "vault initialised by someone other than its owner")

    def on_token_bound(self, i, t, ev):
        if getattr(self, "token_account", None):
            self.bad(i, "token account bound twice")
        self.token_account = ev["token_account"].hex()
        if ev["mint_unfreezable"]:
            self.flags.add("unfreezable")

    def on_agent_set(self, i, t, ev):
        if "killed" in self.flags:
            self.bad(i, "agent configured after kill")
        k = ev["agent"].hex()
        if k == self.owner:
            self.bad(i, "owner registered as an agent")
        a = self.agents.setdefault(k, Agent())
        per_tx, daily, budget, thr, vu = ev["per_tx"], ev["daily"], ev["budget"], ev["threshold"], ev["valid_until_ns"]
        if not (0 < per_tx <= daily <= budget) or thr > per_tx or vu <= t["time_ns"]:
            self.bad(i, f"invalid agent config accepted {per_tx, daily, budget, thr}")
        if ev["epoch"] != a.epoch:
            self.bad(i, f"AGENT_SET epoch {ev['epoch']} != shadow {a.epoch}")
        # CE-1 (owner decision 2026-10-30): limits never drop below what is already used
        if a.cfg is not None and budget < a.spent + a.reserved:
            self.bad(i, f"CE-1: budget lowered to {budget} below spent+reserved {a.spent + a.reserved}")
        if a.cfg is not None and a.day == t["time_ns"] // NS_PER_DAY and daily < a.daily_used:
            self.bad(i, f"CE-1: daily lowered to {daily} below today's use {a.daily_used}")
        a.cfg = (per_tx, daily, budget, thr, vu)
        a.active = True

    def on_agent_revoked(self, i, t, ev):
        a = self.agent_of(i, ev)
        if not a:
            return
        if not a.active:
            self.bad(i, "revoked an agent that was not active")
        a.epoch += 1
        if ev["new_epoch"] != a.epoch:
            self.bad(i, f"revocation epoch {ev['new_epoch']} != shadow {a.epoch}")
        a.active = False
        a.reserved = 0

    def on_recipient(self, i, t, ev):
        a = self.agent_of(i, ev)
        if not a:
            return
        r = ev["recipient"].hex()
        if ev["allowed"]:
            if r not in a.recipients and len(a.recipients) >= 8:
                self.bad(i, "allowlist grew beyond 8")
            a.recipients.add(r)
        else:
            a.recipients.discard(r)

    def charge_day(self, a, now, amount):
        today = now // NS_PER_DAY
        if a.day != today:
            a.day, a.daily_used = today, 0
        a.daily_used += amount
        return a.daily_used

    def check_request_rules(self, i, t, ev, a, what):
        ok = self.live(i, what)
        if t["fee_payer"] != ev["agent"].hex():
            self.bad(i, f"{what} not signed by the agent itself")
        if not a.active:
            self.bad(i, f"{what} by an inactive/revoked agent")
        per_tx, daily, budget, thr, vu = a.cfg
        if t["time_ns"] >= vu:
            self.bad(i, f"{what} with an expired agent key")
        if ev["nonce"] != a.next_nonce:
            self.bad(i, f"{what} nonce {ev['nonce']} != expected {a.next_nonce} (replay/skip)")
        if ev["amount"] == 0:
            self.bad(i, f"{what} of zero")
        if ev["recipient"].hex() not in a.recipients:
            self.bad(i, f"{what} to a recipient not on the allowlist")
        if ev["amount"] > per_tx:
            self.bad(i, f"{what} {ev['amount']} above per-tx limit {per_tx}")
        if self.charge_day(a, t["time_ns"], ev["amount"]) > daily:
            self.bad(i, f"{what} pushes daily use to {a.daily_used} > {daily}")
        if a.spent + a.reserved + ev["amount"] > budget:
            self.bad(i, f"{what} exceeds budget {budget}")
        a.next_nonce = ev["nonce"] + 1
        return ok

    def pay(self, i, ev):
        key = (ev["agent"].hex(), ev["nonce"])
        if key in self.paid_keys:
            self.bad(i, f"second payment for agent {key[0][:12]}… nonce {key[1]}")
        self.paid_keys.add(key)
        self.paid_by_agent[key[0]] = self.paid_by_agent.get(key[0], 0) + ev["amount"]
        self.paid_total += ev["amount"]
        r = ev["recipient"].hex()
        self.inflow[r] = self.inflow.get(r, 0) + ev["amount"]

    def on_paid(self, i, t, ev):
        a = self.agent_of(i, ev)
        if not a:
            return
        op = bytes.fromhex(t["instr"])[0]
        if op == OP["REQUEST"]:
            if ev["approved"]:
                self.bad(i, "instant payment flagged as approved")
            self.check_request_rules(i, t, ev, a, "instant payment")
            if ev["amount"] > a.cfg[3]:
                self.bad(i, f"instant payment {ev['amount']} above the approval threshold {a.cfg[3]}")
            a.spent += ev["amount"]
            self.stats["paid_instant"] += 1
        else:
            if not ev["approved"]:
                self.bad(i, "approved payment not flagged as approved")
            key = (ev["agent"].hex(), ev["nonce"])
            req = self.pending.pop(key, None)
            if req is None:
                self.bad(i, f"approved payment with no open request for nonce {ev['nonce']} (double execution "
                            "or never requested)")
                return
            self.closed[key] = "EXECUTED"
            if (req["recipient"], req["amount"]) != (ev["recipient"].hex(), ev["amount"]):
                self.bad(i, "approved payment differs from the request it executes")
            self.live(i, "approved payment")
            if not a.active:
                self.bad(i, "approved payment for a revoked agent")
            if req["epoch"] != a.epoch:
                self.bad(i, "approved payment of a stale (pre-revocation) request")
            if t["time_ns"] >= req["expires_ns"]:
                self.bad(i, "approved payment after the request expired")
            per_tx, daily, budget, thr, vu = a.cfg
            if t["time_ns"] >= vu:
                self.bad(i, "approved payment with an expired agent key")
            if ev["recipient"].hex() not in a.recipients:
                self.bad(i, "approved payment to a recipient no longer allowlisted")
            if ev["amount"] > per_tx:
                self.bad(i, "approved payment above the current per-tx limit")
            if a.spent + a.reserved > budget:
                self.bad(i, "approved payment exceeds the current budget")
            today = t["time_ns"] // NS_PER_DAY
            if req["day"] == today:
                if a.day != today:
                    a.day, a.daily_used = today, 0
                if a.daily_used > daily:
                    self.bad(i, "approved payment while today's use is above the daily limit")
            elif self.charge_day(a, t["time_ns"], ev["amount"]) > daily:
                self.bad(i, "approved payment charged to a new day exceeds the daily limit")
            a.reserved -= ev["amount"]
            a.spent += ev["amount"]
            self.stats["paid_approved"] += 1
        self.pay(i, ev)

    def on_requested(self, i, t, ev):
        a = self.agent_of(i, ev)
        if not a:
            return
        self.check_request_rules(i, t, ev, a, "payment request")
        if ev["amount"] <= a.cfg[3]:
            self.bad(i, "amount at/below threshold was queued instead of paid instantly")
        key = (ev["agent"].hex(), ev["nonce"])
        if key in self.pending:
            self.bad(i, "request overwrote an open request")
        self.pending[key] = dict(recipient=ev["recipient"].hex(), amount=ev["amount"], expires_ns=ev["expires_ns"],
                                 epoch=a.epoch, day=t["time_ns"] // NS_PER_DAY)
        if ev["expires_ns"] <= t["time_ns"]:
            self.bad(i, "request created already expired")
        a.reserved += ev["amount"]
        self.stats["requested"] += 1

    def close(self, i, t, ev, kind):
        a = self.agent_of(i, ev)
        if not a:
            return
        key = (ev["agent"].hex(), ev["nonce"])
        req = self.pending.pop(key, None)
        if req is None:
            self.bad(i, f"{kind} of a request that is not open")
            return
        self.closed[key] = kind
        stale = req["epoch"] != a.epoch
        if kind == "EXPIRED" and (stale or t["time_ns"] < req["expires_ns"]):
            self.bad(i, "EXPIRED before the deadline (or for a stale request)")
        if kind == "INVALIDATED" and not stale:
            self.bad(i, "INVALIDATED a request of the current epoch")
        if not stale:
            a.reserved -= req["amount"]
        if a.day == req["day"] and a.daily_used >= req["amount"]:
            a.daily_used -= req["amount"]
        self.stats["closed"] += 1

    def on_rejected(self, i, t, ev):
        if t["fee_payer"] not in (self.owner, ev["agent"].hex()):
            self.bad(i, "request rejected by someone other than the owner or its agent")
        self.close(i, t, ev, "REJECTED")

    def on_expired(self, i, t, ev):
        self.close(i, t, ev, "EXPIRED")

    def on_invalidated(self, i, t, ev):
        self.close(i, t, ev, "INVALIDATED")

    def on_paused(self, i, t, ev):
        if "killed" in self.flags:
            self.bad(i, "pause state changed after kill (kill must be irreversible)")
        if ev["flag"]:
            self.flags.add("paused")
        else:
            self.flags.discard("paused")

    def on_killed(self, i, t, ev):
        if "killed" in self.flags:
            self.bad(i, "killed twice")
        self.flags |= {"killed", "paused"}

    def on_withdrawn(self, i, t, ev):
        self.withdrawn_total += ev["amount"]
        d = ev["dest"].hex()
        self.inflow[d] = self.inflow.get(d, 0) + ev["amount"]

    # ------------------------------------------------------------------ final state
    def check_final(self, s):
        n = len(self.records) - 1
        if s["vault"] != self.vault:
            self.bad(n, "snapshot names a different vault")
        vt = s["vault_token"]
        expect = s["funded"] - self.paid_total - self.withdrawn_total
        if s["vault_token_balance"] != expect:
            self.bad(n, f"vault token balance {s['vault_token_balance']} != funded - paid - withdrawn = {expect}")
        bal = s["token_balances"]
        if sum(bal.values()) != s["funded"]:
            self.bad(n, f"tracked token supply {sum(bal.values())} != funded {s['funded']} (tokens created/lost)")
        for acct, amount in bal.items():
            if acct == vt:
                continue
            if amount != self.inflow.get(acct, 0):
                self.bad(n, f"account {acct[:12]}… holds {amount}, events explain {self.inflow.get(acct, 0)}")
        for acct, got in self.inflow.items():
            if acct not in bal and got:
                self.bad(n, f"events pay {acct[:12]}… which the snapshot does not track")
        vs = s["vault_state"]
        if vs.get("total_paid") is not None and vs["total_paid"] != self.paid_total:
            self.bad(n, f"vault total_paid {vs['total_paid']} != events {self.paid_total}")
        want_flags = (2 if "killed" in self.flags else 0) | (1 if "paused" in self.flags else 0) | \
                     (4 if "unfreezable" in self.flags else 0)
        if vs["flags"] != want_flags:
            self.bad(n, f"vault flags {vs['flags']} != events {want_flags}")
        for k, a in self.agents.items():
            sa = s["agents"].get(k)
            if sa is None:
                self.bad(n, f"agent {k[:12]}… missing from snapshot")
                continue
            for field, val in (("spent", a.spent), ("reserved", a.reserved), ("next_nonce", a.next_nonce),
                               ("epoch", a.epoch), ("active", int(a.active)), ("daily_used", a.daily_used),
                               ("day", a.day)):
                if sa[field] != val:
                    self.bad(n, f"agent {k[:12]}… {field} {sa[field]} != replay {val}")
            if set(sa["recipients"]) != a.recipients:
                self.bad(n, f"agent {k[:12]}… allowlist differs from replay")
            # request accounts: every open request in the replay is PENDING on chain, every closed one is not
            REQ_FMT = "<IBBH32s32s32s32sQQQQQQ"   # fs_request_t, 184 bytes
            st_name = {1: "PENDING", 2: "EXECUTED", 3: "REJECTED", 4: "EXPIRED", 5: "INVALIDATED"}
            for nonce_s, raw in s.get("requests", {}).get(k, {}).items():
                f = struct.unpack(REQ_FMT, bytes.fromhex(raw))
                status, rnonce, ramount = f[2], f[9], f[8]
                key = (k, int(nonce_s))
                want = self.closed.get(key, "PENDING" if key in self.pending else None)
                if rnonce != int(nonce_s):
                    self.bad(n, f"request account for nonce {nonce_s} stores nonce {rnonce}")
                if want is None:
                    self.bad(n, f"request account for nonce {nonce_s} exists but no event created it")
                elif st_name.get(status) != want:
                    self.bad(n, f"request nonce {nonce_s} is {st_name.get(status, status)} on chain, replay says {want}")
            if "requests" in s:
                for (ag, nn) in list(self.pending) + [x for x in self.closed]:
                    if ag == k and str(nn) not in s["requests"].get(k, {}):
                        self.bad(n, f"request nonce {nn} in the events has no request account")
            # aggregate check, independent of the shadow state machine: with limits never lowered below
            # what is used (CE-1), everything an agent was ever paid fits inside its final lifetime budget
            if self.paid_by_agent.get(k, 0) > sa["budget"]:
                self.bad(n, f"agent {k[:12]}… was paid {self.paid_by_agent[k]} in total, above its budget {sa['budget']}")
            open_amt = sum(r["amount"] for (ag, _), r in self.pending.items() if ag == k and r["epoch"] == a.epoch)
            if a.reserved != open_amt:
                self.bad(n, f"agent {k[:12]}… reserved {a.reserved} != open current-epoch requests {open_amt}")


def verify_file(path):
    with open(path) as fh:
        recs = [json.loads(line) for line in fh if line.strip()]
    return Verifier(recs, os.path.basename(path)).run()


def main(argv):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = argv or sorted(glob.glob(os.path.join(root, "build", "traces", "*.jsonl")))
    if not paths:
        print("NOT RUN: no traces found (run thru/tests/test_properties.py first)")
        return 1
    total, failed = {}, 0
    for p in paths:
        v = verify_file(p)
        for k, x in v.stats.items():
            total[k] = total.get(k, 0) + x
        if v.violations:
            failed += 1
            print(f"FAIL {os.path.basename(p)}")
            for m in v.violations[:10]:
                print("   ", m)
    print(f"{'PASS' if not failed else 'FAIL'}: {len(paths) - failed}/{len(paths)} traces clean "
          f"(LOCAL SIMULATION traces) totals={total}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
