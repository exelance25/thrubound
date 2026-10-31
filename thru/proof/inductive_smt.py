#!/usr/bin/env python3
"""SMT-checked inductive proofs for an ABSTRACT model of the ThruBound state machine.

What is proved: for every transition T of the abstract model below and every state s and input i
(all values unbounded integers restricted to [0, 2^64-1], exactly the C u64 domain):
        Inv(s) ∧ pre_T(s, i) ∧ s' = post_T(s, i)  ⇒  Inv(s')
plus property-specific obligations. z3 must answer UNSAT for the negation of each obligation.

What is NOT proved: that thru/program/flowstate_core.c implements this model. That link is tested,
not proved, by thru/tests/test_model_conformance.py (random differential testing of the C core
against these same transition formulas). Assumptions H1-H6 are listed in docs/FORMAL_INVARIANTS.md.

Sanity: every transition is checked to be enabled in some Inv-state (non-vacuity), and model
mutations (a check removed) must yield counterexamples, so the proofs are not trivially true.

Usage: python3 inductive_smt.py            -> table of obligations, exit 1 on any failure
"""
import sys
import z3

MAX = 2**64 - 1
DAY = 86_400 * 10**9
NONE, PENDING, EXECUTED, REJECTED, EXPIRED, INVALIDATED = 0, 1, 2, 3, 4, 5
U64 = ["L", "D", "P", "T", "V", "t", "r", "R", "d", "day", "n", "e", "now", "paid", "ttl",
       "qs", "qx", "qn", "qe", "qday", "qexp", "qrec", "qmint", "qvault", "qagent", "vault", "agent", "mint"]
BOOL = ["act", "paused", "killed"]


def state(sfx):
    s = {k: z3.Int(k + sfx) for k in U64}
    s.update({k: z3.Bool(k + sfx) for k in BOOL})
    return s


def rng(s):
    return z3.And([z3.And(s[k] >= 0, s[k] <= MAX) for k in U64])


def today(s):
    return s["now"] / DAY


def Inv(s):
    return z3.And(
        rng(s),
        # configuration (fs_agent_set rules)
        s["P"] > 0, s["P"] <= s["D"], s["D"] <= s["L"], s["T"] <= s["P"], s["ttl"] > 0,
        # J: lifetime, with the ghost R = sum of open current-epoch requests
        s["t"] + s["r"] <= s["L"], s["r"] == s["R"],
        # the tracked request q, when open and current, is part of R; q never comes from the future
        z3.Implies(z3.And(s["qs"] == PENDING, s["qe"] == s["e"]), s["qx"] <= s["R"]),
        z3.Implies(s["qs"] != NONE, z3.And(s["qe"] <= s["e"], s["qn"] < s["n"], s["qday"] <= today(s))),
        # K: period
        s["day"] <= today(s), z3.Implies(s["day"] == today(s), s["d"] <= s["D"]),
        # kill implies pause
        z3.Implies(s["killed"], s["paused"]),
    )


def same(s, s2, keep):
    return z3.And([s2[k] == s[k] for k in keep])


def frame(s, s2, changed):
    return same(s, s2, [k for k in U64 + BOOL if k not in changed])


def live_agent(s):
    return z3.And(z3.Not(s["killed"]), z3.Not(s["paused"]), s["act"], s["now"] < s["V"])


# ------------------------------------------------------------------ transitions (pre, post)
def request(s, s2, i, tracked, instant):
    """fs_request: x, nonce, allowed recipient. tracked: the new pending request is q (q was empty)."""
    x, nonce, allowed = i["x"], i["nonce"], i["allowed"]
    t0 = today(s)
    d0 = z3.If(s["day"] == t0, s["d"], 0)
    pre = z3.And(live_agent(s), nonce == s["n"], x > 0, allowed, x <= s["P"], x <= MAX,
                 d0 + x <= MAX, d0 + x <= s["D"],
                 s["t"] + s["r"] <= MAX, s["t"] + s["r"] + x <= MAX, s["t"] + s["r"] + x <= s["L"],
                 s["n"] + 1 <= MAX)
    common = z3.And(s2["day"] == t0, s2["d"] == d0 + x, s2["n"] == s["n"] + 1)
    if instant:
        pre = z3.And(pre, x <= s["T"], s["paid"] + x <= MAX)
        post = z3.And(common, s2["t"] == s["t"] + x, s2["paid"] == s["paid"] + x,
                      frame(s, s2, ["day", "d", "n", "t", "paid"]))
    else:
        pre = z3.And(pre, x > s["T"], s["now"] + s["ttl"] <= MAX)
        post = z3.And(common, s2["r"] == s["r"] + x, s2["R"] == s["R"] + x)
        if tracked:
            pre = z3.And(pre, s["qs"] == NONE, i["rec"] >= 0, i["rec"] <= MAX)
            post = z3.And(post, s2["qs"] == PENDING, s2["qx"] == x, s2["qn"] == s["n"], s2["qe"] == s["e"],
                          s2["qday"] == t0, s2["qexp"] == s["now"] + s["ttl"], s2["qrec"] == i["rec"],
                          s2["qmint"] == s["mint"], s2["qvault"] == s["vault"], s2["qagent"] == s["agent"],
                          frame(s, s2, ["day", "d", "n", "r", "R", "qs", "qx", "qn", "qe", "qday", "qexp", "qrec",
                                        "qmint", "qvault", "qagent"]))
        else:
            post = z3.And(post, frame(s, s2, ["day", "d", "n", "r", "R"]))
    return pre, post


def binding(s, a):
    return z3.And(a["op"] == 6, a["vault"] == s["qvault"], a["agent"] == s["qagent"], a["rec"] == s["qrec"],
                  a["mint"] == s["qmint"], a["x"] == s["qx"], a["nonce"] == s["qn"], a["exp"] == s["qexp"])


def approve_q(s, s2, a, allowed):
    """fs_approve of the tracked request q with approval a."""
    t0 = today(s)
    x = s["qx"]
    same_day = s["qday"] == t0
    d0 = z3.If(s["day"] == t0, s["d"], 0)
    pre = z3.And(s["qs"] == PENDING, binding(s, a), z3.Not(s["killed"]), z3.Not(s["paused"]), s["qmint"] == s["mint"],
                 s["now"] < s["qexp"], s["act"], s["now"] < s["V"], allowed, s["qe"] == s["e"], x <= s["P"],
                 s["t"] + s["r"] <= MAX, s["t"] + s["r"] <= s["L"],
                 z3.If(same_day, d0 <= s["D"], z3.And(d0 + x <= MAX, d0 + x <= s["D"])), s["paid"] + x <= MAX)
    post = z3.And(s2["day"] == t0, s2["d"] == z3.If(same_day, d0, d0 + x), s2["r"] == s["r"] - x, s2["R"] == s["R"] - x,
                  s2["t"] == s["t"] + x, s2["paid"] == s["paid"] + x, s2["qs"] == EXECUTED,
                  frame(s, s2, ["day", "d", "r", "R", "t", "paid", "qs"]))
    return pre, post


def approve_other(s, s2, i):
    """fs_approve of some other open current-epoch request of amount y (part of R), created on day yday."""
    y, yday = i["y"], i["yday"]
    t0 = today(s)
    d0 = z3.If(s["day"] == t0, s["d"], 0)
    same_day = yday == t0
    pre = z3.And(y > 0, y <= s["R"] - z3.If(z3.And(s["qs"] == PENDING, s["qe"] == s["e"]), s["qx"], 0),
                 yday <= t0, z3.Not(s["killed"]), z3.Not(s["paused"]), s["act"], s["now"] < s["V"], y <= s["P"],
                 s["t"] + s["r"] <= s["L"], z3.If(same_day, d0 <= s["D"], z3.And(d0 + y <= MAX, d0 + y <= s["D"])),
                 s["paid"] + y <= MAX)
    post = z3.And(s2["day"] == t0, s2["d"] == z3.If(same_day, d0, d0 + y), s2["r"] == s["r"] - y, s2["R"] == s["R"] - y,
                  s2["t"] == s["t"] + y, s2["paid"] == s["paid"] + y, frame(s, s2, ["day", "d", "r", "R", "t", "paid"]))
    return pre, post


def release_q(s, s2, i):
    """fs_reject / fs_expire of q (current or stale epoch)."""
    current = s["qe"] == s["e"]
    expired_ok = z3.Or(z3.Not(current), s["now"] >= s["qexp"])
    pre = z3.And(s["qs"] == PENDING, z3.Or(i["reject"], expired_ok))
    dec = z3.And(s["day"] == s["qday"], s["d"] >= s["qx"])
    post = z3.And(s2["r"] == z3.If(current, s["r"] - s["qx"], s["r"]), s2["R"] == z3.If(current, s["R"] - s["qx"], s["R"]),
                  s2["d"] == z3.If(dec, s["d"] - s["qx"], s["d"]),
                  s2["qs"] == z3.If(i["reject"], REJECTED, z3.If(current, EXPIRED, INVALIDATED)),
                  frame(s, s2, ["r", "R", "d", "qs"]))
    return pre, post


def release_other(s, s2, i):
    y, yday = i["y"], i["yday"]
    pre = z3.And(y > 0, y <= s["R"] - z3.If(z3.And(s["qs"] == PENDING, s["qe"] == s["e"]), s["qx"], 0), yday <= today(s))
    dec = z3.And(s["day"] == yday, s["d"] >= y)
    post = z3.And(s2["r"] == s["r"] - y, s2["R"] == s["R"] - y, s2["d"] == z3.If(dec, s["d"] - y, s["d"]),
                  frame(s, s2, ["r", "R", "d"]))
    return pre, post


def revoke(s, s2, i):
    pre = z3.And(s["act"], s["e"] + 1 <= MAX)
    post = z3.And(z3.Not(s2["act"]), s2["e"] == s["e"] + 1, s2["r"] == 0, s2["R"] == 0, frame(s, s2, ["act", "e", "r", "R"]))
    return pre, post


def set_agent(s, s2, i, ce1=True):
    c = i
    pre = z3.And(z3.Not(s["killed"]), c["P"] > 0, c["P"] <= c["D"], c["D"] <= c["L"], c["T"] <= c["P"], c["V"] > s["now"],
                 c["L"] <= MAX, c["V"] <= MAX)
    if ce1:
        pre = z3.And(pre, s["t"] + s["r"] <= MAX, c["L"] >= s["t"] + s["r"], z3.Implies(s["day"] == today(s), c["D"] >= s["d"]))
    post = z3.And(s2["P"] == c["P"], s2["D"] == c["D"], s2["L"] == c["L"], s2["T"] == c["T"], s2["V"] == c["V"], s2["act"],
                  frame(s, s2, ["P", "D", "L", "T", "V", "act"]))
    return pre, post


def set_paused(s, s2, i):
    pre = z3.Not(s["killed"])
    post = z3.And(s2["paused"] == i["p"], frame(s, s2, ["paused"]))
    return pre, post


def kill(s, s2, i):
    pre = z3.Not(s["killed"])
    post = z3.And(s2["killed"], s2["paused"], frame(s, s2, ["killed", "paused"]))
    return pre, post


def tick(s, s2, i):
    pre = z3.And(i["now"] >= s["now"], i["now"] <= MAX)            # H3: block time never decreases
    post = z3.And(s2["now"] == i["now"], frame(s, s2, ["now"]))
    return pre, post


def inputs():
    i = {k: z3.Int("i_" + k) for k in ["x", "nonce", "rec", "y", "yday", "now", "P", "D", "L", "T", "V"]}
    i.update({k: z3.Bool("i_" + k) for k in ["allowed", "reject", "p"]})
    a = {k: z3.Int("a_" + k) for k in ["op", "vault", "agent", "rec", "mint", "x", "nonce", "exp"]}
    return i, a


def transitions(s, s2, i, a, ce1=True, epoch_check=True):
    T = {
        "request instant": request(s, s2, i, False, True),
        "request pending (new q)": request(s, s2, i, True, False),
        "request pending (other)": request(s, s2, i, False, False),
        "approve q": approve_q(s, s2, a, i["allowed"]),
        "approve other": approve_other(s, s2, i),
        "reject/expire q": release_q(s, s2, i),
        "reject/expire other": release_other(s, s2, i),
        "revoke": revoke(s, s2, i),
        "set_agent (existing)": set_agent(s, s2, i, ce1),
        "pause/unpause": set_paused(s, s2, i),
        "kill": kill(s, s2, i),
        "time passes": tick(s, s2, i),
    }
    # every instruction input is a u64 (or a byte) in the C code: restrict the model's inputs the same way
    in_rng = z3.And([z3.And(v >= 0, v <= MAX) for v in list(i.values()) + list(a.values()) if v.sort() == z3.IntSort()])
    T = {k: (z3.And(in_rng, pre), post) for k, (pre, post) in T.items()}
    if not epoch_check:
        pre, post = T["approve q"]
        T["approve q"] = (z3.substitute(pre, (s["qe"] == s["e"], z3.BoolVal(True))), post)
    return T


def proves(goal, timeout_ms=60_000):
    sv = z3.Solver()
    sv.set("timeout", timeout_ms)
    sv.add(z3.Not(goal))
    r = sv.check()
    return ("PROVED" if r == z3.unsat else "COUNTEREXAMPLE" if r == z3.sat else "UNKNOWN"), (sv.model() if r == z3.sat else None)


def sat(f):
    sv = z3.Solver(); sv.set("timeout", 60_000); sv.add(f)
    return sv.check() == z3.sat


def main():
    s, s2 = state(""), state("'")
    i, a = inputs()
    rows, ok = [], True

    def record(prop, tr, goal, expect="PROVED"):
        nonlocal ok
        res, _ = proves(goal)
        good = res == expect
        ok &= good
        rows.append((prop, tr, res, "ok" if good else "FAIL"))

    T = transitions(s, s2, i, a)
    for name, (pre, post) in T.items():
        if not sat(z3.And(Inv(s), pre, post, rng(s2))):
            rows.append(("non-vacuity", name, "NEVER ENABLED", "FAIL")); ok = False
        else:
            rows.append(("non-vacuity", name, "enabled in some Inv-state", "ok"))
        hyp = z3.And(Inv(s), pre, post)
        record("Inv preserved (J, K, ranges, kill⇒pause)", name, z3.Implies(hyp, Inv(s2)))
        record("1-2. spent ≤ budget, reserved ≤ budget", name, z3.Implies(hyp, z3.And(s2["t"] <= s2["L"], s2["r"] <= s2["L"])))
        record("3. nonce never decreases; accepted nonce = n, n' = n+1", name,
               z3.Implies(hyp, z3.And(s2["n"] >= s["n"], z3.Implies(s2["n"] != s["n"], z3.And(i["nonce"] == s["n"], s2["n"] == s["n"] + 1)))))
        record("7. a stale request stays stale", name, z3.Implies(z3.And(hyp, s["qs"] != NONE, s["qe"] < s["e"]), s2["qe"] < s2["e"]))
        record("kill is irreversible", name, z3.Implies(z3.And(hyp, s["killed"]), s2["killed"]))
    # enabling conditions
    for tr in ["request instant", "request pending (other)", "approve q", "approve other"]:
        pre, _ = T[tr]
        record("4. revoked agent cannot transact", tr, z3.Implies(z3.And(Inv(s), z3.Not(s["act"])), z3.Not(pre)))
        record("5. expired permission cannot be used", tr, z3.Implies(z3.And(Inv(s), s["now"] >= s["V"]), z3.Not(pre)))
    pre, _ = T["approve q"]
    record("6. approval valid only for the exact request", "approve q", z3.Implies(pre, binding(s, a)))
    record("7. pending request cannot execute after revocation", "approve q", z3.Implies(z3.And(Inv(s), s["qe"] < s["e"]), z3.Not(pre)))

    # 8 + 9: several agents sharing one vault; accounting moves with the tokens in one transition
    F, B, W, t1, t2, L1, L2, x, w = (z3.Int(n) for n in ["F", "B", "W", "t1", "t2", "L1", "L2", "x", "w"])
    B2, W2, t12, t22 = (z3.Int(n + "'") for n in ["B", "W", "t1", "t2"])
    inv2 = lambda B, W, t1, t2: z3.And(B >= 0, W >= 0, t1 >= 0, t2 >= 0, B + t1 + t2 + W == F, t1 <= L1, t2 <= L2)
    pay1 = z3.And(x > 0, B >= x, t1 + x <= L1, B2 == B - x, t12 == t1 + x, t22 == t2, W2 == W)   # transfer + accounting, atomic (H1)
    pay2 = z3.And(x > 0, B >= x, t2 + x <= L2, B2 == B - x, t22 == t2 + x, t12 == t1, W2 == W)
    wdr = z3.And(w > 0, B >= w, B2 == B - w, W2 == W + w, t12 == t1, t22 == t2)
    fail = z3.And(B2 == B, W2 == W, t12 == t1, t22 == t2)                                        # any failed tx (H1)
    for nm, tr in [("agent 1 pays", pay1), ("agent 2 pays", pay2), ("owner withdraws", wdr), ("failed transaction", fail)]:
        record("8. agents sharing a vault: Σpaid ≤ funded, each ≤ own budget", nm,
               z3.Implies(z3.And(inv2(B, W, t1, t2), tr), z3.And(inv2(B2, W2, t12, t22), t12 + t22 <= F)))
        record("9. recorded spending changes exactly with the vault balance", nm,
               z3.Implies(z3.And(inv2(B, W, t1, t2), tr), (t12 + t22) - (t1 + t2) == (B - B2) - (W2 - W)))

    # mutation sanity: the proofs must fail when a check is removed from the model
    Tm = transitions(s, s2, i, a, ce1=False)
    pre, post = Tm["set_agent (existing)"]
    record("sanity: without CE-1 the lifetime invariant breaks", "set_agent (existing)",
           z3.Implies(z3.And(Inv(s), pre, post), Inv(s2)), expect="COUNTEREXAMPLE")
    Tm = transitions(s, s2, i, a, epoch_check=False)
    pre, _ = Tm["approve q"]
    record("sanity: without the epoch check a stale request executes", "approve q",
           z3.Implies(z3.And(Inv(s), s["qe"] < s["e"]), z3.Not(pre)), expect="COUNTEREXAMPLE")

    w1 = max(len(r[0]) for r in rows)
    w2 = max(len(r[1]) for r in rows)
    for r in rows:
        print(f"{r[0]:<{w1}}  {r[1]:<{w2}}  {r[2]:<26} {r[3]}")
    n_ok = sum(r[3] == "ok" for r in rows)
    print(f"\n{'PASS' if ok else 'FAIL'}: {n_ok}/{len(rows)} obligations as expected (z3 {z3.get_version_string()})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
