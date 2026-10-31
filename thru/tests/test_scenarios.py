"""D. Named scenarios from the Phase 5 gate review, against the LOCAL SIMULATION (real program code).
Each scenario that does not inject state writes a trace to thru/build/traces/scenario-*.jsonl, so the
independent verifier (thru/verifier/verify_thru.py) checks it as well."""
import itertools
import os
import struct
import unittest

import fsclient as F
from fsclient import C, NS_PER_DAY, err_name, key

TRACE_DIR = os.path.join(F.ROOT, "build", "traces")
U64 = 2**64 - 1


class Scenario(unittest.TestCase):
    def setUp(self):
        self.w = F.setup_world(funded=1_000, per_tx=100, daily=300, budget=600, threshold=20, n_recipients=2)
        self.s, self.fs, self.o, self.a, self.v = self.w["s"], self.w["fs"], self.w["owner"], self.w["agent"], self.w["vault"]
        self.vt, self.r, self.mint = self.w["vault_token"], self.w["recipients"], self.w["mint"]
        self.agents = [self.a]
        self.extra_tokens = []

    def code(self, res):
        return err_name(res[0])

    def ok(self, res):
        self.assertEqual(self.code(res), "OK")
        return res[1]

    def fails(self, res, name):
        self.assertEqual(self.code(res), "FS_ERR_" + name)
        self.assertEqual(res[1], [])

    def bal(self, t):
        return self.s.token(t)["amount"]

    def add_agent(self, label, per_tx=100, daily=300, budget=600, threshold=20):
        ag = key(label)
        self.ok(self.fs.set_agent(self.o, self.v, ag, per_tx, daily, budget, threshold, self.s.now + 30 * NS_PER_DAY))
        for r in self.r:
            self.ok(self.fs.set_recipient(self.o, self.v, ag, r, True))
        self.agents.append(ag)
        return ag

    def save(self, name):
        """Trace + raw on-chain snapshot for the independent verifier."""
        os.makedirs(TRACE_DIR, exist_ok=True)
        h = lambda b: b.hex()
        agents, reqs = {}, {}
        for ag in self.agents:
            d = self.fs.agent(self.v, ag)
            agents[h(ag)] = {k: (h(v) if isinstance(v, bytes) else [h(x) for x in v] if isinstance(v, list) else v)
                             for k, v in d.items() if k != "recipients_raw"}
            reqs[h(ag)] = {str(n): h(self.s.account(self.fs.request_addr(self.v, ag, n))[1])
                           for n in range(d["next_nonce"]) if self.s.account(self.fs.request_addr(self.v, ag, n))}
        toks = [self.vt] + self.r + self.extra_tokens
        snap = {"vault": h(self.v), "vault_token": h(self.vt), "funded": self.funded(), "owner": h(self.o),
                "vault_state": {k: (h(v) if isinstance(v, bytes) else v) for k, v in self.fs.vault(self.v).items()},
                "vault_token_balance": self.bal(self.vt), "agents": agents, "requests": reqs,
                "token_balances": {h(t): self.bal(t) for t in toks}}
        self.s.save_trace(os.path.join(TRACE_DIR, f"scenario-{name}.jsonl"), snapshot=snap)

    def funded(self):
        return getattr(self, "_funded", 1_000)


class ConcurrentSpending(Scenario):
    def test_pending_requests_reserve_budget_in_every_approval_order(self):
        """Three agents queue approvals that together exceed the vault's tokens; every approval order is tried.
        No agent ever exceeds its budget, tokens are conserved, and a failed approval changes nothing."""
        b, c = self.add_agent("agent-b"), self.add_agent("agent-c")
        orders = list(itertools.permutations([self.a, b, c]))
        self.assertEqual(len(orders), 6)
        for k, order in enumerate(orders):
            with self.subTest(order=k):
                self.setUp(); b, c = self.add_agent("agent-b"), self.add_agent("agent-c")
                # agent keys are derived from fixed labels, so the permutation's keys are this world's agents
                self.s.put_token_account(self.vt, self.mint, self.v, 250)          # fewer tokens than requested
                self._funded = 250
                for ag in (self.a, b, c):
                    self.ok(self.fs.request_payment(ag, self.v, self.r[0], 100))   # 3 x 100 pending (> threshold)
                    self.fails(self.fs.request_payment(ag, self.v, self.r[0], 600), "PER_TX")
                results = []
                for ag in order:
                    before = (self.fs.agent(self.v, ag), self.bal(self.vt))
                    rc, _ = self.fs.approve(self.o, self.v, ag, 0)
                    results.append(err_name(rc))
                    if rc:
                        self.assertEqual((self.fs.agent(self.v, ag), self.bal(self.vt)), before)
                self.assertEqual(results, ["OK", "OK", "FS_ERR_TRANSFER_FAILED"])
                self.assertEqual(self.bal(self.vt) + self.bal(self.r[0]), 250)
                for ag in (self.a, b, c):
                    d = self.fs.agent(self.v, ag)
                    self.assertLessEqual(d["spent"] + d["reserved"], d["budget"])
                if k == 0:
                    self.save("concurrent")

    def test_budget_is_reserved_at_request_time(self):
        for _ in range(3):
            self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 100))       # day 1: 300 pending (= daily)
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "DAILY")
        self.s.set_time((self.s.now // NS_PER_DAY + 1) * NS_PER_DAY + 10**9)      # next UTC day
        for _ in range(3):
            self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 100))       # day 2: 600 reserved = budget
        self.s.set_time((self.s.now // NS_PER_DAY + 1) * NS_PER_DAY + 10**9)
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "BUDGET")  # nothing paid, all reserved
        self.assertEqual(self.fs.agent(self.v, self.a)["reserved"], 600)
        self.save("reserved")


class PeriodRollover(Scenario):
    def test_midnight_boundary_and_day_change_rules(self):
        mid = (self.s.now // NS_PER_DAY + 1) * NS_PER_DAY
        self.s.set_time(mid - 1)                                                   # 23:59:59.999999999
        for _ in range(15):
            self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 20))
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 20), "DAILY")
        self.s.set_time(mid)                                                       # 00:00:00 next day
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 20))            # BF2-2: a new window
        self.assertEqual(self.fs.agent(self.v, self.a)["daily_used"], 20)

    def test_pending_approved_next_day_is_charged_to_the_new_day(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 90))            # day 1: daily_used 90
        nxt = (self.s.now // NS_PER_DAY + 1) * NS_PER_DAY + 10**9
        self.assertLess(nxt, self.fs.request(self.v, self.a, 0)["expires_ns"])    # still inside the approval window
        self.s.set_time(nxt)                                                       # day 2
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 20))            # day 2: 20
        self.ok(self.fs.approve(self.o, self.v, self.a, 0))                        # charged to day 2: 110
        d = self.fs.agent(self.v, self.a)
        self.assertEqual((d["daily_used"], d["spent"]), (110, 110))
        self.save("rollover")

    def test_rejecting_yesterdays_request_does_not_refund_today(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 90))
        self.s.advance(NS_PER_DAY // 10**9)
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 20))
        self.ok(self.fs.reject(self.o, self.v, self.a, 0))
        d = self.fs.agent(self.v, self.a)
        self.assertEqual((d["daily_used"], d["reserved"], d["spent"]), (20, 0, 20))


class CounterOverflow(Scenario):
    """State is injected to reach counter limits that cannot be reached in a test's lifetime."""
    def inject_agent(self, **fields):
        addr = self.fs.agent_addr(self.v, self.a)
        owner, data = self.s.account(addr)
        f = list(struct.unpack(F.AGENT_FMT, data))
        names = ["magic", "version", "active", "recipient_cnt", "r0", "vault", "agent", "epoch", "per_tx", "daily", "budget",
                 "threshold", "valid_until_ns", "day", "daily_used", "spent", "reserved", "next_nonce", "recipients"]
        for k, v in fields.items():
            f[names.index(k)] = v
        self.s.put_account(addr, owner, struct.pack(F.AGENT_FMT, *f))

    def test_nonce_at_u64_max_cannot_wrap(self):
        self.inject_agent(next_nonce=U64)
        before = self.fs.agent(self.v, self.a)
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1, nonce=U64), "OVERFLOW")
        self.assertEqual(self.fs.agent(self.v, self.a), before)

    def test_huge_limits_and_amounts_never_wrap(self):
        self.inject_agent(per_tx=U64, daily=U64, budget=U64, threshold=U64, spent=U64 - 5)
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 10), "OVERFLOW")   # spent + amount > 2^64-1
        self.inject_agent(budget=U64 - 10, spent=U64 - 15)
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 10), "BUDGET")     # no overflow, over budget
        self.inject_agent(daily_used=U64 - 5, day=self.s.now // NS_PER_DAY)
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 10), "OVERFLOW")

    def test_epoch_at_u64_max_cannot_wrap_on_revoke(self):
        self.inject_agent(epoch=U64)
        self.fails(self.fs.revoke(self.o, self.v, self.a), "OVERFLOW")
        self.assertTrue(self.fs.agent(self.v, self.a)["active"])


class DuplicatesAndRepeats(Scenario):
    def test_duplicate_request_and_repeated_approval(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 50, nonce=0))
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 50, nonce=0), "BAD_NONCE")
        self.ok(self.fs.approve(self.o, self.v, self.a, 0))
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "NO_PENDING")
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 50))
        self.ok(self.fs.reject(self.o, self.v, self.a, 1))
        self.fails(self.fs.approve(self.o, self.v, self.a, 1), "NO_PENDING")
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 50))
        self.s.advance(2 * NS_PER_DAY // 10**9)
        self.ok(self.fs.expire(key("anyone"), self.v, self.a, 2))
        self.fails(self.fs.approve(self.o, self.v, self.a, 2), "NO_PENDING")
        self.assertEqual(self.bal(self.r[0]), 50)
        self.save("duplicates")


class FailedTransfers(Scenario):
    def test_failed_transfer_consumes_nothing(self):
        self.ok(self.fs.withdraw(self.o, self.v, self.r[1], 990))                  # vault keeps 10 tokens
        before = self.fs.agent(self.v, self.a)
        rc, ev = self.fs.request_payment(self.a, self.v, self.r[0], 15)           # instant, but only 10 tokens
        self.assertEqual(err_name(rc), "FS_ERR_TRANSFER_FAILED"); self.assertEqual(ev, [])
        self.assertEqual(self.fs.agent(self.v, self.a), before)                    # nonce, daily, spent unchanged
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 50))            # pending (reserves 50)
        rc, _ = self.fs.approve(self.o, self.v, self.a, 0)
        self.assertEqual(err_name(rc), "FS_ERR_TRANSFER_FAILED")
        self.assertEqual(self.fs.request(self.v, self.a, 0)["status"], C["FS_REQ_PENDING"])
        self.assertEqual(self.fs.agent(self.v, self.a)["spent"], 0)


class RevocationDuringPending(Scenario):
    def test_revoke_regrant_stale_request_never_executes(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 80))
        self.ok(self.fs.revoke(self.o, self.v, self.a))
        self.assertEqual(self.fs.agent(self.v, self.a)["reserved"], 0)
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 100, 300, 600, 20, self.s.now + NS_PER_DAY))
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "STALE_REQUEST")
        self.ok(self.fs.expire(key("anyone"), self.v, self.a, 0))                  # INVALIDATED immediately
        self.assertEqual(self.fs.request(self.v, self.a, 0)["status"], C["FS_REQ_INVALIDATED"])
        d = self.fs.agent(self.v, self.a)
        self.assertEqual((d["reserved"], d["spent"]), (0, 0))
        self.assertEqual(self.bal(self.r[0]), 0)
        self.save("revoke-pending")


class AlternativeTransfers(Scenario):
    def test_no_signer_can_move_vault_tokens_directly(self):
        for who in (key("attacker"), self.a, self.o):
            rc, ev = F.direct_transfer(self.s, who, self.vt, self.r[0], 1)    # token transfer vault_token -> r0
            self.assertEqual(err_name(rc), "0x2006")                            # refused by the token model's AUTH check
            self.assertEqual(ev, [])
        self.assertEqual(self.bal(self.vt), 1_000)
        self.save("alt-transfers")


class MultipleAgents(Scenario):
    def test_agents_share_a_vault_but_not_their_limits(self):
        b = self.add_agent("agent-b", per_tx=50, daily=60, budget=60, threshold=50)
        self.ok(self.fs.request_payment(b, self.v, self.r[0], 50))
        self.fails(self.fs.request_payment(b, self.v, self.r[0], 20), "DAILY")    # b's own limit
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 20))            # a unaffected
        self.ok(self.fs.revoke(self.o, self.v, b))
        self.fails(self.fs.request_payment(b, self.v, self.r[0], 1), "UNKNOWN_AGENT")
        self.ok(self.fs.request_payment(self.a, self.v, self.r[1], 20))            # a still works
        self.assertEqual(self.fs.vault(self.v)["total_paid"], 90)
        self.assertEqual(self.bal(self.vt), 910)
        self.save("multi-agent")


if __name__ == "__main__":
    unittest.main()
