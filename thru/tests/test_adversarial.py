"""B. Adversarial tests — LOCAL SIMULATION (host build of the real program code, not the Thru VM).
The token-program cases rely on the documented ABI and the simulation's MODEL of `transfer`
(source owner must be authorized); the real token program's code is not public."""
import struct
import unittest

import fsclient as F
from fsclient import C, NS_PER_DAY, err_name, key
from test_functional import Base


class Replay(Base):
    def test_same_nonce_twice(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 1_000_000, nonce=0))
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1_000_000, nonce=0), "BAD_NONCE")

    def test_future_and_past_nonce(self):
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1_000_000, nonce=5), "BAD_NONCE")
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 1_000_000, nonce=0))
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 1_000_000, nonce=1))
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1_000_000, nonce=0), "BAD_NONCE")

    def test_failed_request_does_not_consume_nonce(self):
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 999_000_000, nonce=0), "PER_TX")
        self.assertEqual(self.agent()["next_nonce"], 0)
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 1_000_000, nonce=0))

    def test_duplicate_pending_request_account(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000, nonce=0))
        # replaying the same request (same nonce -> same request account) is refused
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000, nonce=0), "BAD_NONCE")


class UnauthorizedAgent(Base):
    def test_attacker_cannot_sign_for_the_agent(self):
        # attacker pays the fee and names the real agent as signer: the agent did not authorize this transaction
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1_000_000, signer=self.x), "UNAUTHORIZED")

    def test_attacker_as_its_own_agent_has_no_agent_account(self):
        rc, ev = self.fs.request_payment(self.x, self.v, self.r[0], 1_000_000, nonce=0, pending=False)
        self.assertNotEqual(rc, 0)
        self.assertEqual(ev, [])

    def test_owner_is_not_the_agent(self):
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1_000_000, signer=self.o, agent_signer=self.o), "NOT_AGENT")


class UnauthorizedOwner(Base):
    def test_every_owner_action_requires_the_owner(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000))
        t = self.s.now + NS_PER_DAY
        dest = key("x-token")
        self.s.put_token_account(dest, self.w["mint"], self.x, 0)
        # attacker pays the fee and lists the real owner: owner did not authorize
        cases = [
            lambda: self.fs.approve(self.o, self.v, self.a, 0, signer=self.x),
            lambda: self.fs.set_agent(self.o, self.v, self.a, 50_000_000, 200_000_000, 1_000_000_000, 10_000_000, t, signer=self.x),
            lambda: self.fs.revoke(self.o, self.v, self.a, signer=self.x),
            lambda: self.fs.set_recipient(self.o, self.v, self.a, dest, True, signer=self.x),
            lambda: self.fs.set_paused(self.o, self.v, True, signer=self.x),
            lambda: self.fs.kill(self.o, self.v, signer=self.x),
            lambda: self.fs.withdraw(self.o, self.v, dest, 1, signer=self.x),
        ]
        for c in cases:
            self.fails(c(), "UNAUTHORIZED")
        # attacker names itself as owner: not the vault's owner
        for c in [lambda: self.fs.approve(self.x, self.v, self.a, 0), lambda: self.fs.set_paused(self.x, self.v, True),
                  lambda: self.fs.withdraw(self.x, self.v, dest, 1), lambda: self.fs.kill(self.x, self.v)]:
            self.fails(c(), "NOT_OWNER")
        # the agent itself cannot approve its own request
        self.fails(self.fs.approve(self.a, self.v, self.a, 0), "NOT_OWNER")
        self.assertEqual(self.s.token(dest)["amount"], 0)

    def test_attacker_cannot_reject_or_init_for_owner(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000))
        self.fails(self.fs.reject(self.x, self.v, self.a, 0), "UNAUTHORIZED")
        self.fails(self.fs.init_vault(self.o, 9, self.w["mint"], signer=self.x), "UNAUTHORIZED")


class WrongTokenAndRecipient(Base):
    def test_recipient_token_account_of_another_mint(self):
        other = key("other-mint-token")
        self.s.put_token_account(other, key("other-mint"), key("someone"), 0)
        self.ok(self.fs.set_recipient(self.o, self.v, self.a, other, True))
        self.fails(self.fs.request_payment(self.a, self.v, other, 1_000_000), "WRONG_TOKEN")

    def test_fake_token_program_rejected(self):
        fake = key("fake-token-program")
        self.s.put_account(fake, key("loader"), b"")
        rc, _ = self.fs.request_payment(self.a, self.v, self.r[0], 1_000_000, token_program=fake)
        self.assertEqual(err_name(rc), "FS_ERR_WRONG_TOKEN")

    def test_executable_substituted_for_token_program(self):
        # UNTO-2328 / VERIA-1 (official C SDK v0.4.3): a real executable (a no-op program, flagged PROGRAM)
        # passed as "the token program" must be refused, or the transfer would "succeed" without moving tokens.
        noop = key("noop-program")
        assert self.s.lib.sim_put_program(noop) == 0
        rc, _ = self.fs.request_payment(self.a, self.v, self.r[0], 1_000_000, token_program=noop)
        self.assertEqual(err_name(rc), "FS_ERR_WRONG_TOKEN")

    def test_vault_token_account_substitution(self):
        decoy = key("decoy-vault-token")
        self.s.put_token_account(decoy, self.w["mint"], self.v, 10**9)
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1_000_000, vault_token=decoy), "WRONG_TOKEN")

    def test_approval_recipient_account_must_match(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000))
        self.fails(self.fs.approve(self.o, self.v, self.a, 0, recipient_token=self.r[1]), "APPROVAL_MISMATCH")


class ApprovalBinding(Base):
    def setUp(self):
        super().setUp()
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000))

    def test_every_bound_field_is_checked(self):
        b = self.fs.approval_for(self.v, self.a, 0)
        variants = {"amount": b["amount"] + 1, "nonce": b["nonce"] + 1, "expires_ns": b["expires_ns"] + 1, "op": C["FS_OP_REJECT"],
                    "recipient": self.r[1], "mint": key("other-mint"), "agent": self.x, "vault": key("other-vault")}
        for field, val in variants.items():
            bad = dict(b, **{field: val})
            rc, ev = self.fs.approve(self.o, self.v, self.a, 0, approval=bad)
            self.assertEqual(err_name(rc), "FS_ERR_APPROVAL_MISMATCH", field)
            self.assertEqual(ev, [])
        self.ok(self.fs.approve(self.o, self.v, self.a, 0, approval=b))

    def test_approval_of_one_request_cannot_execute_another(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[1], 40_000_000))
        first = self.fs.approval_for(self.v, self.a, 0)
        # the owner signed an approval for request 0; it cannot be pointed at request 1
        self.fails(self.fs.approve(self.o, self.v, self.a, 1, approval=first), "APPROVAL_MISMATCH")

    def test_expired_approval(self):
        self.s.advance(86_400)
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "REQUEST_EXPIRED")

    def test_approval_reuse(self):
        self.ok(self.fs.approve(self.o, self.v, self.a, 0))
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "NO_PENDING")


class Concurrency(Base):
    def test_pending_requests_cannot_together_exceed_budget(self):
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 50_000_000, 200_000_000, 200_000_000, 10_000_000, self.s.now + 10 * NS_PER_DAY))
        for _ in range(4):
            self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 50_000_000))
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "DAILY")
        self.s.set_time((self.s.now // NS_PER_DAY + 1) * NS_PER_DAY + 1)
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "BUDGET")
        for n in range(4):
            self.ok(self.fs.approve(self.o, self.v, self.a, n))
        a = self.agent()
        self.assertEqual((a["spent"], a["reserved"]), (200_000_000, 0))

    def test_lowered_limits_block_old_approvals(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 40_000_000))
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 20_000_000, 200_000_000, 1_000_000_000, 10_000_000, self.s.now + NS_PER_DAY))
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "PER_TX")


class Overflow(Base):
    def test_max_values_never_wrap(self):
        M = 2**64 - 1
        self.s.put_token_account(self.w["vault_token"], self.w["mint"], self.v, M)
        self.ok(self.fs.set_agent(self.o, self.v, self.a, M, M, M, M, self.s.now + NS_PER_DAY))
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 2**63))
        snap = self.agent()
        # 2^63 + 2^63 = 2^64 does not fit in u64: must be rejected (DAILY or OVERFLOW), never wrap
        for when in ("same day", "next day"):
            if when == "next day":
                self.s.set_time((self.s.now // NS_PER_DAY + 1) * NS_PER_DAY + 1)
            for amt in (2**63, M):
                rc, ev = self.fs.request_payment(self.a, self.v, self.r[0], amt)
                self.assertIn(err_name(rc), ("FS_ERR_DAILY", "FS_ERR_BUDGET", "FS_ERR_OVERFLOW"), (when, amt))
                self.assertEqual(ev, [])
        after = self.agent()
        self.assertEqual((after["spent"], after["reserved"], after["next_nonce"]), (snap["spent"], snap["reserved"], snap["next_nonce"]))
        self.assertEqual(self.bal(self.r[0]), 2**63)


class TransactionFormat(Base):
    """The simulation enforces the official account-list rule, so every other test runs with lists a real
    Thru node would accept (docs: Transactions > Account List Verification)."""
    def test_unsorted_or_duplicate_account_lists_are_invalid(self):
        hi, lo = sorted([self.v, self.fs.agent_addr(self.v, self.a)], reverse=True)
        ix = struct.pack("<BHHB", C["FS_OP_SET_PAUSED"], 2, 0, 1)
        self.assertEqual(err_name(self.s.exec(self.o, [hi, lo], [], ix)[0]), "0xb007")          # rw unsorted
        self.assertEqual(err_name(self.s.exec(self.o, [], [hi, lo], ix)[0]), "0xb008")          # ro unsorted
        self.assertEqual(err_name(self.s.exec(self.o, [self.v], [self.v], ix)[0]), "0xb006")    # duplicate
        self.assertEqual(err_name(self.s.exec(self.o, [self.o], [], ix)[0]), "0xb006")          # fee payer repeated
        self.assertEqual(self.fs.vault(self.v)["flags"] & C["FS_VAULT_PAUSED"], 0)


class AlternateTransferRoutes(Base):
    """Thru counterpart of KSI-1: can the vault's tokens move without Flowstate's checks?"""

    def direct_transfer(self, fee_payer, src, dst, amount):
        # official token ABI: transfer(source_idx, dest_idx, amount), canonical account lists
        return F.direct_transfer(self.s, fee_payer, src, dst, amount)

    def test_nobody_can_move_vault_tokens_directly(self):
        before = self.bal(self.w["vault_token"])
        for who in (self.x, self.a, self.o):          # attacker, agent AND owner: none of them is the token-account owner
            rc, _ = self.direct_transfer(who, self.w["vault_token"], self.r[0], 1)
            self.assertEqual(err_name(rc), "0x2006")   # the token model's AUTH check, not a malformed transaction
        self.assertEqual(self.bal(self.w["vault_token"]), before)

    def test_flowstate_never_authorizes_the_vault_outside_its_checks(self):
        # over-limit request: the program reverts before any token CPI, so nothing moves
        before = self.bal(self.w["vault_token"])
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 60_000_000), "PER_TX")
        self.assertEqual(self.bal(self.w["vault_token"]), before)


class AccountSubstitution(Base):
    def test_foreign_owned_account_at_the_derived_address(self):
        """A READ-ONLY account at the correct derived address but owned by ANOTHER program must be refused:
        here a forged copy of the vault (owner field = attacker) is used to add the attacker's token account
        to the real agent's allowlist. Writable accounts are already protected by the runtime (a program can
        only write accounts it owns); for read-only accounts the program's own owner check is the defence.
        On Thru only this program can create accounts at its derived addresses, so this is defence in depth;
        the simulation lets us place such an account to test the check itself."""
        loot = key("x-loot-token")
        self.s.put_token_account(loot, self.w["mint"], self.x, 0)
        real = self.s.account(self.v)
        forged = bytearray(real[1]); forged[8:40] = self.x               # vault.owner := attacker
        self.s.put_account(self.v, key("some-other-program"), bytes(forged))
        agent_before = self.fs.agent(self.v, self.a)
        rc, ev = self.fs.set_recipient(self.x, self.v, self.a, loot, True)
        self.assertEqual(err_name(rc), "FS_ERR_BAD_ACCOUNT")
        self.assertEqual(ev, [])
        self.assertEqual(self.fs.agent(self.v, self.a), agent_before)
        self.s.put_account(self.v, real[0], real[1])                     # restore the real vault

    def test_agent_account_of_another_vault(self):
        self.ok(self.fs.init_vault(self.x, 1, self.w["mint"]))
        xv = self.fs.vault_addr(self.x, 1)
        xt = key("x-vault-token")
        self.s.put_token_account(xt, self.w["mint"], xv, 0)
        self.ok(self.fs.bind_token(self.x, xv, xt))
        self.ok(self.fs.set_agent(self.x, xv, self.a, 1, 1, 1, 0, self.s.now + NS_PER_DAY))
        # use the attacker-vault agent account (generous? no: tiny) against the real vault
        idx_agent = self.fs.agent_addr(xv, self.a)
        rw, ro = [self.v, idx_agent, self.w["vault_token"], self.r[0]], [self.s.token_program]
        i = F.tx_index(self.a, rw, ro)
        ix = struct.pack("<BHHHHHHHQQI", C["FS_OP_REQUEST"], i(self.v), i(idx_agent), 0, F.NO_ACCOUNT,
                         i(self.w["vault_token"]), i(self.r[0]), i(self.s.token_program), 0, 1, 0)
        rc, _ = self.s.exec(self.a, rw, ro, ix)
        self.assertEqual(err_name(rc), "FS_ERR_WRONG_VAULT")

    def test_counterfeit_vault_account_not_owned_by_program(self):
        real = self.s.account(self.v)[1]
        fake = key("counterfeit-vault")
        self.s.put_account(fake, self.x, real)             # same bytes, wrong owner
        ix = struct.pack("<BHHB", C["FS_OP_SET_PAUSED"], 2, 0, 1)
        rc, _ = self.s.exec(self.o, [fake], [], ix)
        self.assertEqual(err_name(rc), "FS_ERR_BAD_ACCOUNT")

    def test_vault_passed_read_only_cannot_be_written(self):
        before = self.fs.vault(self.v)
        ix = struct.pack("<BHHB", C["FS_OP_SET_PAUSED"], 2, 0, 1)
        rc, _ = self.s.exec(self.o, [], [self.v], ix)
        self.assertEqual(err_name(rc), "FS_ERR_BAD_ACCOUNT")
        self.assertEqual(self.fs.vault(self.v), before)                 # nothing changed, not paused
        self.assertEqual(self.fs.vault(self.v)["flags"] & C["FS_VAULT_PAUSED"], 0)

    def test_malformed_instructions(self):
        for ix in [b"", b"\x63", struct.pack("<BHH", C["FS_OP_SET_PAUSED"], 2, 0), struct.pack("<BHHBB", C["FS_OP_SET_PAUSED"], 2, 0, 1, 7)]:
            rc, ev = self.s.exec(self.o, [self.v], [], ix)
            self.assertEqual(err_name(rc), "FS_ERR_BAD_INSTRUCTION")
            self.assertEqual(ev, [])


class PauseAndRevocationBypass(Base):
    def test_pause_bypass_attempts(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000))
        self.ok(self.fs.set_paused(self.o, self.v, True))
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1), "PAUSED")
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "PAUSED")
        rc, _ = AlternateTransferRoutes.direct_transfer(self, self.a, self.w["vault_token"], self.r[0], 1)
        self.assertNotEqual(rc, 0)

    def test_revocation_bypass_attempts(self):
        self.ok(self.fs.request_payment(self.a, self.v, self.r[0], 30_000_000))
        self.ok(self.fs.revoke(self.o, self.v, self.a))
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "UNKNOWN_AGENT")
        self.fails(self.fs.request_payment(self.a, self.v, self.r[0], 1, nonce=1, pending=False), "UNKNOWN_AGENT")
        self.ok(self.fs.set_agent(self.o, self.v, self.a, 50_000_000, 200_000_000, 1_000_000_000, 10_000_000, self.s.now + NS_PER_DAY))
        self.fails(self.fs.approve(self.o, self.v, self.a, 0), "STALE_REQUEST")


if __name__ == "__main__":
    unittest.main()
