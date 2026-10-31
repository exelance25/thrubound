"""Mutation tests for the independent verifier: every tampered trace must be flagged, and the
untouched traces must pass. Uses the LOCAL SIMULATION traces in thru/build/traces/."""
import copy
import glob
import os
import struct
import unittest

import verify_thru as V

TRACES = sorted(glob.glob(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "traces",
                                       "*.jsonl")))


def load(path):
    import json
    with open(path) as fh:
        return [json.loads(line) for line in fh if line.strip()]


def ev_name(t):
    return V.decode_event(t["events"][0]["data"])["name"] if t["rc"] == 0 and t["events"] else None


def patch_event(t, **fields):
    d = V.decode_event(t["events"][0]["data"])
    name, fmt, names = V.EV[d["kind"]]
    d.update(fields)
    t["events"][0]["data"] = struct.pack(fmt, *[d[n] for n in names]).hex()


def find(recs, pred):
    for i, t in enumerate(recs[:-1]):
        if pred(t):
            return i
    return None


class VerifierMutations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not TRACES:
            raise unittest.SkipTest("NOT RUN: no traces (run thru/tests/test_properties.py first)")
        cls.base = {p: load(p) for p in TRACES}

    def clean(self):
        for p, recs in self.base.items():
            v = V.Verifier(copy.deepcopy(recs), os.path.basename(p)).run()
            self.assertEqual(v.violations, [], p)

    def test_clean_traces_pass(self):
        self.clean()

    def mutate(self, label, fn):
        """apply fn to every trace where it finds a target; each mutant must be flagged."""
        hits = 0
        for p, recs in self.base.items():
            m = copy.deepcopy(recs)
            if fn(m) is False:
                continue
            hits += 1
            v = V.Verifier(m, os.path.basename(p)).run()
            self.assertNotEqual(v.violations, [], f"{label}: mutant of {os.path.basename(p)} NOT detected")
        self.assertGreater(hits, 0, f"{label}: no trace had a target for this mutation")

    # --- each mutation models a specific way a broken program (or a forged record) could look
    def test_inflated_payment_amount(self):
        def f(m):
            i = find(m, lambda t: ev_name(t) == "PAID")
            if i is None: return False
            patch_event(m[i], amount=V.decode_event(m[i]["events"][0]["data"])["amount"] + 1)
        self.mutate("inflated amount", f)

    def test_replayed_nonce(self):
        def f(m):
            idx = [i for i, t in enumerate(m[:-1]) if ev_name(t) in ("PAID", "REQUESTED")
                   and bytes.fromhex(t["instr"])[0] == V.OP["REQUEST"]]
            if len(idx) < 2: return False
            first = V.decode_event(m[idx[0]]["events"][0]["data"])
            later = next((i for i in idx[1:] if V.decode_event(m[i]["events"][0]["data"])["agent"] == first["agent"]), None)
            if later is None: return False
            patch_event(m[later], nonce=first["nonce"])
        self.mutate("replayed nonce", f)

    def test_double_execution_of_approval(self):
        def f(m):
            i = find(m, lambda t: ev_name(t) == "PAID" and bytes.fromhex(t["instr"])[0] == V.OP["APPROVE"])
            if i is None: return False
            m.insert(i + 1, copy.deepcopy(m[i]))
        self.mutate("double execution", f)

    def test_payment_while_paused(self):
        def f(m):
            p = find(m, lambda t: ev_name(t) == "PAUSED" and V.decode_event(t["events"][0]["data"])["flag"] == 1)
            if p is None: return False
            src = find(m, lambda t: ev_name(t) == "PAID" and bytes.fromhex(t["instr"])[0] == V.OP["REQUEST"])
            if src is None: return False
            x = copy.deepcopy(m[src]); x["time_ns"] = m[p]["time_ns"]
            m.insert(p + 1, x)
        self.mutate("payment while paused", f)

    def test_payment_by_revoked_agent(self):
        def f(m):
            r = find(m, lambda t: ev_name(t) == "AGENT_REVOKED")
            if r is None: return False
            ag = V.decode_event(m[r]["events"][0]["data"])["agent"]
            src = find(m, lambda t: ev_name(t) == "PAID" and V.decode_event(t["events"][0]["data"])["agent"] == ag)
            if src is None: return False
            x = copy.deepcopy(m[src]); x["time_ns"] = m[r]["time_ns"]
            m.insert(r + 1, x)
        self.mutate("revoked agent pays", f)

    def test_failed_tx_with_events(self):
        def f(m):
            i = find(m, lambda t: ev_name(t) == "PAID")
            if i is None: return False
            m[i]["rc"] = 0x1010
        self.mutate("failed tx keeps effects", f)

    def test_dropped_rejection(self):
        def f(m):
            i = find(m, lambda t: ev_name(t) == "REJECTED")
            if i is None: return False
            del m[i]
        self.mutate("dropped rejection", f)

    def test_approval_signed_by_agent(self):
        def f(m):
            i = find(m, lambda t: ev_name(t) == "PAID" and bytes.fromhex(t["instr"])[0] == V.OP["APPROVE"])
            if i is None: return False
            m[i]["fee_payer"] = V.decode_event(m[i]["events"][0]["data"])["agent"].hex()
        self.mutate("agent self-approves", f)

    def test_unlisted_recipient(self):
        def f(m):
            i = find(m, lambda t: ev_name(t) == "PAID")
            if i is None: return False
            patch_event(m[i], recipient=b"\x77" * 32)
        self.mutate("unlisted recipient", f)

    def test_tokens_appear_from_nowhere(self):
        def f(m):
            s = m[-1]["snapshot"]; k = next(iter(s["token_balances"]))
            s["token_balances"][k] += 1
        self.mutate("conservation", f)

    def test_vault_balance_drained(self):
        def f(m):
            m[-1]["snapshot"]["vault_token_balance"] -= 1
        self.mutate("vault drained", f)

    def test_unpause_after_kill(self):
        def f(m):
            p = find(m, lambda t: ev_name(t) == "PAUSED")
            if p is None: return False
            k = copy.deepcopy(m[p]); k["instr"] = "0a" + k["instr"][2:]; patch_event(k, kind=12, flag=1)
            u = copy.deepcopy(m[p]); patch_event(u, flag=0)
            m.insert(p + 1, k); m.insert(p + 2, u)
        self.mutate("unpause after kill", f)

    def test_limit_lowered_below_spent(self):
        def f(m):
            # find an AGENT_SET after which the agent has spent something, and replay it with budget = 1
            spent = {}
            for i, t in enumerate(m[:-1]):
                n = ev_name(t)
                if n == "PAID":
                    e = V.decode_event(t["events"][0]["data"]); spent[e["agent"]] = spent.get(e["agent"], 0) + e["amount"]
                if n == "AGENT_SET":
                    e = V.decode_event(t["events"][0]["data"])
                    if spent.get(e["agent"], 0) > 1:
                        x = copy.deepcopy(t); patch_event(x, per_tx=1, daily=1, budget=1, threshold=0)
                        m.insert(i + 1, x); return
            return False
        self.mutate("CE-1 lowering", f)

    def test_snapshot_spent_tampered(self):
        def f(m):
            ag = m[-1]["snapshot"]["agents"]
            if not ag: return False
            next(iter(ag.values()))["spent"] -= 1
        self.mutate("snapshot spent", f)


if __name__ == "__main__":
    unittest.main()
