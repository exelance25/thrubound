/* Flowstate on Thru — pure policy core. See flowstate_core.h.
 * Rule: validate on local copies, commit with a single structure assignment at the end. */
#include "flowstate_core.h"

#define FS_OP_APPROVE 6   /* must match flowstate_abi.h */

static void fs_copy(void *d, void const *s, unsigned long n) {
  unsigned char *dd = (unsigned char *)d; unsigned char const *ss = (unsigned char const *)s;
  for (unsigned long i = 0; i < n; i++) dd[i] = ss[i];
}
static void fs_zero(void *d, unsigned long n) { unsigned char *dd = (unsigned char *)d; for (unsigned long i = 0; i < n; i++) dd[i] = 0; }

int fs_key_eq(uint8_t const a[FS_KEY_SZ], uint8_t const b[FS_KEY_SZ]) {
  uint8_t x = 0; for (int i = 0; i < FS_KEY_SZ; i++) x = (uint8_t)(x | (a[i] ^ b[i])); return x == 0;
}
int fs_key_is_zero(uint8_t const a[FS_KEY_SZ]) {
  uint8_t x = 0; for (int i = 0; i < FS_KEY_SZ; i++) x = (uint8_t)(x | a[i]); return x == 0;
}
uint64_t fs_utc_day(uint64_t now_ns) { return now_ns / FS_NS_PER_DAY; }

/* checked arithmetic */
static int add_ok(uint64_t a, uint64_t b, uint64_t *out) { if (a > UINT64_MAX - b) return 0; *out = a + b; return 1; }

/* ------------------------------------------------------------------ vault */
int fs_vault_init(fs_vault_t *v, uint8_t const owner[FS_KEY_SZ], uint8_t const mint[FS_KEY_SZ],
                  uint64_t vault_id, uint64_t ttl_ns) {
  if (v->magic != 0) return FS_ERR_ALREADY_INITIALIZED;
  if (fs_key_is_zero(owner) || fs_key_is_zero(mint)) return FS_ERR_BAD_INSTRUCTION;
  if (ttl_ns < FS_TTL_MIN_NS || ttl_ns > FS_TTL_MAX_NS) return FS_ERR_INVALID_CONFIG;
  fs_vault_t n; fs_zero(&n, sizeof n);
  n.magic = FS_VAULT_MAGIC; n.version = FS_LAYOUT_VERSION;
  fs_copy(n.owner, owner, FS_KEY_SZ); fs_copy(n.mint, mint, FS_KEY_SZ);
  n.vault_id = vault_id; n.approval_ttl_ns = ttl_ns;
  *v = n;
  return FS_OK;
}

int fs_vault_check_live(fs_vault_t const *v) {
  if (v->magic != FS_VAULT_MAGIC || v->version != FS_LAYOUT_VERSION) return FS_ERR_NOT_INITIALIZED;
  if (v->flags & FS_VAULT_KILLED) return FS_ERR_KILLED;
  if (v->flags & FS_VAULT_PAUSED) return FS_ERR_PAUSED;
  if (fs_key_is_zero(v->token_account)) return FS_ERR_TOKEN_NOT_BOUND;
  return FS_OK;
}

int fs_vault_bind_token(fs_vault_t *v, uint8_t const token_account[FS_KEY_SZ]) {
  if (v->magic != FS_VAULT_MAGIC) return FS_ERR_NOT_INITIALIZED;
  if (v->flags & FS_VAULT_KILLED) return FS_ERR_KILLED;
  if (!fs_key_is_zero(v->token_account)) return FS_ERR_ALREADY_INITIALIZED; /* bound once, never swapped */
  if (fs_key_is_zero(token_account)) return FS_ERR_BAD_ACCOUNT;
  fs_copy(v->token_account, token_account, FS_KEY_SZ);
  return FS_OK;
}

int fs_set_paused(fs_vault_t *v, int paused) {
  if (v->magic != FS_VAULT_MAGIC) return FS_ERR_NOT_INITIALIZED;
  if (v->flags & FS_VAULT_KILLED) return FS_ERR_KILLED;   /* kill is irreversible: no unpause */
  v->flags = (uint8_t)(paused ? (v->flags | FS_VAULT_PAUSED) : (v->flags & ~FS_VAULT_PAUSED));
  return FS_OK;
}

int fs_kill(fs_vault_t *v) {
  if (v->magic != FS_VAULT_MAGIC) return FS_ERR_NOT_INITIALIZED;
  if (v->flags & FS_VAULT_KILLED) return FS_ERR_KILLED;
  v->flags = (uint8_t)(v->flags | FS_VAULT_KILLED | FS_VAULT_PAUSED);
  return FS_OK;
}

/* ------------------------------------------------------------------ agents */
int fs_agent_set(fs_vault_t *v, fs_agent_t *a, uint8_t const vault_addr[FS_KEY_SZ],
                 uint8_t const agent_key[FS_KEY_SZ], fs_agent_cfg_t const *cfg, uint64_t now_ns, int is_new) {
  if (v->magic != FS_VAULT_MAGIC) return FS_ERR_NOT_INITIALIZED;
  if (v->flags & FS_VAULT_KILLED) return FS_ERR_KILLED;
  if (fs_key_is_zero(agent_key) || fs_key_eq(agent_key, v->owner)) return FS_ERR_INVALID_CONFIG; /* agent never the owner */
  if (cfg->per_tx == 0 || cfg->daily == 0 || cfg->budget == 0) return FS_ERR_INVALID_CONFIG;
  if (cfg->per_tx > cfg->daily || cfg->daily > cfg->budget) return FS_ERR_INVALID_CONFIG;
  if (cfg->threshold > cfg->per_tx) return FS_ERR_INVALID_CONFIG;
  if (cfg->valid_until_ns <= now_ns) return FS_ERR_INVALID_CONFIG;
  fs_agent_t n = *a;
  if (is_new) {
    if (a->magic != 0) return FS_ERR_ALREADY_INITIALIZED;
    uint32_t cnt = v->agent_count + 1u; if (cnt == 0) return FS_ERR_OVERFLOW;
    fs_zero(&n, sizeof n);
    n.magic = FS_AGENT_MAGIC; n.version = FS_LAYOUT_VERSION;
    fs_copy(n.vault, vault_addr, FS_KEY_SZ); fs_copy(n.agent, agent_key, FS_KEY_SZ);
    v->agent_count = cnt;
  } else {
    if (a->magic != FS_AGENT_MAGIC) return FS_ERR_UNKNOWN_AGENT;
    if (!fs_key_eq(a->vault, vault_addr)) return FS_ERR_WRONG_VAULT;
    if (!fs_key_eq(a->agent, agent_key)) return FS_ERR_BAD_ACCOUNT;  /* an agent account never changes its key */
    /* CE-1 (owner decision 2026-10-30): limits can never drop below what is already committed, so
     * spent + reserved <= budget and (same day) daily_used <= daily hold in every reachable state. */
    uint64_t committed; if (!add_ok(a->spent, a->reserved, &committed)) return FS_ERR_OVERFLOW;
    if (cfg->budget < committed) return FS_ERR_INVALID_CONFIG;
    if (a->day == fs_utc_day(now_ns) && cfg->daily < a->daily_used) return FS_ERR_INVALID_CONFIG;
  }
  n.per_tx = cfg->per_tx; n.daily = cfg->daily; n.budget = cfg->budget;
  n.threshold = cfg->threshold; n.valid_until_ns = cfg->valid_until_ns;
  n.active = 1;              /* counters (spent, reserved, daily) and epoch are preserved */
  *a = n;
  return FS_OK;
}

int fs_agent_revoke(fs_agent_t *a) {
  if (a->magic != FS_AGENT_MAGIC || !a->active) return FS_ERR_UNKNOWN_AGENT;
  uint64_t e; if (!add_ok(a->epoch, 1, &e)) return FS_ERR_OVERFLOW;
  a->active = 0;
  a->epoch = e;              /* every pending request of the old epoch can never execute */
  a->reserved = 0;           /* ... so all their reservations end here, exactly once */
  return FS_OK;
}

int fs_agent_recipient_allowed(fs_agent_t const *a, uint8_t const recipient[FS_KEY_SZ]) {
  if (fs_key_is_zero(recipient)) return 0;
  for (int i = 0; i < a->recipient_cnt && i < FS_MAX_RECIPIENTS; i++) if (fs_key_eq(a->recipients[i], recipient)) return 1;
  return 0;
}

int fs_agent_set_recipient(fs_agent_t *a, uint8_t const recipient[FS_KEY_SZ], int allowed) {
  if (a->magic != FS_AGENT_MAGIC) return FS_ERR_UNKNOWN_AGENT;
  if (fs_key_is_zero(recipient)) return FS_ERR_BAD_INSTRUCTION;
  int idx = -1;
  for (int i = 0; i < a->recipient_cnt && i < FS_MAX_RECIPIENTS; i++) if (fs_key_eq(a->recipients[i], recipient)) idx = i;
  if (allowed) {
    if (idx >= 0) return FS_OK;
    if (a->recipient_cnt >= FS_MAX_RECIPIENTS) return FS_ERR_ALLOWLIST_FULL;
    fs_copy(a->recipients[a->recipient_cnt], recipient, FS_KEY_SZ);
    a->recipient_cnt = (uint8_t)(a->recipient_cnt + 1);
  } else {
    if (idx < 0) return FS_OK;
    uint8_t last = (uint8_t)(a->recipient_cnt - 1);
    if (idx != last) fs_copy(a->recipients[idx], a->recipients[last], FS_KEY_SZ);
    fs_zero(a->recipients[last], FS_KEY_SZ);
    a->recipient_cnt = last;
  }
  return FS_OK;
}

/* ------------------------------------------------------------------ payments */
int fs_request(fs_vault_t *v, fs_agent_t *a, uint8_t const vault_addr[FS_KEY_SZ],
               uint8_t const recipient[FS_KEY_SZ], uint64_t amount, uint64_t nonce, uint64_t now_ns,
               fs_request_t *req, int *decision) {
  *decision = FS_DECISION_NONE;
  int e = fs_vault_check_live(v); if (e) return e;
  if (a->magic != FS_AGENT_MAGIC || !a->active) return FS_ERR_UNKNOWN_AGENT;
  if (!fs_key_eq(a->vault, vault_addr)) return FS_ERR_WRONG_VAULT;
  if (now_ns >= a->valid_until_ns) return FS_ERR_AGENT_EXPIRED;
  if (nonce != a->next_nonce) return FS_ERR_BAD_NONCE;
  if (amount == 0) return FS_ERR_ZERO_AMOUNT;
  if (!fs_agent_recipient_allowed(a, recipient)) return FS_ERR_RECIPIENT_NOT_ALLOWED;
  if (amount > a->per_tx) return FS_ERR_PER_TX;

  fs_agent_t n = *a;
  uint64_t today = fs_utc_day(now_ns);
  if (n.day != today) { n.day = today; n.daily_used = 0; }
  uint64_t used; if (!add_ok(n.daily_used, amount, &used)) return FS_ERR_OVERFLOW;
  if (used > n.daily) return FS_ERR_DAILY;
  uint64_t committed, total;
  if (!add_ok(n.spent, n.reserved, &committed) || !add_ok(committed, amount, &total)) return FS_ERR_OVERFLOW;
  if (total > n.budget) return FS_ERR_BUDGET;
  uint64_t nn; if (!add_ok(n.next_nonce, 1, &nn)) return FS_ERR_OVERFLOW;
  n.next_nonce = nn;           /* consumed whether instant or pending: a nonce can never be used twice */
  n.daily_used = used;

  if (amount <= n.threshold) {
    uint64_t paid; if (!add_ok(v->total_paid, amount, &paid)) return FS_ERR_OVERFLOW;
    n.spent += amount;          /* cannot overflow: spent + reserved + amount <= budget */
    *a = n; v->total_paid = paid;
    *decision = FS_DECISION_INSTANT;
    return FS_OK;
  }
  if (req->magic != 0) return FS_ERR_ALREADY_INITIALIZED;
  uint64_t exp; if (!add_ok(now_ns, v->approval_ttl_ns, &exp)) return FS_ERR_OVERFLOW;
  fs_request_t r; fs_zero(&r, sizeof r);
  r.magic = FS_REQ_MAGIC; r.version = FS_LAYOUT_VERSION; r.status = FS_REQ_PENDING;
  fs_copy(r.vault, vault_addr, FS_KEY_SZ); fs_copy(r.agent, a->agent, FS_KEY_SZ);
  fs_copy(r.recipient, recipient, FS_KEY_SZ); fs_copy(r.mint, v->mint, FS_KEY_SZ);
  r.amount = amount; r.nonce = nonce; r.epoch = n.epoch; r.day = today; r.created_ns = now_ns; r.expires_ns = exp;
  n.reserved += amount;         /* bounded by the budget check above */
  *a = n; *req = r;
  *decision = FS_DECISION_PENDING;
  return FS_OK;
}

int fs_approve(fs_vault_t *v, fs_agent_t *a, fs_request_t *req, fs_approval_t const *ap, uint64_t now_ns) {
  if (req->magic != FS_REQ_MAGIC || req->status != FS_REQ_PENDING) return FS_ERR_NO_PENDING;
  /* the approval must name exactly this operation */
  if (ap->op != FS_OP_APPROVE || !fs_key_eq(ap->vault, req->vault) || !fs_key_eq(ap->agent, req->agent) ||
      !fs_key_eq(ap->recipient, req->recipient) || !fs_key_eq(ap->mint, req->mint) ||
      ap->amount != req->amount || ap->nonce != req->nonce || ap->expires_ns != req->expires_ns)
    return FS_ERR_APPROVAL_MISMATCH;
  int e = fs_vault_check_live(v); if (e) return e;
  if (!fs_key_eq(req->mint, v->mint)) return FS_ERR_WRONG_TOKEN;
  if (now_ns >= req->expires_ns) return FS_ERR_REQUEST_EXPIRED;
  if (a->magic != FS_AGENT_MAGIC || !fs_key_eq(a->agent, req->agent) || !fs_key_eq(a->vault, req->vault)) return FS_ERR_BAD_ACCOUNT;
  if (!a->active) return FS_ERR_UNKNOWN_AGENT;
  if (now_ns >= a->valid_until_ns) return FS_ERR_AGENT_EXPIRED;          /* key validity at approval (R-2) */
  if (!fs_agent_recipient_allowed(a, req->recipient)) return FS_ERR_RECIPIENT_NOT_ALLOWED;
  if (req->epoch != a->epoch) return FS_ERR_STALE_REQUEST;                /* authority generation (R-1) */
  if (req->amount > a->per_tx) return FS_ERR_PER_TX;                       /* current limits (R-3) */
  uint64_t committed; if (!add_ok(a->spent, a->reserved, &committed)) return FS_ERR_OVERFLOW;
  if (committed > a->budget) return FS_ERR_BUDGET;                         /* reserved already includes amount */

  fs_agent_t n = *a;
  uint64_t today = fs_utc_day(now_ns);
  if (req->day == today) {
    if (n.day != today) { n.day = today; n.daily_used = 0; }
    if (n.daily_used > n.daily) return FS_ERR_DAILY;                      /* same day: already counted */
  } else {
    if (n.day != today) { n.day = today; n.daily_used = 0; }
    uint64_t used; if (!add_ok(n.daily_used, req->amount, &used)) return FS_ERR_OVERFLOW;
    if (used > n.daily) return FS_ERR_DAILY;                              /* charged to the execution day */
    n.daily_used = used;
  }
  uint64_t paid; if (!add_ok(v->total_paid, req->amount, &paid)) return FS_ERR_OVERFLOW;
  n.reserved -= req->amount;    /* reserved >= amount: current epoch, still pending */
  n.spent += req->amount;
  *a = n; v->total_paid = paid; req->status = FS_REQ_EXECUTED;
  return FS_OK;
}

static void release(fs_agent_t *a, fs_request_t const *req) {
  if (req->epoch == a->epoch) a->reserved -= req->amount;   /* stale: already released at revocation */
  if (a->day == req->day && a->daily_used >= req->amount) a->daily_used -= req->amount;
}

int fs_reject(fs_agent_t *a, fs_request_t *req) {
  if (req->magic != FS_REQ_MAGIC || req->status != FS_REQ_PENDING) return FS_ERR_NO_PENDING;
  if (a->magic != FS_AGENT_MAGIC || !fs_key_eq(a->agent, req->agent) || !fs_key_eq(a->vault, req->vault)) return FS_ERR_BAD_ACCOUNT;
  release(a, req); req->status = FS_REQ_REJECTED;
  return FS_OK;
}

int fs_expire(fs_agent_t *a, fs_request_t *req, uint64_t now_ns) {
  if (req->magic != FS_REQ_MAGIC || req->status != FS_REQ_PENDING) return FS_ERR_NO_PENDING;
  if (a->magic != FS_AGENT_MAGIC || !fs_key_eq(a->agent, req->agent) || !fs_key_eq(a->vault, req->vault)) return FS_ERR_BAD_ACCOUNT;
  int stale = req->epoch != a->epoch;
  if (!stale && now_ns < req->expires_ns) return FS_ERR_REQUEST_NOT_EXPIRED;
  release(a, req); req->status = (uint8_t)(stale ? FS_REQ_INVALIDATED : FS_REQ_EXPIRED);
  return FS_OK;
}
