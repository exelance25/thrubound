"""E. Model conformance: the C policy core (flowstate_core.c, called directly through ctypes) against the
abstract transition model that thru/proof/inductive_smt.py proves things about.

For random states that satisfy the model's invariant (biased towards boundaries such as 0, limits and
2^64-1), each C transition is executed and compared with the model: accept/refuse must agree, and on
success every modelled field must equal the model's post-state. This connects the SMT proofs to the
code by testing; it is not itself a proof."""
import ctypes
import os
import random
import struct
import sys
import unittest

import z3

import fsclient as F
from fsclient import C

sys.path.insert(0, os.path.join(F.ROOT, "proof"))
import inductive_smt as M  # noqa: E402

MAX = 2**64 - 1
TRIALS = int(os.environ.get("FS_CONFORMANCE_TRIALS", "3000"))
lib = ctypes.CDLL(F.LIB)
KEYS = {n: F.key("conf-" + n) for n in ["vault", "agent", "mint", "owner", "rec", "other"]}
k2i = lambda b: int.from_bytes(b[:8], "little")          # model identity of a 32-byte key


class World:
    """One random model state, realised as C structs."""
    def __init__(self, rng):
        R = rng
        pick = lambda lo, hi: R.choice([lo, hi, lo + 1 if lo < hi else lo, hi - 1 if hi > lo else hi, R.randint(lo, hi)])
        s = {}
        s["L"] = pick(1, R.choice([1000, 10**12, MAX]))
        s["D"] = pick(1, s["L"]); s["P"] = pick(1, s["D"]); s["T"] = pick(0, s["P"])
        s["t"] = pick(0, s["L"]); s["r"] = pick(0, s["L"] - s["t"]); s["R"] = s["r"]
        s["ttl"] = R.choice([300 * 10**9, M.DAY])
        s["now"] = R.choice([1_900_000_000 * 10**9 + R.randint(0, 3 * M.DAY), R.randint(0, 2**63)])
        today = s["now"] // M.DAY
        s["day"] = R.choice([today, max(0, today - R.randint(1, 3))])
        s["d"] = pick(0, s["D"]) if s["day"] == today else R.choice([0, R.randint(0, MAX)])
        s["n"] = R.choice([R.randint(1, 50), MAX - 1, MAX])
        s["e"] = R.choice([R.randint(0, 5), MAX])
        s["V"] = R.choice([s["now"] + 10**9, max(0, s["now"] - 1), s["now"]])
        s["paid"] = R.choice([R.randint(0, 10**12), MAX - R.randint(0, 3)])
        s["act"] = R.random() < 0.8; s["killed"] = R.random() < 0.05; s["paused"] = s["killed"] or R.random() < 0.1
        s["vault"], s["agent"], s["mint"] = k2i(KEYS["vault"]), k2i(KEYS["agent"]), k2i(KEYS["mint"])
        # the tracked request q
        s["qs"] = R.choice([M.NONE, M.PENDING, M.PENDING, M.EXECUTED, M.REJECTED])
        s["qe"] = s["e"] if R.random() < 0.7 else R.randint(0, s["e"])
        s["qn"] = R.randint(0, s["n"] - 1)
        cap = s["r"] if (s["qs"] == M.PENDING and s["qe"] == s["e"]) else MAX
        s["qx"] = R.randint(1, max(1, min(cap, MAX)))
        if s["qs"] == M.PENDING and s["qe"] == s["e"] and s["qx"] > s["r"]:
            s["qs"] = M.REJECTED                       # a current pending request is always part of r
        s["qday"] = R.choice([today, max(0, today - 1)])
        s["qexp"] = R.choice([s["now"] + 10**9, s["now"], max(0, s["now"] - 1)])
        self.rec_allowed = R.random() < 0.85
        s["qrec"] = k2i(KEYS["rec"]); s["qmint"] = s["mint"]; s["qvault"] = s["vault"]; s["qagent"] = s["agent"]
        if s["qs"] == M.NONE:
            for k in ["qx", "qn", "qe", "qday", "qexp"]:
                s[k] = 0 if k != "qn" else min(s[k], s["n"] - 1)
        if R.random() < 0.5:                       # "happy" half: live agent, so acceptance paths are exercised too
            s.update(act=True, paused=False, killed=False, V=s["now"] + 10**12, n=R.randint(1, 50), e=R.randint(0, 5),
                     paid=R.randint(0, 10**9), day=today, d=R.randint(0, s["D"] // 2))
            s["t"] = R.randint(0, s["L"] // 2); s["r"] = s["R"] = R.randint(0, (s["L"] - s["t"]) // 2)
            s["qe"] = s["e"] if R.random() < 0.8 else R.randint(0, s["e"])
            s["qn"] = R.randint(0, s["n"] - 1); s["qday"] = today; s["qexp"] = s["now"] + 10**9
            s["qx"] = R.randint(1, max(1, min(s["P"], s["r"] if s["r"] else 1)))
            if s["qe"] == s["e"] and s["qx"] > s["r"]:
                s["qs"] = M.REJECTED
            self.rec_allowed = R.random() < 0.95
        self.s = s

    # C structs ------------------------------------------------------------------------
    def vault(self):
        s = self.s
        flags = (1 if s["paused"] else 0) | (2 if s["killed"] else 0)
        return ctypes.create_string_buffer(struct.pack(F.VAULT_FMT, C["FS_VAULT_MAGIC"], 1, flags, 0, KEYS["owner"], KEYS["mint"],
                                                       KEYS["other"], 1, s["ttl"], s["paid"], 1, 0), 136)

    def agent(self):
        s = self.s
        recips = [KEYS["rec"]] if self.rec_allowed else []
        return ctypes.create_string_buffer(struct.pack(F.AGENT_FMT, C["FS_AGENT_MAGIC"], 1, 1 if s["act"] else 0, len(recips), 0,
                                                       KEYS["vault"], KEYS["agent"], s["e"], s["P"], s["D"], s["L"], s["T"], s["V"],
                                                       s["day"], s["d"], s["t"], s["r"], s["n"], b"".join(recips).ljust(256, b"\0")), 416)

    def request(self):
        s = self.s
        if s["qs"] == M.NONE:
            return ctypes.create_string_buffer(184)
        return ctypes.create_string_buffer(struct.pack(F.REQ_FMT, C["FS_REQ_MAGIC"], 1, s["qs"], 0, KEYS["vault"], KEYS["agent"],
                                                       KEYS["rec"], KEYS["mint"], s["qx"], s["qn"], s["qe"], s["qday"],
                                                       max(0, s["now"] - 1), s["qexp"]), 184)


def read_back(s, vb, ab, rb):
    v = F.decode_vault(vb.raw[:136]); a = F.decode_agent(ab.raw[:416])
    out = dict(s)
    out.update(t=a["spent"], r=a["reserved"], d=a["daily_used"], day=a["day"], n=a["next_nonce"], e=a["epoch"],
               act=bool(a["active"]), P=a["per_tx"], D=a["daily"], L=a["budget"], T=a["threshold"], V=a["valid_until_ns"],
               paid=v["total_paid"], paused=bool(v["flags"] & 1), killed=bool(v["flags"] & 2))
    if rb.raw[:4] != b"\0\0\0\0":
        q = F.decode_request(rb.raw[:184])
        out.update(qs=q["status"], qx=q["amount"], qn=q["nonce"], qe=q["epoch"], qday=q["day"], qexp=q["expires_ns"])
    return out


class Conformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s, cls.s2 = M.state(""), M.state("'")
        cls.i, cls.a = M.inputs()
        cls.T = M.transitions(cls.s, cls.s2, cls.i, cls.a)

    def model(self, name, s, inputs):
        """Evaluate the model concretely: (enabled, post-state)."""
        pre, post = self.T[name]
        subst = [(self.s[k], z3.BoolVal(v) if isinstance(v, bool) else z3.IntVal(v)) for k, v in s.items() if k in self.s]
        given = {str(var) for var, _ in inputs}
        subst += [(var, z3.BoolVal(v) if isinstance(v, bool) else z3.IntVal(v)) for var, v in inputs]
        for var in list(self.i.values()) + list(self.a.values()):      # inputs this transition does not use
            if str(var) not in given:
                subst.append((var, z3.BoolVal(False) if var.sort() == z3.BoolSort() else z3.IntVal(0)))
        enabled = z3.is_true(z3.simplify(z3.substitute(pre, subst)))
        if not enabled:
            return False, None
        sv = z3.Solver(); sv.add(z3.substitute(post, subst))
        self.assertEqual(sv.check(), z3.sat)
        m = sv.model()
        val = lambda e: (z3.is_true(m.eval(e, model_completion=True)) if e.sort() == z3.BoolSort() else m.eval(e, model_completion=True).as_long())
        return True, {k: val(self.s2[k]) for k in self.s2}

    def compare(self, name, w, rc, vb, ab, rb, inputs):
        enabled, post = self.model(name, w.s, inputs)
        self.assertEqual(rc == 0, enabled, f"{name}: C rc={F.err_name(rc)} model enabled={enabled} state={w.s}")
        if enabled:
            got = read_back(w.s, vb, ab, rb)
            for k in ["t", "r", "d", "day", "n", "e", "act", "P", "D", "L", "T", "V", "paid", "paused", "killed", "qs", "qx", "qe", "qday", "qexp"]:
                if name.startswith("request pending") or name == "reject/expire q" or name == "approve q" or not k.startswith("q"):
                    self.assertEqual(got[k], post[k], f"{name}: field {k} C={got[k]} model={post[k]} state={w.s}")
        return enabled

    def test_random_transitions_agree(self):
        rng = random.Random(20261031)
        enabled_count, accepted = {}, {}
        for trial in range(TRIALS):
            w = World(rng)
            s = w.s
            today = s["now"] // M.DAY
            kind = rng.choice(["request", "approve", "release", "revoke", "set_agent"])
            vb, ab, rb = w.vault(), w.agent(), w.request()
            if kind == "request":
                x = rng.choice([0, 1, s["T"], s["T"] + 1, s["P"], s["P"] + 1, rng.randint(0, MAX)])
                nonce = rng.choice([s["n"], s["n"], s["n"] - 1, min(MAX, s["n"] + 1)])
                if s["qs"] != M.NONE:
                    rb = ctypes.create_string_buffer(184)          # C always writes a fresh request account
                dec = ctypes.c_int(0)
                rc = lib.fs_request(vb, ab, ctypes.c_char_p(KEYS["vault"]), ctypes.c_char_p(KEYS["rec"]), ctypes.c_uint64(x),
                                    ctypes.c_uint64(nonce), ctypes.c_uint64(s["now"]), rb, ctypes.byref(dec))
                ins = [(self.i["x"], x), (self.i["nonce"], nonce), (self.i["allowed"], w.rec_allowed), (self.i["rec"], k2i(KEYS["rec"]))]
                s_model = dict(s, qs=M.NONE, qx=0, qn=0, qe=0, qday=0, qexp=0)
                w.s = s_model
                name = "request instant" if (rc == 0 and dec.value == 1) or (rc != 0 and x <= s["T"]) else "request pending (new q)"
                if rc == 0 and dec.value == 2:
                    name = "request pending (new q)"
                accepted[name] = accepted.get(name, 0) + (rc == 0)
                self.compare(name, w, rc, vb, ab, rb, ins)
            elif kind == "approve" and s["qs"] != M.NONE:
                field = rng.choice([None, None, None, "amount", "nonce", "expires", "recipient", "op"])
                ap = dict(vault=KEYS["vault"], agent=KEYS["agent"], recipient=KEYS["rec"], mint=KEYS["mint"], amount=s["qx"],
                          nonce=s["qn"], expires=s["qexp"], op=C["FS_OP_APPROVE"])
                if field == "recipient": ap["recipient"] = KEYS["other"]
                elif field == "op": ap["op"] = 7
                elif field: ap[field] = (ap[field] + 1) % 2**64
                apb = ctypes.create_string_buffer(struct.pack(F.APPROVAL_FMT, ap["vault"], ap["agent"], ap["recipient"], ap["mint"],
                                                              ap["amount"], ap["nonce"], ap["expires"], ap["op"]), 153)
                rc = lib.fs_approve(vb, ab, rb, apb, ctypes.c_uint64(s["now"]))
                ins = [(self.i["allowed"], w.rec_allowed), (self.a["op"], ap["op"]), (self.a["vault"], k2i(ap["vault"])),
                       (self.a["agent"], k2i(ap["agent"])), (self.a["rec"], k2i(ap["recipient"])), (self.a["mint"], k2i(ap["mint"])),
                       (self.a["x"], ap["amount"]), (self.a["nonce"], ap["nonce"]), (self.a["exp"], ap["expires"])]
                name = "approve q"
                accepted[name] = accepted.get(name, 0) + (rc == 0)
                self.compare(name, w, rc, vb, ab, rb, ins)
            elif kind == "release" and s["qs"] != M.NONE:
                reject = rng.random() < 0.5
                rc = lib.fs_reject(ab, rb) if reject else lib.fs_expire(ab, rb, ctypes.c_uint64(s["now"]))
                name = "reject/expire q"
                accepted[name] = accepted.get(name, 0) + (rc == 0)
                self.compare(name, w, rc, vb, ab, rb, [(self.i["reject"], reject)])
            elif kind == "revoke":
                rc = lib.fs_agent_revoke(ab)
                name = "revoke"
                accepted[name] = accepted.get(name, 0) + (rc == 0)
                self.compare(name, w, rc, vb, ab, rb, [])
            else:
                L = rng.choice([s["t"] + s["r"], max(1, s["t"] + s["r"] - 1), rng.randint(1, MAX)])
                D = rng.choice([s["d"], max(1, s["d"] - 1), rng.randint(1, max(1, L))])
                P = rng.choice([1, rng.randint(1, max(1, D))]); T = rng.randint(0, P)
                V = rng.choice([s["now"] + 1, s["now"]])
                cfg = ctypes.create_string_buffer(struct.pack("<5Q", P, D, L, T, V), 40)
                rc = lib.fs_agent_set(vb, ab, ctypes.c_char_p(KEYS["vault"]), ctypes.c_char_p(KEYS["agent"]), cfg, ctypes.c_uint64(s["now"]), 0)
                ins = [(self.i["P"], P), (self.i["D"], D), (self.i["L"], L), (self.i["T"], T), (self.i["V"], V)]
                name = "set_agent (existing)"
                accepted[name] = accepted.get(name, 0) + (rc == 0)
                self.compare(name, w, rc, vb, ab, rb, ins)
            enabled_count[name if kind not in ("approve", "release") or s["qs"] != M.NONE else "skip"] = \
                enabled_count.get(name, 0) + 1
        print("\n  conformance trials per transition:", {k: v for k, v in sorted(enabled_count.items()) if k != "skip"})
        print("  of which accepted by both C and model:", dict(sorted(accepted.items())))
        for n in ["request instant", "request pending (new q)", "approve q", "reject/expire q", "revoke", "set_agent (existing)"]:
            self.assertGreater(enabled_count.get(n, 0), 20, n)
            self.assertGreater(accepted.get(n, 0), 5, n + " (accepted)")


if __name__ == "__main__":
    unittest.main()
