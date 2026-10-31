/* Flowstate on Thru — on-chain program (C SDK).
 *
 * Thin adapter around flowstate_core.c: it parses the instruction, checks every account
 * (owner program, derived address, stored keys), checks authorization with the SDK's
 * tsdk_is_account_authorized_by_idx (fee payer, or an account authorized by a calling
 * program), runs the policy core, writes state, emits events, and moves tokens ONLY through
 * the official token program with the vault account as the authorized token-account owner.
 * Any failure calls tsdk_revert(), which reverts the whole transaction.
 *
 * UNAUDITED. NOT DEPLOYED. Compiled for RISC-V but NOT EXECUTED ON A THRU VM in this
 * repository: tests run the same code on the host against thru/sim (a simulation of the SDK). */
#include <thru-sdk/c/tn_sdk.h>
#include <thru-sdk/c/tn_sdk_syscall.h>
#include <thru-sdk/c/tn_sdk_sha256.h>
#include <stddef.h>
#include "flowstate_abi.h"

#ifndef FS_TOKEN_PROGRAM_BYTES
/* Source-documented address of the official token program on freshly bootstrapped networks
   (tn_sdk_programs.h). Must be verified against the target network before any deployment. */
#define FS_TOKEN_PROGRAM_BYTES TSDK_TOKEN_PROGRAM_ADDR_BYTES
#endif
static uchar const TOKEN_PROGRAM[32] = FS_TOKEN_PROGRAM_BYTES;

#define REQUIRE(c, e) do { if (!(c)) tsdk_revert((ulong)(e)); } while (0)
#define CHECK(e) do { int _e = (e); if (_e) tsdk_revert((ulong)_e); } while (0)

/* ------------------------------------------------------------------ helpers */
static tn_pubkey_t const * addr_of(ushort idx) {
  REQUIRE(tsdk_is_account_idx_valid(idx), FS_ERR_BAD_ACCOUNT);
  return &tsdk_txn_get_acct_addrs(tsdk_get_txn())[idx];
}

static void require_signer(ushort idx, uchar const expected[32], int err) {
  REQUIRE(tsdk_is_account_idx_valid(idx), FS_ERR_BAD_ACCOUNT);
  REQUIRE(fs_key_eq(addr_of(idx)->key, expected), err);
  REQUIRE(tsdk_is_account_authorized_by_idx(idx), FS_ERR_UNAUTHORIZED);
}

static void derive_seed(char const *tag, void const *a, ulong asz, void const *b, ulong bsz, void const *c, ulong csz, uchar seed[32]) {
  tsdk_sha256_t sha; tsdk_sha256_init(&sha);
  ulong tl = 0; while (tag[tl]) tl++;
  tsdk_sha256_append(&sha, tag, tl);
  if (asz) tsdk_sha256_append(&sha, a, asz);
  if (bsz) tsdk_sha256_append(&sha, b, bsz);
  if (csz) tsdk_sha256_append(&sha, c, csz);
  tsdk_sha256_fini(&sha, seed);
}

static void require_derived(ushort idx, uchar const seed[32]) {
  tn_pubkey_t expect;
  tsdk_create_program_defined_account_address(tsdk_get_current_program_acc_addr(), 0, seed, &expect);
  REQUIRE(fs_key_eq(addr_of(idx)->key, expect.key), FS_ERR_DERIVATION);
}

/* Program-owned account of exactly `sz` bytes; returns a pointer to its data. */
static void * load_owned(ushort idx, ulong sz) {
  REQUIRE(tsdk_is_account_idx_valid(idx) && tsdk_account_exists(idx), FS_ERR_BAD_ACCOUNT);
  REQUIRE(tsdk_is_account_owned_by_current_program(idx), FS_ERR_BAD_ACCOUNT);
  REQUIRE(tsdk_get_account_meta(idx)->data_sz == sz, FS_ERR_BAD_ACCOUNT);
  return tsdk_get_account_data_ptr(idx);
}

static void * make_writable(ushort idx) {
  REQUIRE(tsys_set_account_data_writable(idx) == TSDK_SUCCESS, FS_ERR_BAD_ACCOUNT);
  return tsdk_get_account_data_ptr(idx);
}

/* Create a program-defined account of `sz` bytes at idx (address must match the seed). */
static void * create_account(ushort idx, uchar const seed[32], void const *proof, ulong proof_sz, ulong sz) {
  require_derived(idx, seed);
  REQUIRE(!tsdk_account_exists(idx), FS_ERR_ALREADY_INITIALIZED);
  REQUIRE(tsys_account_create(idx, seed, proof, proof_sz) == TSDK_SUCCESS, FS_ERR_ACCOUNT_CREATE);
  /* Official order (C SDK reference, Syscalls: "tsys_account_resize ... The account must already be
     writable"; quickstart counter program): create, then set writable, then resize. */
  REQUIRE(tsys_set_account_data_writable(idx) == TSDK_SUCCESS, FS_ERR_ACCOUNT_CREATE);
  REQUIRE(tsys_account_resize(idx, sz) == TSDK_SUCCESS, FS_ERR_ACCOUNT_CREATE);
  void *p = tsdk_get_account_data_ptr(idx);
  REQUIRE(p != 0, FS_ERR_ACCOUNT_CREATE);
  memset(p, 0, sz);
  return p;
}

static fs_token_account_t const * load_token_account(ushort idx) {
  REQUIRE(tsdk_is_account_idx_valid(idx) && tsdk_account_exists(idx), FS_ERR_BAD_ACCOUNT);
  tsdk_account_meta_t const *m = tsdk_get_account_meta(idx);
  REQUIRE(fs_key_eq(m->owner.key, TOKEN_PROGRAM), FS_ERR_WRONG_TOKEN);
  REQUIRE(m->data_sz == FS_TOKEN_ACCOUNT_SZ, FS_ERR_WRONG_TOKEN);
  return (fs_token_account_t const *)tsdk_get_account_data_ptr(idx);
}

/* The ONLY place tokens leave a vault: official token program, vault account authorized as owner. */
static void token_transfer(ushort token_program_idx, ushort vault_idx, ushort src_idx, ushort dst_idx, ulong amount) {
  /* Invoke-target authentication (official C SDK v0.4.3, UNTO-2328): the index must name the canonical
     token program AND an existing account flagged PROGRAM, so a substituted executable can never make the
     transfer "succeed" without moving tokens. Same checks as tsdk_is_program_at_idx. */
  REQUIRE(fs_key_eq(addr_of(token_program_idx)->key, TOKEN_PROGRAM), FS_ERR_WRONG_TOKEN);
  REQUIRE(tsdk_account_exists(token_program_idx), FS_ERR_WRONG_TOKEN);
  REQUIRE(tsdk_get_account_meta(token_program_idx)->flags & TSDK_ACCOUNT_FLAG_PROGRAM, FS_ERR_WRONG_TOKEN);
  fs_token_transfer_ix_t ix = { FS_TOKEN_IX_TRANSFER, src_idx, dst_idx, amount };
  /* tsdk_invoke_auth_t has a flexible array: build it field by field in an aligned buffer.
     The SDK's tsys_invoke itself rejects auth entries not owned by this program. */
  ulong authbuf[2] = { 0UL, 0UL };
  ulong magic = TSDK_INVOKE_AUTH_MAGIC; ushort cnt = 1, dcnt = 0;
  memcpy((uchar *)authbuf + offsetof(tsdk_invoke_auth_t, magic), &magic, sizeof magic);
  memcpy((uchar *)authbuf + offsetof(tsdk_invoke_auth_t, auth_cnt), &cnt, sizeof cnt);
  memcpy((uchar *)authbuf + offsetof(tsdk_invoke_auth_t, deauth_cnt), &dcnt, sizeof dcnt);
  memcpy((uchar *)authbuf + offsetof(tsdk_invoke_auth_t, acc_idxs), &vault_idx, sizeof vault_idx);
  ulong err = 0;
  ulong rc = tsys_invoke(&ix, sizeof ix, token_program_idx, (tsdk_invoke_auth_t const *)tsdk_type_pun_const(authbuf), &err);
  REQUIRE(rc == TSDK_SUCCESS && err == 0, FS_ERR_TRANSFER_FAILED);
}

static ulong now_ns(void) { return tsdk_get_current_block_ctx()->block_time; }

static void emit(void const *ev, ulong sz) { tsys_emit_event(ev, sz); }

/* Load + validate the vault at idx (program-owned, right size, initialized). */
static fs_vault_t * vault_at(ushort idx) {
  fs_vault_t *v = (fs_vault_t *)load_owned(idx, sizeof(fs_vault_t));
  REQUIRE(v->magic == FS_VAULT_MAGIC && v->version == FS_LAYOUT_VERSION, FS_ERR_NOT_INITIALIZED);
  return v;
}

/* Load + validate the agent account at idx for the given vault (derived address re-checked). */
static fs_agent_t * agent_at(ushort idx, ushort vault_idx) {
  fs_agent_t *a = (fs_agent_t *)load_owned(idx, sizeof(fs_agent_t));
  REQUIRE(a->magic == FS_AGENT_MAGIC, FS_ERR_UNKNOWN_AGENT);
  REQUIRE(fs_key_eq(a->vault, addr_of(vault_idx)->key), FS_ERR_WRONG_VAULT);
  uchar seed[32]; derive_seed(FS_SEED_TAG_AGENT, a->vault, 32, a->agent, 32, 0, 0, seed);
  require_derived(idx, seed);
  return a;
}

static fs_request_t * request_at(ushort idx, ushort vault_idx, fs_agent_t const *a) {
  fs_request_t *r = (fs_request_t *)load_owned(idx, sizeof(fs_request_t));
  REQUIRE(r->magic == FS_REQ_MAGIC, FS_ERR_NO_PENDING);
  REQUIRE(fs_key_eq(r->vault, addr_of(vault_idx)->key) && fs_key_eq(r->agent, a->agent), FS_ERR_WRONG_VAULT);
  uchar seed[32]; derive_seed(FS_SEED_TAG_REQUEST, r->vault, 32, r->agent, 32, &r->nonce, 8, seed);
  require_derived(idx, seed);
  return r;
}

static void const * proof_after(void const *ix, ulong ix_sz, ulong hdr_sz, uint proof_sz) {
  REQUIRE(ix_sz == hdr_sz + proof_sz, FS_ERR_BAD_INSTRUCTION);
  return proof_sz ? (uchar const *)ix + hdr_sz : 0;
}

/* ------------------------------------------------------------------ instructions */
static void ix_init_vault(void const *d, ulong sz) {
  REQUIRE(sz >= sizeof(fs_ix_init_vault_t), FS_ERR_BAD_INSTRUCTION);
  fs_ix_init_vault_t ix; memcpy(&ix, d, sizeof ix);
  void const *proof = proof_after(d, sz, sizeof ix, ix.proof_sz);
  REQUIRE(tsdk_is_account_authorized_by_idx(ix.owner_idx), FS_ERR_UNAUTHORIZED);
  uchar const *owner = addr_of(ix.owner_idx)->key;
  uchar seed[32]; derive_seed(FS_SEED_TAG_VAULT, owner, 32, &ix.vault_id, 8, 0, 0, seed);
  fs_vault_t *v = (fs_vault_t *)create_account(ix.vault_idx, seed, proof, ix.proof_sz, sizeof(fs_vault_t));
  fs_vault_t n; memset(&n, 0, sizeof n);
  CHECK(fs_vault_init(&n, owner, ix.mint, ix.vault_id, ix.ttl_ns));
  *v = n;
  fs_ev_vault_init_t ev = { FS_EV_VAULT_INIT, {0}, {0}, {0} };
  memcpy(ev.vault, addr_of(ix.vault_idx)->key, 32); memcpy(ev.owner, owner, 32); memcpy(ev.mint, ix.mint, 32);
  emit(&ev, sizeof ev);
}

static void ix_bind_token(void const *d, ulong sz) {
  REQUIRE(sz == sizeof(fs_ix_bind_token_t), FS_ERR_BAD_INSTRUCTION);
  fs_ix_bind_token_t ix; memcpy(&ix, d, sizeof ix);
  fs_vault_t n = *vault_at(ix.vault_idx);
  require_signer(ix.owner_idx, n.owner, FS_ERR_NOT_OWNER);
  fs_token_account_t const *t = load_token_account(ix.token_acct_idx);
  REQUIRE(fs_key_eq(t->mint, n.mint), FS_ERR_WRONG_TOKEN);
  REQUIRE(fs_key_eq(t->owner, addr_of(ix.vault_idx)->key), FS_ERR_WRONG_TOKEN); /* only the vault can authorize it */
  REQUIRE(t->is_frozen == 0, FS_ERR_WRONG_TOKEN);
  if (ix.mint_idx != FS_NO_ACCOUNT) {
    /* KSI-1 (Thru): per the official CLI, freeze/thaw need the mint's freeze authority. A mint without
     * one closes that path; record it so clients and the Proof Lab can report it. */
    REQUIRE(tsdk_is_account_idx_valid(ix.mint_idx) && tsdk_account_exists(ix.mint_idx), FS_ERR_BAD_ACCOUNT);
    tsdk_account_meta_t const *mm = tsdk_get_account_meta(ix.mint_idx);
    REQUIRE(fs_key_eq(mm->owner.key, TOKEN_PROGRAM), FS_ERR_WRONG_TOKEN);
    REQUIRE(mm->data_sz == FS_TOKEN_MINT_SZ, FS_ERR_WRONG_TOKEN);
    REQUIRE(fs_key_eq(addr_of(ix.mint_idx)->key, n.mint), FS_ERR_WRONG_TOKEN);
    uchar const *md = (uchar const *)tsdk_get_account_data_ptr(ix.mint_idx);
    REQUIRE(md[FS_MINT_HAS_FREEZE_OFF] == 0, FS_ERR_MINT_FREEZABLE);
    n.flags = (uint8_t)(n.flags | FS_VAULT_MINT_UNFREEZABLE);
  }
  CHECK(fs_vault_bind_token(&n, addr_of(ix.token_acct_idx)->key));
  *(fs_vault_t *)make_writable(ix.vault_idx) = n;
  fs_ev_token_bound_t ev = { FS_EV_TOKEN_BOUND, {0}, {0}, (uint8_t)((n.flags & FS_VAULT_MINT_UNFREEZABLE) ? 1 : 0) };
  memcpy(ev.vault, addr_of(ix.vault_idx)->key, 32); memcpy(ev.token_account, n.token_account, 32);
  emit(&ev, sizeof ev);
}

static void ix_set_agent(void const *d, ulong sz) {
  REQUIRE(sz >= sizeof(fs_ix_set_agent_t), FS_ERR_BAD_INSTRUCTION);
  fs_ix_set_agent_t ix; memcpy(&ix, d, sizeof ix);
  void const *proof = proof_after(d, sz, sizeof ix, ix.proof_sz);
  fs_vault_t n = *vault_at(ix.vault_idx);
  require_signer(ix.owner_idx, n.owner, FS_ERR_NOT_OWNER);
  uchar const *vaddr = addr_of(ix.vault_idx)->key;
  fs_agent_t *ap; fs_agent_t a;
  if (ix.create) {
    uchar seed[32]; derive_seed(FS_SEED_TAG_AGENT, vaddr, 32, ix.agent, 32, 0, 0, seed);
    ap = (fs_agent_t *)create_account(ix.agent_acct_idx, seed, proof, ix.proof_sz, sizeof(fs_agent_t));
    memset(&a, 0, sizeof a);
  } else {
    REQUIRE(ix.proof_sz == 0, FS_ERR_BAD_INSTRUCTION);
    ap = agent_at(ix.agent_acct_idx, ix.vault_idx);
    a = *ap;
    ap = (fs_agent_t *)make_writable(ix.agent_acct_idx);
  }
  fs_agent_cfg_t cfg = { ix.per_tx, ix.daily, ix.budget, ix.threshold, ix.valid_until_ns };
  CHECK(fs_agent_set(&n, &a, vaddr, ix.agent, &cfg, now_ns(), ix.create != 0));
  *ap = a;
  *(fs_vault_t *)make_writable(ix.vault_idx) = n;
  fs_ev_agent_set_t ev = { FS_EV_AGENT_SET, {0}, {0}, a.per_tx, a.daily, a.budget, a.threshold, a.valid_until_ns, a.epoch };
  memcpy(ev.vault, vaddr, 32); memcpy(ev.agent, a.agent, 32);
  emit(&ev, sizeof ev);
}

static void ix_revoke(void const *d, ulong sz) {
  REQUIRE(sz == sizeof(fs_ix_revoke_t), FS_ERR_BAD_INSTRUCTION);
  fs_ix_revoke_t ix; memcpy(&ix, d, sizeof ix);
  fs_vault_t const *v = vault_at(ix.vault_idx);
  require_signer(ix.owner_idx, v->owner, FS_ERR_NOT_OWNER);
  fs_agent_t a = *agent_at(ix.agent_acct_idx, ix.vault_idx);
  CHECK(fs_agent_revoke(&a));
  *(fs_agent_t *)make_writable(ix.agent_acct_idx) = a;
  fs_ev_agent_revoked_t ev = { FS_EV_AGENT_REVOKED, {0}, {0}, a.epoch };
  memcpy(ev.vault, a.vault, 32); memcpy(ev.agent, a.agent, 32);
  emit(&ev, sizeof ev);
}

static void ix_set_recipient(void const *d, ulong sz) {
  REQUIRE(sz == sizeof(fs_ix_set_recipient_t), FS_ERR_BAD_INSTRUCTION);
  fs_ix_set_recipient_t ix; memcpy(&ix, d, sizeof ix);
  fs_vault_t const *v = vault_at(ix.vault_idx);
  REQUIRE(!(v->flags & FS_VAULT_KILLED), FS_ERR_KILLED);
  require_signer(ix.owner_idx, v->owner, FS_ERR_NOT_OWNER);
  fs_agent_t a = *agent_at(ix.agent_acct_idx, ix.vault_idx);
  CHECK(fs_agent_set_recipient(&a, ix.recipient, ix.allowed != 0));
  *(fs_agent_t *)make_writable(ix.agent_acct_idx) = a;
  fs_ev_recipient_t ev = { FS_EV_RECIPIENT, {0}, {0}, {0}, (uchar)(ix.allowed != 0) };
  memcpy(ev.vault, a.vault, 32); memcpy(ev.agent, a.agent, 32); memcpy(ev.recipient, ix.recipient, 32);
  emit(&ev, sizeof ev);
}

static void ix_request(void const *d, ulong sz) {
  REQUIRE(sz >= sizeof(fs_ix_request_t), FS_ERR_BAD_INSTRUCTION);
  fs_ix_request_t ix; memcpy(&ix, d, sizeof ix);
  void const *proof = proof_after(d, sz, sizeof ix, ix.proof_sz);
  fs_vault_t v = *vault_at(ix.vault_idx);
  fs_agent_t a = *agent_at(ix.agent_acct_idx, ix.vault_idx);
  require_signer(ix.agent_signer_idx, a.agent, FS_ERR_NOT_AGENT);   /* the agent itself, never someone else */
  uchar const *vaddr = addr_of(ix.vault_idx)->key;
  uchar const *recipient = addr_of(ix.recipient_token_idx)->key;
  fs_token_account_t const *rt = load_token_account(ix.recipient_token_idx);
  REQUIRE(fs_key_eq(rt->mint, v.mint), FS_ERR_WRONG_TOKEN);
  fs_request_t r; memset(&r, 0, sizeof r);
  int decision = 0;
  CHECK(fs_request(&v, &a, vaddr, recipient, ix.amount, ix.nonce, now_ns(), &r, &decision));
  *(fs_agent_t *)make_writable(ix.agent_acct_idx) = a;
  *(fs_vault_t *)make_writable(ix.vault_idx) = v;
  if (decision == FS_DECISION_INSTANT) {
    REQUIRE(ix.request_acct_idx == FS_NO_ACCOUNT && ix.proof_sz == 0, FS_ERR_BAD_INSTRUCTION);
    REQUIRE(fs_key_eq(addr_of(ix.vault_token_idx)->key, v.token_account), FS_ERR_WRONG_TOKEN);
    token_transfer(ix.token_program_idx, ix.vault_idx, ix.vault_token_idx, ix.recipient_token_idx, ix.amount);
    fs_ev_paid_t ev = { FS_EV_PAID, {0}, {0}, {0}, ix.amount, ix.nonce, 0 };
    memcpy(ev.vault, vaddr, 32); memcpy(ev.agent, a.agent, 32); memcpy(ev.recipient, recipient, 32);
    emit(&ev, sizeof ev);
  } else {
    uchar seed[32]; derive_seed(FS_SEED_TAG_REQUEST, vaddr, 32, a.agent, 32, &ix.nonce, 8, seed);
    fs_request_t *rp = (fs_request_t *)create_account(ix.request_acct_idx, seed, proof, ix.proof_sz, sizeof(fs_request_t));
    *rp = r;
    fs_ev_requested_t ev = { FS_EV_REQUESTED, {0}, {0}, {0}, r.amount, r.nonce, r.expires_ns };
    memcpy(ev.vault, vaddr, 32); memcpy(ev.agent, a.agent, 32); memcpy(ev.recipient, recipient, 32);
    emit(&ev, sizeof ev);
  }
}

static void ix_approve(void const *d, ulong sz) {
  REQUIRE(sz == sizeof(fs_ix_approve_t), FS_ERR_BAD_INSTRUCTION);
  fs_ix_approve_t ix; memcpy(&ix, d, sizeof ix);
  fs_vault_t v = *vault_at(ix.vault_idx);
  require_signer(ix.owner_idx, v.owner, FS_ERR_NOT_OWNER);
  fs_agent_t a = *agent_at(ix.agent_acct_idx, ix.vault_idx);
  fs_request_t r = *request_at(ix.request_acct_idx, ix.vault_idx, &a);
  REQUIRE(fs_key_eq(ix.approval.vault, addr_of(ix.vault_idx)->key), FS_ERR_APPROVAL_MISMATCH);
  REQUIRE(fs_key_eq(addr_of(ix.recipient_token_idx)->key, r.recipient), FS_ERR_APPROVAL_MISMATCH);
  fs_token_account_t const *rt = load_token_account(ix.recipient_token_idx);
  REQUIRE(fs_key_eq(rt->mint, v.mint), FS_ERR_WRONG_TOKEN);
  CHECK(fs_approve(&v, &a, &r, &ix.approval, now_ns()));
  *(fs_agent_t *)make_writable(ix.agent_acct_idx) = a;
  *(fs_request_t *)make_writable(ix.request_acct_idx) = r;
  *(fs_vault_t *)make_writable(ix.vault_idx) = v;
  REQUIRE(fs_key_eq(addr_of(ix.vault_token_idx)->key, v.token_account), FS_ERR_WRONG_TOKEN);
  token_transfer(ix.token_program_idx, ix.vault_idx, ix.vault_token_idx, ix.recipient_token_idx, r.amount);
  fs_ev_paid_t ev = { FS_EV_PAID, {0}, {0}, {0}, r.amount, r.nonce, 1 };
  memcpy(ev.vault, r.vault, 32); memcpy(ev.agent, r.agent, 32); memcpy(ev.recipient, r.recipient, 32);
  emit(&ev, sizeof ev);
}

static void ix_reject(void const *d, ulong sz) {
  REQUIRE(sz == sizeof(fs_ix_reject_t), FS_ERR_BAD_INSTRUCTION);
  fs_ix_reject_t ix; memcpy(&ix, d, sizeof ix);
  fs_vault_t const *v = vault_at(ix.vault_idx);
  fs_agent_t a = *agent_at(ix.agent_acct_idx, ix.vault_idx);
  fs_request_t r = *request_at(ix.request_acct_idx, ix.vault_idx, &a);
  /* owner or the agent itself may reject */
  uchar const *actor = addr_of(ix.actor_idx)->key;
  REQUIRE(fs_key_eq(actor, v->owner) || fs_key_eq(actor, a.agent), FS_ERR_UNAUTHORIZED);
  REQUIRE(tsdk_is_account_authorized_by_idx(ix.actor_idx), FS_ERR_UNAUTHORIZED);
  CHECK(fs_reject(&a, &r));
  *(fs_agent_t *)make_writable(ix.agent_acct_idx) = a;
  *(fs_request_t *)make_writable(ix.request_acct_idx) = r;
  fs_ev_closed_t ev = { FS_EV_REJECTED, {0}, {0}, r.nonce };
  memcpy(ev.vault, r.vault, 32); memcpy(ev.agent, r.agent, 32);
  emit(&ev, sizeof ev);
}

static void ix_expire(void const *d, ulong sz) {
  REQUIRE(sz == sizeof(fs_ix_expire_t), FS_ERR_BAD_INSTRUCTION);
  fs_ix_expire_t ix; memcpy(&ix, d, sizeof ix);
  (void)vault_at(ix.vault_idx);                       /* anyone may close an expired or stale request */
  fs_agent_t a = *agent_at(ix.agent_acct_idx, ix.vault_idx);
  fs_request_t r = *request_at(ix.request_acct_idx, ix.vault_idx, &a);
  CHECK(fs_expire(&a, &r, now_ns()));
  *(fs_agent_t *)make_writable(ix.agent_acct_idx) = a;
  *(fs_request_t *)make_writable(ix.request_acct_idx) = r;
  fs_ev_closed_t ev = { (uchar)(r.status == FS_REQ_INVALIDATED ? FS_EV_INVALIDATED : FS_EV_EXPIRED), {0}, {0}, r.nonce };
  memcpy(ev.vault, r.vault, 32); memcpy(ev.agent, r.agent, 32);
  emit(&ev, sizeof ev);
}

static void ix_set_paused(void const *d, ulong sz) {
  REQUIRE(sz == sizeof(fs_ix_set_paused_t), FS_ERR_BAD_INSTRUCTION);
  fs_ix_set_paused_t ix; memcpy(&ix, d, sizeof ix);
  fs_vault_t v = *vault_at(ix.vault_idx);
  require_signer(ix.owner_idx, v.owner, FS_ERR_NOT_OWNER);
  CHECK(fs_set_paused(&v, ix.paused != 0));
  *(fs_vault_t *)make_writable(ix.vault_idx) = v;
  fs_ev_flag_t ev = { FS_EV_PAUSED, {0}, (uchar)(ix.paused != 0) };
  memcpy(ev.vault, addr_of(ix.vault_idx)->key, 32);
  emit(&ev, sizeof ev);
}

static void ix_kill(void const *d, ulong sz) {
  REQUIRE(sz == sizeof(fs_ix_kill_t), FS_ERR_BAD_INSTRUCTION);
  fs_ix_kill_t ix; memcpy(&ix, d, sizeof ix);
  fs_vault_t v = *vault_at(ix.vault_idx);
  require_signer(ix.owner_idx, v.owner, FS_ERR_NOT_OWNER);
  CHECK(fs_kill(&v));
  *(fs_vault_t *)make_writable(ix.vault_idx) = v;
  fs_ev_flag_t ev = { FS_EV_KILLED, {0}, 1 };
  memcpy(ev.vault, addr_of(ix.vault_idx)->key, 32);
  emit(&ev, sizeof ev);
}

/* Owner withdrawal (also after kill). Does not touch agent accounting; R-4 (a withdrawal can leave
   a pending request unfundable) is accepted and documented. */
static void ix_withdraw(void const *d, ulong sz) {
  REQUIRE(sz == sizeof(fs_ix_withdraw_t), FS_ERR_BAD_INSTRUCTION);
  fs_ix_withdraw_t ix; memcpy(&ix, d, sizeof ix);
  fs_vault_t const *v = vault_at(ix.vault_idx);
  require_signer(ix.owner_idx, v->owner, FS_ERR_NOT_OWNER);
  REQUIRE(ix.amount > 0, FS_ERR_ZERO_AMOUNT);
  REQUIRE(fs_key_eq(addr_of(ix.vault_token_idx)->key, v->token_account), FS_ERR_WRONG_TOKEN);
  fs_token_account_t const *dt = load_token_account(ix.dest_token_idx);
  REQUIRE(fs_key_eq(dt->mint, v->mint), FS_ERR_WRONG_TOKEN);
  token_transfer(ix.token_program_idx, ix.vault_idx, ix.vault_token_idx, ix.dest_token_idx, ix.amount);
  fs_ev_withdrawn_t ev = { FS_EV_WITHDRAWN, {0}, {0}, ix.amount };
  memcpy(ev.vault, addr_of(ix.vault_idx)->key, 32); memcpy(ev.dest, addr_of(ix.dest_token_idx)->key, 32);
  emit(&ev, sizeof ev);
}

/* ------------------------------------------------------------------ entrypoint */
TSDK_ENTRYPOINT_FN void
start(void const *instruction_data, ulong instruction_data_sz) {
  REQUIRE(!tsdk_is_program_reentrant(), FS_ERR_REENTRANT);
  REQUIRE(instruction_data_sz >= 1, FS_ERR_BAD_INSTRUCTION);
  uchar op = *(uchar const *)instruction_data;
  switch (op) {
    case FS_OP_INIT_VAULT:    ix_init_vault(instruction_data, instruction_data_sz); break;
    case FS_OP_BIND_TOKEN:    ix_bind_token(instruction_data, instruction_data_sz); break;
    case FS_OP_SET_AGENT:     ix_set_agent(instruction_data, instruction_data_sz); break;
    case FS_OP_REVOKE:        ix_revoke(instruction_data, instruction_data_sz); break;
    case FS_OP_SET_RECIPIENT: ix_set_recipient(instruction_data, instruction_data_sz); break;
    case FS_OP_REQUEST:       ix_request(instruction_data, instruction_data_sz); break;
    case FS_OP_APPROVE:       ix_approve(instruction_data, instruction_data_sz); break;
    case FS_OP_REJECT:        ix_reject(instruction_data, instruction_data_sz); break;
    case FS_OP_EXPIRE:        ix_expire(instruction_data, instruction_data_sz); break;
    case FS_OP_SET_PAUSED:    ix_set_paused(instruction_data, instruction_data_sz); break;
    case FS_OP_KILL:          ix_kill(instruction_data, instruction_data_sz); break;
    case FS_OP_WITHDRAW:      ix_withdraw(instruction_data, instruction_data_sz); break;
    default:                  tsdk_revert(FS_ERR_BAD_INSTRUCTION);
  }
  tsdk_return(0UL);
}
