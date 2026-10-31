"""A. Functional tests — LOCAL SIMULATION of the Flowstate Thru program (host build, not the Thru VM).
Run: python3 -m unittest discover -s thru/tests -v   (after thru/build_host.sh)"""
import unittest

import fsclient as F
from fsclient import C, NS_PER_DAY, err_name, key

E = lambda name: C["FS_ERR_" + name]


class Base(unittest.TestCase):
    def setUp(self):
        self.w = F.setup_world()
        self.s, self.fs = self.w["s"], self.w["fs"]
        self.o, self.a, self.x = self.w["owner"], self.w["agent"], self.w["attacker"]
        self.v, self.r = self.w["vault"], self.w["recipients"]

    def ok(self, res):
        self.assertEqual(err_name(res[0]), "OK")
        return res[1]

    def fails(self, res, name):
        self.assertEqual(err_name(res[0]), name if name.startswith("0x") else "FS_ERR_" + name)
        self.assertEqual(res[1], [], "a failed transaction must not emit events")

    def bal(self, acct):
        return self.s.token(acct)["amount"]

    def agent(self):
        return self.fs.agent(self.v, self.a)


class VaultCreation(Base):
    def test_vault_initialized_with_owner_mint_token_account(self):
        vd = self.fs.vault(self.v)
        self.assertEqual((vd["magic"], vd["owner"], vd["mint"], vd["token_account"], vd["agent_count"]),
                         (C["FS_VAULT_MAGIC"], self.o, self.w["mint"], self.w["vault_token"], 1))
        owner, _ = self.s.account(self.v)
        self.assertEqual(owner, self.s.program, "vault account is owned by the Flowstate program")

    def test_second_init_of_same_vault_rejected(self):
        self.fails(self.fs.init_vault(self.o, 1, self.w["mint"]), "ALREADY_INITIALIZED")

    def test_ttl_bounds(self):
        self.fails(self.fs.init_vault(self.o, 2, self.w["mint"], ttl_ns=60 * 10**9), "INVALID_CONFIG")
        self.fails(self.fs.init_vault(self.o, 3, self.w["mint"], ttl_ns=31 * NS_PER_DAY), "INVALID_CONFIG")
        self.ok(self.fs.init_vault(self.o, 4, self.w["mint"], ttl_ns=300 * 10**9))

    def test_bind_token_unfreezable_mint(self):
        """KSI-1 (Thru): with the mint passed, BIND_TOKEN accepts only a mint without a freeze authority
        and records it in the vault flags (FS_VAULT_MINT_UNFREEZABLE)."""
        def fresh(n, freeze):
            mint = key(f"m-{n}")
            self.s.put_mint_account(mint, self.o, freeze_authority=key("freezer") if freeze else None)
            self.ok(self.fs.init_vault(self.o, 100 + n, mint))
            v = self.fs.vault_addr(self.o, 100 + n)
            t = key(f"t-{n}")
            self.s.put_token_account(t, mint, v, 0)
            return mint, v, t
        mint, v, t = fresh(1, freeze=False)
        ev = self.ok(self.fs.bind_token(self.o, v, t, mint_acct=mint))
        self.assertTrue(self.fs.vault(v)["flags"] & C["FS_VAULT_MINT_UNFREEZABLE"])
        self.assertEqual(ev[0][1][-1], 1)                                # TOKEN_BOUND carries the flag
        mint, v, t = fresh(2, freeze=True)
        self.fails(self.fs.bind_token(self.o, v, t, mint_acct=mint), "MINT_FREEZABLE")
        other, _, _ = fresh(3, freeze=False)
        self.fails(self.fs.bind_token(self.o, v, t, mint_acct=other), "WRONG_TOKEN")        # not this vault's mint
        fake = key("fake-mint")
        self.s.put_account(fake, key("not-token-program"), bytes(115))
        self.fails(self.fs.bind_token(self.o, v, t, mint_acct=fake), "WRONG_TOKEN")         # not a token-program account
        self.ok(self.fs.bind_token(self.o, v, t))                                           # mint not given: allowed, no flag
        self.assertFalse(self.fs.vault(v)["flags"] & C["FS_VAULT_MINT_UNFREEZABLE"])

    def test_bind_token_checks(self):
        self.ok(self.fs.init_vault(self.o, 7, self.w["mint"]))
        v7 = self.fs.vault_addr(self.o, 7)
        bad_mint, not_vault_owned, frozen, good = key("t-bad-mint"), key("t-not-vault"), key("t-frozen"), key("t-good")
        self.s.put_token_account(bad_mint, key("other-mint"), v7, 0)
        self.s.put_token_account(not_vault_owned, self.w["mint"], self.o, 0)
        self.s.put_token_account(frozen, self.w["mint"], v7, 0, frozen=1)
        self.s.put_token_account(good, self.w["mint"], v7, 0)
        self.s.put_account(key("t-fake"), self.x, b"\x00" * 73)
        self.fails(self.fs.bind_token(self.o, v7, bad_mint), "WRONG_TOKEN")
        self.fails(self.fs.bind_token(self.o, v7, not_vault_owned), "WRONG_TOKEN")
        self.fails(self.fs.bind_token(self.o, v7, frozen), "WRONG_TOKEN")
        self.fails(self.fs.bind_token(self.o, v7, key("t-fake")), "WRONG_TOKEN")
        self.ok(self.fs.bind_token(self.o, v7, good))
        self.fails(self.fs.bind_token(self.o, v7, good), "ALREADY_INITIALIZED")


class AgentRegistration(Base):
    def test_agent_account_fields(self):
        a = self.agent()
        self.assertEqual((a["active"], a["vault"], a["agent"], a["epoch"], a["next_nonce"], a["recipient_cnt"]), (1, self.v, self.a, 0, 0, 2))

    def test_invalid_configs_rejected(self):
        t = self.s.now + NS_PER_DAY
        n = key("agent-2")
        for args in [(0, 10, 10, 0, t), (20, 10, 100, 0, t), (10, 200, 100, 0, t), (10, 20, 100, 11, t), (10, 20, 100, 5, self.s.now)]:
            self.fails(self.fs.set_agent(self.o, self.v, n, *args), "INVALID_CONFIG")
        self.fails(self.fs.set_agent(self.o, self.v, self.o, 10, 20, 100, 5, t), "INVALID_CONFIG")  # owner can never be an agent

    def test_update_preserves_counters(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 5_000_000))
        before = self.agent()
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 40_000_000, 100_000_000, 900_000_000, 5_000_000, self.s.now + NS_PER_DAY))
        after = self.agent()
        self.assertEqual((after["spent"], after["next_nonce"], after["epoch"], after["daily_used"]), (before["spent"], before["next_nonce"], before["epoch"], before["daily_used"]))
        self.assertEqual(after["per_tx"], 40_000_000)


class Payments(Base):
    def test_instant_payment_moves_tokens_once(self):
        v0, r0 = self.bal(self.w["vault_token"]), self.bal(self.r[0])
        ev = self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 7_000_000))
        self.assertEqual([e[1][0] for e in ev], [C["FS_EV_PAID"]])
        self.assertEqual((self.bal(self.w["vault_token"]), self.bal(self.r[0])), (v0 - 7_000_000, r0 + 7_000_000))
        a = self.agent()
        self.assertEqual((a["spent"], a["reserved"], a["daily_used"], a["next_nonce"]), (7_000_000, 0, 7_000_000, 1))
        self.assertEqual(self.fs.vault(self.v)["total_paid"], 7_000_000)

    def test_above_threshold_becomes_pending_and_reserves(self):
        v0 = self.bal(self.w["vault_token"])
        ev = self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000))
        self.assertEqual([e[1][0] for e in ev], [C["FS_EV_REQUESTED"]])
        self.assertEqual(self.bal(self.w["vault_token"]), v0, "nothing moves before approval")
        r = self.fs.request(self.v, self.a, 0)
        self.assertEqual((r["status"], r["amount"], r["recipient"], r["mint"]), (C["FS_REQ_PENDING"], 30_000_000, self.r[0], self.w["mint"]))
        self.assertEqual(self.agent()["reserved"], 30_000_000)

    def test_exact_threshold_is_instant(self):
        self.assertEqual([e[1][0] for e in self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 10_000_000))], [C["FS_EV_PAID"]])

    def test_zero_amount_rejected(self):
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 0), "ZERO_AMOUNT")


class Approval(Base):
    def setUp(self):
        super().setUp()
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000))

    def test_approve_executes_exactly_the_request(self):
        r0 = self.bal(self.r[0])
        ev = self.ok(self.fs.approve(self.o, self.v, self.a, 0))
        self.assertEqual([e[1][0] for e in ev], [C["FS_EV_PAID"]])
        self.assertEqual(self.bal(self.r[0]), r0 + 30_000_000)
        a = self.agent()
        self.assertEqual((a["spent"], a["reserved"]), (30_000_000, 0))
        self.assertEqual(self.fs.request(self.v, self.a, 0)["status"], C["FS_REQ_EXECUTED"])

    def test_owner_reject_releases(self):
        self.ok(self.fs.reject(self.o, self.v, self.a, 0))
        a = self.agent()
        self.assertEqual((a["reserved"], a["daily_used"], a["spent"]), (0, 0, 0))
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "NO_PENDING")

    def test_agent_may_reject_its_own_request(self):
        self.ok(self.fs.reject(self.a, self.v, self.a, 0))

    def test_expire_only_after_ttl(self):
        self.fails(self.fs.expire(self.x, self.v, self.a, 0), "REQUEST_NOT_EXPIRED")
        self.s.advance(86_400)
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "REQUEST_EXPIRED")
        ev = self.ok(self.fs.expire(self.x, self.v, self.a, 0))   # anyone may close it
        self.assertEqual([e[1][0] for e in ev], [C["FS_EV_EXPIRED"]])
        self.assertEqual(self.agent()["reserved"], 0)


class Limits(Base):
    def test_ce1_limits_cannot_drop_below_used(self):
        """CE-1 (owner decision 2026-10-30): spent + reserved <= budget and today's daily_used <= daily
        must hold in every state, so a reconfiguration below what is already used is refused."""
        vu = self.s.now + NS_PER_DAY
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 10_000_000))          # instant, spent = 10e6
        before = self.fs.agent(self.v, self.a)
        self.fails(self.fs.set_agent(self.o, self.v, self.a, 5_000_000, 5_000_000, 9_999_999, 1, vu), "INVALID_CONFIG")
        self.fails(self.fs.set_agent(self.o, self.v, self.a, 5_000_000, 9_999_999, 1_000_000_000, 1, vu), "INVALID_CONFIG")
        self.assertEqual(self.fs.agent(self.v, self.a), before)
        # exactly at the used amount is allowed, and then nothing more can be spent
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 10_000_000, 10_000_000, 10_000_000, 1, vu))
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "DAILY")
        # a new UTC day resets the daily counter, so a lower daily limit is accepted again
        self.s.set_time((self.s.now // NS_PER_DAY + 1) * NS_PER_DAY + 10**9)
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 1_000_000, 1_000_000, 10_000_000, 1, self.s.now + NS_PER_DAY))
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "BUDGET")

    def test_per_tx_boundary(self):
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 50_000_000, 200_000_000, 1_000_000_000, 50_000_000, self.s.now + NS_PER_DAY))
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 50_000_000))
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 50_000_001), "PER_TX")

    def test_daily_limit_utc_day_and_reset(self):
        day_start = (self.s.now // NS_PER_DAY + 1) * NS_PER_DAY
        self.s.set_time(day_start + 60 * 10**9)
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 50_000_000, 100_000_000, 1_000_000_000, 50_000_000, self.s.now + 5 * NS_PER_DAY))
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 50_000_000))
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 50_000_000))   # exactly the daily limit
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "DAILY")
        self.s.set_time(day_start + NS_PER_DAY)                                  # next UTC day
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 1))

    def test_two_times_daily_around_midnight_is_possible_documented(self):
        """BF2-2 carried over: fixed UTC day, not a rolling 24 hours."""
        midnight = (self.s.now // NS_PER_DAY + 1) * NS_PER_DAY
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 50_000_000, 100_000_000, 1_000_000_000, 50_000_000, self.s.now + 5 * NS_PER_DAY))
        self.s.set_time(midnight - 2 * 10**9)
        for _ in range(2):
            self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 50_000_000))
        self.s.set_time(midnight + 1 * 10**9)
        for _ in range(2):
            self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 50_000_000))
        self.assertEqual(self.bal(self.r[0]), 200_000_000)   # 2 x daily within 3 seconds

    def test_budget_includes_reservations(self):
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 50_000_000, 100_000_000, 100_000_000, 10_000_000, self.s.now + NS_PER_DAY))
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 50_000_000))   # pending, reserved
        self.ok(self.fs.request_payment(self.a, self.v, self.r[1], 50_000_000))   # pending, reserved
        # next UTC day: the day window is empty again, so only the budget (incl. reservations) can block
        self.s.set_time((self.s.now // NS_PER_DAY + 1) * NS_PER_DAY + 10**9)
        self.assertEqual(self.fs.request(self.v, self.a, 0)["status"], C["FS_REQ_PENDING"])
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "BUDGET")

    def test_lifetime_budget_exhaustion(self):
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 10_000_000, 20_000_000, 30_000_000, 10_000_000, self.s.now + 10 * NS_PER_DAY))
        for day in range(3):
            self.s.set_time((self.s.now // NS_PER_DAY + 1) * NS_PER_DAY + 10**9)
            self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 10_000_000))
        self.s.set_time((self.s.now // NS_PER_DAY + 1) * NS_PER_DAY + 10**9)
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "BUDGET")


class Expiry(Base):
    def test_expired_key_cannot_request_or_be_approved_and_renewal_restores(self):
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 50_000_000, 200_000_000, 1_000_000_000, 10_000_000, self.s.now + 3600 * 10**9))
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000))
        self.s.advance(3600)
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "AGENT_EXPIRED")
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "AGENT_EXPIRED")
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 50_000_000, 200_000_000, 1_000_000_000, 10_000_000, self.s.now + NS_PER_DAY))
        self.ok(self.fs.approve(self.o, self.v, self.a, 0))

    def test_key_boundary_is_exclusive(self):
        vu = self.s.now + 3600 * 10**9
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 50_000_000, 200_000_000, 1_000_000_000, 10_000_000, vu))
        self.s.set_time(vu - 1)
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 1))
        self.s.set_time(vu)
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "AGENT_EXPIRED")


class Allowlist(Base):
    def test_not_allowlisted_recipient_rejected(self):
        other = key("unlisted-token")
        self.s.put_token_account(other, self.w["mint"], key("someone"), 0)
        self.fails(self.fs.request_payment(self.a, self.v, other, 1), "RECIPIENT_NOT_ALLOWED")

    def test_removed_recipient_blocks_payment_and_approval(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000))
        self.ok(self.fs.set_recipient(self.o, self.v, self.a, self.r[0], False))
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "RECIPIENT_NOT_ALLOWED")
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "RECIPIENT_NOT_ALLOWED")
        self.ok(self.fs.set_recipient(self.o, self.v, self.a, self.r[0], True))
        self.ok(self.fs.approve(self.o, self.v, self.a, 0))

    def test_capacity_is_eight(self):
        for i in range(2, 8):
            self.ok(self.fs.set_recipient(self.o, self.v, self.a, key(f"cap-{i}"), True))
        self.fails(self.fs.set_recipient(self.o, self.v, self.a, key("cap-9"), True), "ALLOWLIST_FULL")


class Revocation(Base):
    def test_revoked_agent_cannot_request(self):
        self.ok(self.fs.revoke(self.o, self.v, self.a))
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "UNKNOWN_AGENT")

    def test_revoke_releases_reservations_and_old_request_never_executes(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000))
        self.ok(self.fs.revoke(self.o, self.v, self.a))
        a = self.agent()
        self.assertEqual((a["active"], a["epoch"], a["reserved"]), (0, 1, 0))
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 50_000_000, 200_000_000, 1_000_000_000, 10_000_000, self.s.now + NS_PER_DAY))
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "STALE_REQUEST")
        ev = self.ok(self.fs.expire(self.x, self.v, self.a, 0))     # stale: closable before TTL
        self.assertEqual([e[1][0] for e in ev], [C["FS_EV_INVALIDATED"]])
        self.assertEqual(self.agent()["reserved"], 0)


class PauseKill(Base):
    def test_pause_blocks_and_unpause_restores(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000))
        self.ok(self.fs.set_paused(self.o, self.v, True))
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "PAUSED")
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "PAUSED")
        self.ok(self.fs.set_paused(self.o, self.v, False))
        self.ok(self.fs.approve(self.o, self.v, self.a, 0))

    def test_kill_is_irreversible_but_withdrawal_remains(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000))
        self.ok(self.fs.kill(self.o, self.v))
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "KILLED")
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "KILLED")
        self.fails(self.fs.set_paused(self.o, self.v, False), "KILLED")
        self.fails(self.fs.set_agent(self.o, self.v, self.a, 1, 1, 1, 0, self.s.now + NS_PER_DAY), "KILLED")
        self.ok(self.fs.reject(self.a, self.v, self.a, 0))
        dest = key("owner-token")
        self.s.put_token_account(dest, self.w["mint"], self.o, 0)
        bal = self.bal(self.w["vault_token"])
        self.ok(self.fs.withdraw(self.o, self.v, dest, bal))
        self.assertEqual((self.bal(self.w["vault_token"]), self.bal(dest)), (0, bal))


if __name__ == "__main__":
    unittest.main()
