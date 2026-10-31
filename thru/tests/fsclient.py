"""Flowstate on Thru — Python client for the LOCAL SIMULATION (host build of the real program code).

Builds the exact instruction bytes defined in thru/program/flowstate_abi.h. Constants are parsed
from the C headers (single source of truth). Every transaction is executed by
thru/build/host/libflowstate_sim.so: the same flowstate.c / flowstate_core.c that compiles for the
Thru VM, linked against a host simulation of the SDK. NOT THE THRU VM, NOT A NETWORK.

In the simulation a "signature" is modelled by being the transaction's fee payer, exactly as the
SDK's authorization rule describes; no cryptographic signature is created or checked here."""
import ctypes
import hashlib
import json
import os
import re
import struct

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIB = os.environ.get("FS_SIM_LIB") or os.path.join(ROOT, "build", "host", "libflowstate_sim.so")


def _parse_constants():
    c = {}
    for f in ("program/flowstate_core.h", "program/flowstate_abi.h"):
        src = open(os.path.join(ROOT, f)).read()
        for m in re.finditer(r"#define\s+(FS_[A-Z0-9_]+)\s+\(?(0x[0-9A-Fa-f]+|\d+)(?:ULL|u|U)?\b", src):
            c[m.group(1)] = int(m.group(2), 0)
        for m in re.finditer(r"\b(FS_[A-Z0-9_]+)\s*=\s*(0x[0-9A-Fa-f]+|\d+)", src):
            c[m.group(1)] = int(m.group(2), 0)
        for m in re.finditer(r'#define\s+(FS_SEED_TAG_[A-Z]+)\s+"([^"]+)"', src):
            c[m.group(1)] = m.group(2).encode()
    return c


C = _parse_constants()
ERR_NAMES = {v: k for k, v in C.items() if k.startswith("FS_ERR_")}
NS_PER_DAY = 86_400 * 10**9
NO_ACCOUNT = C["FS_NO_ACCOUNT"]

VAULT_FMT = "<IBBH32s32s32sQQQII"
AGENT_FMT = "<IBBBB32s32s" + "Q" * 11 + "256s"
REQ_FMT = "<IBBH32s32s32s32sQQQQQQ"
APPROVAL_FMT = "<32s32s32s32sQQQB"
TOKEN_FMT = "<32s32sQB"
assert struct.calcsize(VAULT_FMT) == 136 and struct.calcsize(AGENT_FMT) == 416
assert struct.calcsize(REQ_FMT) == 184 and struct.calcsize(APPROVAL_FMT) == 153 and struct.calcsize(TOKEN_FMT) == 73


def sha256(*parts):
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
    return h.digest()


def pda(program, seed):
    """Program-defined account address, as tsdk_create_program_defined_account_address."""
    return sha256(program, b"\x00", seed)


def u64(x):
    return struct.pack("<Q", x)


def key(label):
    """Deterministic 32-byte public key for a named test actor (simulation only)."""
    return sha256(b"flowstate-sim-key/", label.encode())


def err_name(code):
    return "OK" if code == 0 else ERR_NAMES.get(code, hex(code))


class Sim:
    def __init__(self, program_label="flowstate-local-sim"):
        self.lib = ctypes.CDLL(LIB)
        L = self.lib
        L.sim_exec.restype = ctypes.c_ulong
        L.sim_exec.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_ulong]
        L.sim_get_account.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]
        L.sim_put_account.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong]
        L.sim_set_clock.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
        L.sim_event.restype = ctypes.c_ulong
        L.sim_event.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong]
        L.sim_sha256.argtypes = [ctypes.c_char_p, ctypes.c_ulong, ctypes.c_char_p]
        self.program = key(program_label)
        L.sim_reset(self.program)
        tp = ctypes.create_string_buffer(32)
        L.sim_token_program(tp)
        self.token_program = tp.raw
        self.slot = 1
        self.now = 1_900_000_000 * 10**9
        L.sim_set_clock(self.slot, self.now)
        self.trace = []

    # ---------------------------------------------------------------- chain access
    def set_time(self, ns):
        self.now = ns
        self.slot += 1
        self.lib.sim_set_clock(self.slot, ns)

    def advance(self, seconds):
        self.set_time(self.now + seconds * 10**9)

    def account(self, addr):
        owner = ctypes.create_string_buffer(32)
        data = ctypes.create_string_buffer(1024)
        sz = ctypes.c_ulong(0)
        if not self.lib.sim_get_account(addr, owner, data, 1024, ctypes.byref(sz)):
            return None
        return owner.raw, data.raw[: sz.value]

    def put_account(self, addr, owner, data=b""):
        assert self.lib.sim_put_account(addr, owner, data, len(data)) == 0

    def sha256_c(self, data):
        out = ctypes.create_string_buffer(32)
        self.lib.sim_sha256(data, len(data), out)
        return out.raw

    # ---------------------------------------------------------------- token accounts (test setup)
    def put_token_account(self, addr, mint, owner, amount, frozen=0):
        """Stands in for the token program's initialize_account + mint_to (test setup, not an instruction)."""
        self.put_account(addr, self.token_program, struct.pack(TOKEN_FMT, mint, owner, amount, frozen))

    def put_mint_account(self, addr, mint_authority, freeze_authority=None, supply=0, decimals=6):
        """Test setup: a TokenMintAccount laid out per the official ABI (115 bytes)."""
        data = struct.pack("<BQ32s32s32sB", decimals, supply, mint_authority, mint_authority,
                           freeze_authority or bytes(32), 1 if freeze_authority else 0) + bytes([4]) + b"TEST\0\0\0\0"
        assert len(data) == 115
        self.put_account(addr, self.token_program, data)

    def token(self, addr):
        a = self.account(addr)
        if not a:
            return None
        mint, owner, amount, frozen = struct.unpack(TOKEN_FMT, a[1])
        return {"mint": mint, "owner": owner, "amount": amount, "frozen": frozen}

    # ---------------------------------------------------------------- execution
    def exec(self, fee_payer, rw, ro, instr, program=None, label=""):
        program = program or self.program
        rc = self.lib.sim_exec(program, fee_payer, b"".join(rw), len(rw), b"".join(ro), len(ro), instr, len(instr))
        events = []
        for i in range(self.lib.sim_event_count()):
            prog = ctypes.create_string_buffer(32)
            buf = ctypes.create_string_buffer(512)
            n = self.lib.sim_event(i, prog, buf, 512)
            events.append((prog.raw, buf.raw[:n]))
        self.trace.append({"label": label, "slot": self.slot, "time_ns": self.now, "program": program.hex(),
                           "fee_payer": fee_payer.hex(), "instr": instr.hex(), "rc": rc,
                           "events": [{"program": p.hex(), "data": d.hex()} for p, d in events]})
        return rc, events

    def save_trace(self, path, snapshot=None):
        with open(path, "w") as fh:
            for t in self.trace:
                fh.write(json.dumps(t) + "\n")
            if snapshot is not None:
                fh.write(json.dumps({"snapshot": snapshot}) + "\n")


def tx_index(fee_payer, rw, ro):
    """Canonicalises the account lists IN PLACE per the official rule (no duplicates anywhere; read-write
    and read-only each sorted ascending; the fee payer only at index 0) and returns the index lookup.
    Callers pass the same list objects to Sim.exec afterwards."""
    rw[:] = sorted({a for a in rw if a != fee_payer})
    ro[:] = sorted({a for a in ro if a != fee_payer and a not in rw})
    order = [fee_payer, None] + list(rw) + list(ro)
    def idx(addr):
        for i, a in enumerate(order):
            if a == addr:
                return i
        raise KeyError("account not in transaction")
    return idx


def direct_transfer(sim, fee_payer, src, dst, amount):
    """A token-program transfer sent straight to the token program (no ThruBound), with canonical lists."""
    rw, ro = [src, dst], []
    idx = tx_index(fee_payer, rw, ro)
    ix = struct.pack("<BHHQ", 2, idx(src), idx(dst), amount)
    return sim.exec(fee_payer, rw, ro, ix, program=sim.token_program, label="direct")


# -------------------------------------------------------------------- state decoders
def decode_vault(data):
    f = struct.unpack(VAULT_FMT, data)
    return dict(zip(["magic", "version", "flags", "r0", "owner", "mint", "token_account", "vault_id", "ttl_ns", "total_paid", "agent_count", "r1"], f))


def decode_agent(data):
    f = struct.unpack(AGENT_FMT, data)
    names = ["magic", "version", "active", "recipient_cnt", "r0", "vault", "agent", "epoch", "per_tx", "daily", "budget",
             "threshold", "valid_until_ns", "day", "daily_used", "spent", "reserved", "next_nonce", "recipients_raw"]
    d = dict(zip(names, f))
    d["recipients"] = [d["recipients_raw"][32 * i: 32 * i + 32] for i in range(d["recipient_cnt"])]
    return d


def decode_request(data):
    f = struct.unpack(REQ_FMT, data)
    return dict(zip(["magic", "version", "status", "r0", "vault", "agent", "recipient", "mint", "amount", "nonce", "epoch", "day", "created_ns", "expires_ns"], f))


# -------------------------------------------------------------------- high-level flows
class Flowstate:
    """Convenience layer: one method per instruction; returns (rc, events)."""

    def __init__(self, sim):
        self.s = sim
        self.P = sim.program

    def vault_addr(self, owner, vault_id):
        return pda(self.P, sha256(C["FS_SEED_TAG_VAULT"], owner, u64(vault_id)))

    def agent_addr(self, vault, agent):
        return pda(self.P, sha256(C["FS_SEED_TAG_AGENT"], vault, agent))

    def request_addr(self, vault, agent, nonce):
        return pda(self.P, sha256(C["FS_SEED_TAG_REQUEST"], vault, agent, u64(nonce)))

    def vault(self, v):
        a = self.s.account(v)
        return decode_vault(a[1]) if a else None

    def agent(self, v, agent):
        a = self.s.account(self.agent_addr(v, agent))
        return decode_agent(a[1]) if a else None

    def request(self, v, agent, nonce):
        a = self.s.account(self.request_addr(v, agent, nonce))
        return decode_request(a[1]) if a else None

    # instructions -------------------------------------------------------------------
    def init_vault(self, owner, vault_id, mint, ttl_ns=86_400 * 10**9, signer=None):
        signer = signer or owner
        v = self.vault_addr(owner, vault_id)
        rw, ro = [v], [] if signer == owner else [owner]
        idx = tx_index(signer, rw, ro)
        ix = struct.pack("<BHH32sQQI", C["FS_OP_INIT_VAULT"], idx(v), idx(owner), mint, vault_id, ttl_ns, 0)
        return self.s.exec(signer, rw, ro, ix, label="init_vault")

    def bind_token(self, owner, v, token_acct, signer=None, mint_acct=None):
        signer = signer or owner
        rw, ro = [v], [token_acct] + ([] if signer == owner else [owner]) + ([mint_acct] if mint_acct else [])
        idx = tx_index(signer, rw, ro)
        ix = struct.pack("<BHHHH", C["FS_OP_BIND_TOKEN"], idx(v), idx(owner), idx(token_acct),
                         idx(mint_acct) if mint_acct else C["FS_NO_ACCOUNT"])
        return self.s.exec(signer, rw, ro, ix, label="bind_token")

    def set_agent(self, owner, v, agent, per_tx, daily, budget, threshold, valid_until_ns, create=None, signer=None):
        signer = signer or owner
        a = self.agent_addr(v, agent)
        if create is None:
            create = self.s.account(a) is None
        rw, ro = [v, a], ([] if signer == owner else [owner])
        idx = tx_index(signer, rw, ro)
        ix = struct.pack("<BHHH32sQQQQQBI", C["FS_OP_SET_AGENT"], idx(v), idx(owner), idx(a), agent, per_tx, daily, budget, threshold, valid_until_ns, 1 if create else 0, 0)
        return self.s.exec(signer, rw, ro, ix, label="set_agent")

    def revoke(self, owner, v, agent, signer=None):
        signer = signer or owner
        a = self.agent_addr(v, agent)
        rw, ro = [a], [v] + ([] if signer == owner else [owner])
        idx = tx_index(signer, rw, ro)
        return self.s.exec(signer, rw, ro, struct.pack("<BHHH", C["FS_OP_REVOKE"], idx(v), idx(owner), idx(a)), label="revoke")

    def set_recipient(self, owner, v, agent, recipient, allowed=True, signer=None):
        signer = signer or owner
        a = self.agent_addr(v, agent)
        rw, ro = [a], [v] + ([] if signer == owner else [owner])
        idx = tx_index(signer, rw, ro)
        ix = struct.pack("<BHHH32sB", C["FS_OP_SET_RECIPIENT"], idx(v), idx(owner), idx(a), recipient, 1 if allowed else 0)
        return self.s.exec(signer, rw, ro, ix, label="set_recipient")

    def request_payment(self, agent, v, recipient_token, amount, nonce=None, signer=None, pending=None,
                        vault_token=None, token_program=None, agent_signer=None):
        signer = signer or agent
        agent_signer = agent_signer or agent
        vd = self.vault(v)
        ad = self.agent(v, agent)
        if nonce is None:
            nonce = ad["next_nonce"] if ad else 0
        if pending is None:
            pending = bool(ad) and amount > ad["threshold"]
        vault_token = vault_token or (vd["token_account"] if vd else bytes(32))
        token_program = token_program or self.s.token_program
        a = self.agent_addr(v, agent)
        req = self.request_addr(v, agent, nonce) if pending else None
        rw = [v, a, vault_token, recipient_token] + ([req] if pending else [])
        ro = [token_program] + ([] if agent_signer == signer else [agent_signer])
        idx = tx_index(signer, rw, ro)
        ix = struct.pack("<BHHHHHHHQQI", C["FS_OP_REQUEST"], idx(v), idx(a), idx(agent_signer), idx(req) if pending else NO_ACCOUNT,
                         idx(vault_token), idx(recipient_token), idx(token_program), nonce, amount, 0)
        return self.s.exec(signer, rw, ro, ix, label="request")

    def approval_for(self, v, agent, nonce, **override):
        r = self.request(v, agent, nonce)
        b = dict(vault=r["vault"], agent=r["agent"], recipient=r["recipient"], mint=r["mint"], amount=r["amount"], nonce=r["nonce"], expires_ns=r["expires_ns"], op=C["FS_OP_APPROVE"])
        b.update(override)
        return b

    def approve(self, owner, v, agent, nonce, approval=None, signer=None, recipient_token=None, vault_token=None, token_program=None):
        signer = signer or owner
        ap = approval or self.approval_for(v, agent, nonce)
        a, req = self.agent_addr(v, agent), self.request_addr(v, agent, nonce)
        vd = self.vault(v)
        vault_token = vault_token or vd["token_account"]
        recipient_token = recipient_token or ap["recipient"]
        token_program = token_program or self.s.token_program
        rw = [v, a, req, vault_token, recipient_token]
        ro = [token_program] + ([] if signer == owner else [owner])
        idx = tx_index(signer, rw, ro)
        approval = struct.pack(APPROVAL_FMT, ap["vault"], ap["agent"], ap["recipient"], ap["mint"], ap["amount"], ap["nonce"], ap["expires_ns"], ap["op"])
        ix = struct.pack("<BHHHHHHH", C["FS_OP_APPROVE"], idx(v), idx(owner), idx(a), idx(req), idx(vault_token), idx(recipient_token), idx(token_program)) + approval
        return self.s.exec(signer, rw, ro, ix, label="approve")

    def reject(self, actor, v, agent, nonce, signer=None):
        signer = signer or actor
        a, req = self.agent_addr(v, agent), self.request_addr(v, agent, nonce)
        rw, ro = [a, req], [v] + ([] if signer == actor else [actor])
        idx = tx_index(signer, rw, ro)
        return self.s.exec(signer, rw, ro, struct.pack("<BHHHH", C["FS_OP_REJECT"], idx(v), idx(a), idx(req), idx(actor)), label="reject")

    def expire(self, caller, v, agent, nonce):
        a, req = self.agent_addr(v, agent), self.request_addr(v, agent, nonce)
        rw, ro = [a, req], [v]
        idx = tx_index(caller, rw, ro)
        return self.s.exec(caller, rw, ro, struct.pack("<BHHH", C["FS_OP_EXPIRE"], idx(v), idx(a), idx(req)), label="expire")

    def set_paused(self, owner, v, paused, signer=None):
        signer = signer or owner
        rw, ro = [v], ([] if signer == owner else [owner])
        idx = tx_index(signer, rw, ro)
        return self.s.exec(signer, rw, ro, struct.pack("<BHHB", C["FS_OP_SET_PAUSED"], idx(v), idx(owner), 1 if paused else 0), label="set_paused")

    def kill(self, owner, v, signer=None):
        signer = signer or owner
        rw, ro = [v], ([] if signer == owner else [owner])
        idx = tx_index(signer, rw, ro)
        return self.s.exec(signer, rw, ro, struct.pack("<BHH", C["FS_OP_KILL"], idx(v), idx(owner)), label="kill")

    def withdraw(self, owner, v, dest_token, amount, signer=None, token_program=None):
        signer = signer or owner
        vd = self.vault(v)
        token_program = token_program or self.s.token_program
        rw, ro = [v, vd["token_account"], dest_token], [token_program] + ([] if signer == owner else [owner])
        idx = tx_index(signer, rw, ro)
        ix = struct.pack("<BHHHHHQ", C["FS_OP_WITHDRAW"], idx(v), idx(owner), idx(vd["token_account"]), idx(dest_token), idx(token_program), amount)
        return self.s.exec(signer, rw, ro, ix, label="withdraw")


def setup_world(sim=None, funded=1_000_000_000, per_tx=50_000_000, daily=200_000_000, budget=1_000_000_000,
                threshold=10_000_000, valid_for_ns=30 * NS_PER_DAY, n_recipients=2):
    """Owner + bound vault token account + one agent with allowlisted recipients. Amounts in token base units."""
    s = sim or Sim()
    fs = Flowstate(s)
    owner, agent, attacker = key("owner"), key("agent"), key("attacker")
    mint = key("test-mint")
    rc, _ = fs.init_vault(owner, 1, mint)
    assert rc == 0, err_name(rc)
    v = fs.vault_addr(owner, 1)
    vt = key("vault-token-account")
    s.put_token_account(vt, mint, v, funded)
    s.put_mint_account(mint, owner)            # test mint: authority = owner, NO freeze authority
    rc, _ = fs.bind_token(owner, v, vt, mint_acct=mint)
    assert rc == 0, err_name(rc)
    rc, _ = fs.set_agent(owner, v, agent, per_tx, daily, budget, threshold, s.now + valid_for_ns)
    assert rc == 0, err_name(rc)
    recips = []
    for i in range(n_recipients):
        r = key(f"recipient-token-{i}")
        s.put_token_account(r, mint, key(f"recipient-{i}"), 0)
        rc, _ = fs.set_recipient(owner, v, agent, r, True)
        assert rc == 0, err_name(rc)
        recips.append(r)
    return dict(s=s, fs=fs, owner=owner, agent=agent, attacker=attacker, mint=mint, vault=v, vault_token=vt, recipients=recips)
