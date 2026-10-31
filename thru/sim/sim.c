/* LOCAL SIMULATION of the Thru SDK surface used by thru/program/flowstate.c — HOST ONLY.
 *
 * THIS IS NOT THE THRU VM. It re-implements, on the host, the documented behaviour of:
 *   - transaction account indexing (0 = fee payer, 1 = program, then read-write, then read-only)
 *   - authorization: tsdk_is_account_authorized_by_idx / _by_pubkey (fee payer; current program;
 *     accounts a calling program listed in its tsys_invoke auth list) — copied from tn_sdk.c logic
 *   - tsys_invoke auth validation (auth entries must be owned by the caller) — from tn_sdk_syscall.c
 *   - program-defined account creation (address = sha256(program || 0 || seed)); state proofs are
 *     NOT verified here
 *   - revert = all-or-nothing rollback of every account touched by the transaction
 *   - a MODEL of the official token program's `transfer` (ABI thru.program.token v0.1.0): the
 *     source token account's `owner` must be authorized, same mint, not frozen, enough balance.
 *     The real token program's source is not public; this model is an assumption to be verified.
 * Everything produced with this file is labelled LOCAL SIMULATION. */
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <thru-sdk/c/tn_sdk.h>
#include <thru-sdk/c/tn_sdk_syscall.h>
#include <thru-sdk/c/tn_sdk_sha256.h>
#include "../program/flowstate_abi.h"

#define SIM_MAX_ACCOUNTS 1024
#define SIM_MAX_DATA     1024
#define SIM_MAX_TXN_ACCS 64
#define SIM_MAX_EVENTS   64
#define SIM_MAX_EV_SZ    512

typedef struct {
  int exists;
  uchar addr[32];
  tsdk_account_meta_t meta;
  uchar data[SIM_MAX_DATA];
} sim_account_t;

static sim_account_t g_accounts[SIM_MAX_ACCOUNTS];
static int g_account_cnt;
static uchar g_flowstate_program[32];
static uchar const g_token_program[32] = TSDK_TOKEN_PROGRAM_ADDR_BYTES;
static tsdk_block_ctx_t g_block;

/* current transaction */
static uchar g_txn_buf[sizeof(tsdk_txn_hdr_v1_t) + 32 * SIM_MAX_TXN_ACCS];
static sim_account_t *g_tx_acc[SIM_MAX_TXN_ACCS];
static int g_tx_cnt;
static int g_rw_cnt;
static sim_account_t g_snapshot[SIM_MAX_ACCOUNTS];
static int g_snapshot_cnt;

/* call frames: depth 1 = top-level program */
typedef struct { ushort program_idx; ushort auth[8]; ushort auth_cnt; } sim_frame_t;
static sim_frame_t g_frames[8];
static int g_depth;

static jmp_buf g_exit;
static ulong g_exit_code;
static int g_reverted;

typedef struct { uchar program[32]; ulong sz; uchar data[SIM_MAX_EV_SZ]; } sim_event_t;
static sim_event_t g_events[SIM_MAX_EVENTS];
static int g_event_cnt;

/* ------------------------------------------------------------------ chain registry */
static sim_account_t * find_account(uchar const addr[32]) {
  for (int i = 0; i < g_account_cnt; i++) if (!memcmp(g_accounts[i].addr, addr, 32)) return &g_accounts[i];
  return NULL;
}
static sim_account_t * get_or_add(uchar const addr[32]) {
  sim_account_t *a = find_account(addr);
  if (a) return a;
  if (g_account_cnt >= SIM_MAX_ACCOUNTS) return NULL;
  a = &g_accounts[g_account_cnt++];
  memset(a, 0, sizeof *a);
  memcpy(a->addr, addr, 32);
  return a;
}

/* ------------------------------------------------------------------ SDK surface (host) */
tsdk_txn_t const * tsdk_get_txn(void) { return (tsdk_txn_t const *)(void const *)g_txn_buf; }
tsdk_block_ctx_t const * tsdk_get_current_block_ctx(void) { return &g_block; }
tsdk_block_ctx_t const * tsdk_get_past_block_ctx(ulong n) { (void)n; return &g_block; }
int tsdk_is_account_idx_valid(ushort idx) { return idx < g_tx_cnt; }
tsdk_account_meta_t const * tsdk_get_account_meta(ushort idx) { return &g_tx_acc[idx]->meta; }
void * tsdk_get_account_data_ptr(ushort idx) { return g_tx_acc[idx]->data; }
int tsdk_account_exists(ushort idx) { return g_tx_acc[idx]->exists; }
ushort tsdk_get_current_program_acc_idx(void) { return g_frames[g_depth].program_idx; }
tn_pubkey_t const * tsdk_get_current_program_acc_addr(void) {
  return (tn_pubkey_t const *)(void const *)g_tx_acc[g_frames[g_depth].program_idx]->addr;
}
ushort tsdk_get_caller_program_acc_idx(void) { return g_depth < 2 ? TSDK_CALLER_PROGRAM_NONE : g_frames[g_depth - 1].program_idx; }

int tsdk_is_account_authorized_by_idx(ushort idx) {
  if (idx == 0) return 1;                                     /* fee payer */
  if (g_frames[g_depth].program_idx == idx) return 1;          /* current program */
  for (int d = g_depth - 1; d >= 1; d--)                       /* parent frames' auth lists */
    for (int i = 0; i < g_frames[d].auth_cnt; i++) if (g_frames[d].auth[i] == idx) return 1;
  return 0;
}
int tsdk_is_account_authorized_by_pubkey(tn_pubkey_t const *pk) {
  if (!memcmp(pk->key, g_tx_acc[0]->addr, 32)) return 1;
  if (!memcmp(pk->key, g_tx_acc[g_frames[g_depth].program_idx]->addr, 32)) return 1;
  for (int d = g_depth - 1; d >= 1; d--)
    for (int i = 0; i < g_frames[d].auth_cnt; i++)
      if (!memcmp(pk->key, g_tx_acc[g_frames[d].auth[i]]->addr, 32)) return 1;
  return 0;
}
int tsdk_is_account_owned_by_current_program(ushort idx) {
  return !memcmp(g_tx_acc[idx]->meta.owner.key, g_tx_acc[g_frames[g_depth].program_idx]->addr, 32);
}
int tsdk_is_program_reentrant(void) {
  for (int d = g_depth - 1; d >= 1; d--) if (g_frames[d].program_idx == g_frames[g_depth].program_idx) return 1;
  return 0;
}
tn_pubkey_t * tsdk_create_program_defined_account_address(tn_pubkey_t const *owner, uchar eph, uchar const seed[32], tn_pubkey_t *out) {
  tsdk_sha256_t sha; tsdk_sha256_init(&sha);
  tsdk_sha256_append(&sha, owner, 32); tsdk_sha256_append(&sha, &eph, 1); tsdk_sha256_append(&sha, seed, 32);
  tsdk_sha256_fini(&sha, out);
  return out;
}

static int idx_writable(ushort idx) { return idx == 0 || (idx >= 2 && idx < 2 + g_rw_cnt); }
/* Official rule (C SDK reference, Syscalls): tsys_set_account_data_writable "must be called before writing
 * to tsdk_get_account_data_ptr(...)", and tsys_account_resize requires "the account must already be
 * writable". The simulation tracks it per transaction account and enforces both. */
static uchar g_wset[SIM_MAX_TXN_ACCS];

ulong tsys_set_account_data_writable(ulong idx) {
  if (idx >= (ulong)g_tx_cnt || !idx_writable((ushort)idx) || !g_tx_acc[idx]->exists) return 1;
  if (!tsdk_is_account_owned_by_current_program((ushort)idx)) return 2;
  g_wset[idx] = 1;
  return TSDK_SUCCESS;
}
ulong tsys_account_create(ulong idx, uchar const seed[TN_SEED_SIZE], void const *proof, ulong proof_sz) {
  (void)proof; (void)proof_sz;            /* state proofs are not simulated */
  if (idx >= (ulong)g_tx_cnt || !idx_writable((ushort)idx) || g_tx_acc[idx]->exists) return 1;
  tn_pubkey_t expect;
  tsdk_create_program_defined_account_address(tsdk_get_current_program_acc_addr(), 0, seed, &expect);
  if (memcmp(expect.key, g_tx_acc[idx]->addr, 32)) return 2;
  sim_account_t *a = g_tx_acc[idx];
  a->exists = 1; memset(&a->meta, 0, sizeof a->meta); memset(a->data, 0, sizeof a->data);
  a->meta.version = 1; a->meta.flags = TSDK_ACCOUNT_FLAG_NEW;
  memcpy(a->meta.owner.key, tsdk_get_current_program_acc_addr()->key, 32);
  return TSDK_SUCCESS;
}
ulong tsys_account_resize(ulong idx, ulong sz) {
  if (idx >= (ulong)g_tx_cnt || sz > SIM_MAX_DATA || !tsdk_is_account_owned_by_current_program((ushort)idx)) return 1;
  if (!g_wset[idx]) return 3;                         /* not set writable first */
  g_tx_acc[idx]->meta.data_sz = (uint)sz;
  return TSDK_SUCCESS;
}
ulong tsys_emit_event(void const *d, ulong sz) {
  if (g_event_cnt < SIM_MAX_EVENTS && sz <= SIM_MAX_EV_SZ) {
    sim_event_t *e = &g_events[g_event_cnt++];
    memcpy(e->program, tsdk_get_current_program_acc_addr()->key, 32); e->sz = sz; memcpy(e->data, d, sz);
  }
  return TSDK_SUCCESS;
}
ulong tsys_log(void const *d, ulong sz) { (void)d; (void)sz; return TSDK_SUCCESS; }
void tsdk_revert(ulong code) { g_exit_code = code; g_reverted = 1; longjmp(g_exit, 1); }
void tsdk_return(ulong code) { g_exit_code = code; g_reverted = 0; longjmp(g_exit, 1); }
void tsdk_printf(char const *fmt, ...) { (void)fmt; }

/* ---------- MODEL of the official token program (transfer only) ---------- */
#define TOKEN_ERR_BAD_IX 0x2001
#define TOKEN_ERR_ACCOUNT 0x2002
#define TOKEN_ERR_MINT 0x2003
#define TOKEN_ERR_FROZEN 0x2004
#define TOKEN_ERR_FUNDS 0x2005
#define TOKEN_ERR_AUTH 0x2006

static ulong token_program_run(uchar const *d, ulong sz) {
  if (sz != sizeof(fs_token_transfer_ix_t) || d[0] != FS_TOKEN_IX_TRANSFER) return TOKEN_ERR_BAD_IX;
  fs_token_transfer_ix_t ix; memcpy(&ix, d, sizeof ix);
  if (!tsdk_is_account_idx_valid(ix.source_idx) || !tsdk_is_account_idx_valid(ix.dest_idx)) return TOKEN_ERR_ACCOUNT;
  sim_account_t *s = g_tx_acc[ix.source_idx], *t = g_tx_acc[ix.dest_idx];
  if (!s->exists || !t->exists || memcmp(s->meta.owner.key, g_token_program, 32) || memcmp(t->meta.owner.key, g_token_program, 32)) return TOKEN_ERR_ACCOUNT;
  if (s->meta.data_sz != FS_TOKEN_ACCOUNT_SZ || t->meta.data_sz != FS_TOKEN_ACCOUNT_SZ) return TOKEN_ERR_ACCOUNT;
  if (!idx_writable(ix.source_idx) || !idx_writable(ix.dest_idx)) return TOKEN_ERR_ACCOUNT;
  fs_token_account_t src, dst; memcpy(&src, s->data, sizeof src); memcpy(&dst, t->data, sizeof dst);
  if (memcmp(src.mint, dst.mint, 32)) return TOKEN_ERR_MINT;
  if (src.is_frozen || dst.is_frozen) return TOKEN_ERR_FROZEN;
  if (!tsdk_is_account_authorized_by_pubkey((tn_pubkey_t const *)(void const *)src.owner)) return TOKEN_ERR_AUTH;
  if (src.amount < ix.amount) return TOKEN_ERR_FUNDS;
  if (ix.source_idx != ix.dest_idx) {
    src.amount -= ix.amount; dst.amount += ix.amount;
    memcpy(s->data, &src, sizeof src); memcpy(t->data, &dst, sizeof dst);
  }
  return 0;
}

ulong tsys_invoke(void const *instr, ulong instr_sz, ushort program_idx, tsdk_invoke_auth_t const *auth, ulong *err) {
  if (auth) {                                        /* same validation as the SDK wrapper */
    if (auth->magic != TSDK_INVOKE_AUTH_MAGIC) tsdk_revert(0xA001);
    for (ushort i = 0; i < auth->auth_cnt; i++) {
      if (!tsdk_is_account_idx_valid(auth->acc_idxs[i])) tsdk_revert(0xA002);
      if (!tsdk_is_account_owned_by_current_program(auth->acc_idxs[i])) tsdk_revert(0xA003);
    }
  }
  if (!tsdk_is_account_idx_valid(program_idx) || g_depth >= 7) { *err = 1; return 1; }
  sim_frame_t *caller = &g_frames[g_depth];
  caller->auth_cnt = 0;
  if (auth) for (ushort i = 0; i < auth->auth_cnt && i < 8; i++) caller->auth[caller->auth_cnt++] = auth->acc_idxs[i];
  g_depth++; g_frames[g_depth].program_idx = program_idx; g_frames[g_depth].auth_cnt = 0;
  ulong rc;
  if (!memcmp(g_tx_acc[program_idx]->addr, g_token_program, 32)) rc = token_program_run((uchar const *)instr, instr_sz);
  else if (g_tx_acc[program_idx]->exists && (g_tx_acc[program_idx]->meta.flags & TSDK_ACCOUNT_FLAG_PROGRAM))
    rc = 0;                                          /* any other executable behaves like the official no-op program:
                                                        it returns success and moves nothing (UNTO-2328 attack model) */
  else rc = 0xA004;                                  /* not an executable */
  g_depth--; caller->auth_cnt = 0;
  *err = rc;
  return rc ? 1 : TSDK_SUCCESS;
}

/* the program under test */
void start(void const *instruction_data, ulong instruction_data_sz);

/* ------------------------------------------------------------------ API for tests (ctypes) */
void sim_reset(uchar const flowstate_program[32]) {
  memset(g_accounts, 0, sizeof g_accounts); g_account_cnt = 0; g_event_cnt = 0;
  memcpy(g_flowstate_program, flowstate_program, 32);
  memset(&g_block, 0, sizeof g_block);
  sim_account_t *p = get_or_add(flowstate_program); p->exists = 1; p->meta.flags = TSDK_ACCOUNT_FLAG_PROGRAM;
  sim_account_t *t = get_or_add(g_token_program); t->exists = 1; t->meta.flags = TSDK_ACCOUNT_FLAG_PROGRAM;
}
void sim_token_program(uchar out[32]) { memcpy(out, g_token_program, 32); }
void sim_set_clock(ulong slot, ulong block_time_ns) { g_block.slot = slot; g_block.block_time = block_time_ns; }

/* Test setup only (stands in for token-program mint/initialize instructions and wallet creation). */
int sim_put_account(uchar const addr[32], uchar const owner[32], uchar const *data, ulong sz) {
  if (sz > SIM_MAX_DATA) return 1;
  sim_account_t *a = get_or_add(addr); if (!a) return 2;
  a->exists = 1; memset(&a->meta, 0, sizeof a->meta); a->meta.version = 1;
  memcpy(a->meta.owner.key, owner, 32); a->meta.data_sz = (uint)sz;
  memset(a->data, 0, sizeof a->data); if (sz) memcpy(a->data, data, sz);
  return 0;
}
/* An executable account that is not the token program (behaves like a no-op program when invoked). */
int sim_put_program(uchar const addr[32]) {
  sim_account_t *a = get_or_add(addr); if (!a) return 2;
  a->exists = 1; memset(&a->meta, 0, sizeof a->meta); a->meta.version = 1; a->meta.flags = TSDK_ACCOUNT_FLAG_PROGRAM;
  return 0;
}
int sim_get_account(uchar const addr[32], uchar owner_out[32], uchar *data_out, ulong cap, ulong *sz_out) {
  sim_account_t *a = find_account(addr);
  if (!a || !a->exists) return 0;
  memcpy(owner_out, a->meta.owner.key, 32);
  ulong n = a->meta.data_sz < cap ? a->meta.data_sz : cap;
  memcpy(data_out, a->data, n); *sz_out = a->meta.data_sz;
  return 1;
}

/* Execute one transaction: accounts = [fee_payer, program, rw..., ro...]. Returns 0 on success or
   the revert code. On revert, every account is restored and no event is kept. */
ulong sim_exec(uchar const program[32], uchar const fee_payer[32], uchar const *rw, int rw_cnt,
               uchar const *ro, int ro_cnt, uchar const *instr, ulong instr_sz) {
  g_event_cnt = 0;
  if (2 + rw_cnt + ro_cnt > SIM_MAX_TXN_ACCS) return 0xB001;
  memset(g_wset, 0, sizeof g_wset);
  memcpy(g_snapshot, g_accounts, sizeof g_accounts); g_snapshot_cnt = g_account_cnt;
  memset(g_txn_buf, 0, sizeof g_txn_buf);
  tsdk_txn_hdr_v1_t *h = (tsdk_txn_hdr_v1_t *)(void *)g_txn_buf;
  h->transaction_version = 1; h->readwrite_accounts_cnt = (ushort)rw_cnt; h->readonly_accounts_cnt = (ushort)ro_cnt;
  h->instr_data_sz = (ushort)instr_sz; h->chain_id = 1;
  memcpy(h->fee_payer_pubkey.key, fee_payer, 32); memcpy(h->program_pubkey.key, program, 32);
  uchar *keys = g_txn_buf + sizeof(tsdk_txn_hdr_v1_t);
  for (int i = 0; i < rw_cnt; i++) memcpy(keys + 32 * i, rw + 32 * i, 32);
  for (int i = 0; i < ro_cnt; i++) memcpy(keys + 32 * (rw_cnt + i), ro + 32 * i, 32);
  g_tx_cnt = 2 + rw_cnt + ro_cnt; g_rw_cnt = rw_cnt;
  /* Official transaction rule (docs: Transactions > Account List Verification): no duplicate accounts
   * anywhere in the transaction; read-write and read-only lists each sorted ascending. A transaction that
   * breaks it is invalid and never executes. */
  {
    tn_pubkey_t const *ad = tsdk_txn_get_acct_addrs(tsdk_get_txn());
    for (int i = 0; i < g_tx_cnt; i++)
      for (int j = i + 1; j < g_tx_cnt; j++)
        if (!memcmp(ad[i].key, ad[j].key, 32)) return 0xB006;           /* duplicate account */
    for (int i = 1; i < rw_cnt; i++) if (memcmp(rw + 32 * (i - 1), rw + 32 * i, 32) >= 0) return 0xB007; /* rw unsorted */
    for (int i = 1; i < ro_cnt; i++) if (memcmp(ro + 32 * (i - 1), ro + 32 * i, 32) >= 0) return 0xB008; /* ro unsorted */
  }
  tn_pubkey_t const *addrs = tsdk_txn_get_acct_addrs(tsdk_get_txn());
  for (int i = 0; i < g_tx_cnt; i++) {
    g_tx_acc[i] = get_or_add(addrs[i].key);
    if (!g_tx_acc[i]) { memcpy(g_accounts, g_snapshot, sizeof g_accounts); g_account_cnt = g_snapshot_cnt; return 0xB002; }
  }
  if (!g_tx_acc[1]->exists || !(g_tx_acc[1]->meta.flags & TSDK_ACCOUNT_FLAG_PROGRAM)) return 0xB003;
  g_depth = 1; g_frames[1].program_idx = 1; g_frames[1].auth_cnt = 0;
  g_reverted = 0; g_exit_code = 0;
  if (!setjmp(g_exit)) {
    if (!memcmp(program, g_flowstate_program, 32)) start(instr, instr_sz);
    else if (!memcmp(program, g_token_program, 32)) { ulong rc = token_program_run(instr, instr_sz); if (rc) tsdk_revert(rc); tsdk_return(0); }
    else tsdk_revert(0xB004);
  }
  if (!g_reverted && !memcmp(program, g_flowstate_program, 32)) {
    /* any program-owned account whose data or size changed must have been set writable (0xB009) */
    for (int i = 2; i < g_tx_cnt; i++) {
      sim_account_t *a = g_tx_acc[i];
      if (memcmp(a->meta.owner.key, g_flowstate_program, 32) || g_wset[i]) continue;
      sim_account_t const *before = 0;
      for (int k = 0; k < g_snapshot_cnt; k++) if (!memcmp(g_snapshot[k].addr, a->addr, 32)) { before = &g_snapshot[k]; break; }
      int changed = !before || before->exists != a->exists || before->meta.data_sz != a->meta.data_sz ||
                    memcmp(before->data, a->data, a->meta.data_sz);
      if (changed) { g_reverted = 1; g_exit_code = 0xB009; break; }
    }
  }
  if (g_reverted) {
    memcpy(g_accounts, g_snapshot, sizeof g_accounts); g_account_cnt = g_snapshot_cnt; g_event_cnt = 0;
    return g_exit_code ? g_exit_code : 0xB005;
  }
  for (int i = 0; i < g_account_cnt; i++) g_accounts[i].meta.flags = (uchar)(g_accounts[i].meta.flags & ~TSDK_ACCOUNT_FLAG_NEW);
  return 0;
}

int sim_event_count(void) { return g_event_cnt; }
ulong sim_event(int i, uchar program_out[32], uchar *out, ulong cap) {
  if (i < 0 || i >= g_event_cnt) return 0;
  memcpy(program_out, g_events[i].program, 32);
  ulong n = g_events[i].sz < cap ? g_events[i].sz : cap; memcpy(out, g_events[i].data, n);
  return g_events[i].sz;
}
