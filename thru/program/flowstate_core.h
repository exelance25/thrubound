/* Flowstate on Thru — pure policy core.
 *
 * No syscalls, no allocation, no globals. Every function takes the state it needs, validates
 * everything first and only then writes (all-or-nothing). The same file is compiled for the
 * Thru VM (RISC-V, via flowstate.c) and for the host (tests and local simulation).
 *
 * Account layouts are fixed, little-endian, packed and versioned. See docs/THRU_ACCOUNT_MODEL.md.
 * UNAUDITED. NOT DEPLOYED. NOT EXECUTED ON A THRU VM. */
#ifndef FLOWSTATE_CORE_H
#define FLOWSTATE_CORE_H

#include <stdint.h>

#define FS_KEY_SZ            32
#define FS_MAX_RECIPIENTS    8
#define FS_NS_PER_DAY        86400000000000ULL      /* daily window = UTC calendar day */
#define FS_TTL_MIN_NS        (300ULL * 1000000000ULL)
#define FS_TTL_MAX_NS        (30ULL * FS_NS_PER_DAY)

#define FS_VAULT_MAGIC       0x31565346u   /* "FSV1" */
#define FS_AGENT_MAGIC       0x31415346u   /* "FSA1" */
#define FS_REQ_MAGIC         0x31525346u   /* "FSR1" */
#define FS_LAYOUT_VERSION    1

#define FS_VAULT_PAUSED      0x01
#define FS_VAULT_KILLED      0x02
#define FS_VAULT_MINT_UNFREEZABLE 0x04  /* verified at BIND_TOKEN: the mint has no freeze authority */

enum fs_req_status { FS_REQ_NONE = 0, FS_REQ_PENDING = 1, FS_REQ_EXECUTED = 2, FS_REQ_REJECTED = 3,
                     FS_REQ_EXPIRED = 4, FS_REQ_INVALIDATED = 5 };

/* Error codes (returned by core functions and used as revert codes by the program). */
enum fs_err {
  FS_OK = 0,
  FS_ERR_BAD_INSTRUCTION = 0x1001, FS_ERR_BAD_ACCOUNT = 0x1002, FS_ERR_NOT_OWNER = 0x1003,
  FS_ERR_NOT_AGENT = 0x1004, FS_ERR_UNAUTHORIZED = 0x1005, FS_ERR_ALREADY_INITIALIZED = 0x1006,
  FS_ERR_NOT_INITIALIZED = 0x1007, FS_ERR_PAUSED = 0x1008, FS_ERR_KILLED = 0x1009,
  FS_ERR_UNKNOWN_AGENT = 0x100A, FS_ERR_AGENT_EXPIRED = 0x100B, FS_ERR_BAD_NONCE = 0x100C,
  FS_ERR_ZERO_AMOUNT = 0x100D, FS_ERR_RECIPIENT_NOT_ALLOWED = 0x100E, FS_ERR_PER_TX = 0x100F,
  FS_ERR_DAILY = 0x1010, FS_ERR_BUDGET = 0x1011, FS_ERR_INVALID_CONFIG = 0x1012,
  FS_ERR_NO_PENDING = 0x1013, FS_ERR_REQUEST_EXPIRED = 0x1014, FS_ERR_REQUEST_NOT_EXPIRED = 0x1015,
  FS_ERR_STALE_REQUEST = 0x1016, FS_ERR_APPROVAL_MISMATCH = 0x1017, FS_ERR_OVERFLOW = 0x1018,
  FS_ERR_ALLOWLIST_FULL = 0x1019, FS_ERR_WRONG_TOKEN = 0x101A, FS_ERR_TOKEN_NOT_BOUND = 0x101B,
  FS_ERR_TRANSFER_FAILED = 0x101C, FS_ERR_INSUFFICIENT_FUNDS = 0x101D, FS_ERR_WRONG_VAULT = 0x101E,
  FS_ERR_REENTRANT = 0x101F, FS_ERR_ACCOUNT_CREATE = 0x1020, FS_ERR_DERIVATION = 0x1021, FS_ERR_MINT_FREEZABLE = 0x1022,
};

#pragma pack(push, 1)
typedef struct {
  uint32_t magic;              /* FS_VAULT_MAGIC */
  uint8_t  version;            /* FS_LAYOUT_VERSION */
  uint8_t  flags;              /* FS_VAULT_PAUSED | FS_VAULT_KILLED | FS_VAULT_MINT_UNFREEZABLE */
  uint16_t reserved0;
  uint8_t  owner[FS_KEY_SZ];   /* account that must authorize owner actions */
  uint8_t  mint[FS_KEY_SZ];    /* the only token this vault pays in */
  uint8_t  token_account[FS_KEY_SZ]; /* vault's token account (owner field == vault address); zero until bound */
  uint64_t vault_id;
  uint64_t approval_ttl_ns;
  uint64_t total_paid;
  uint32_t agent_count;
  uint32_t reserved1;
} fs_vault_t;                  /* 136 bytes */

typedef struct {
  uint32_t magic;              /* FS_AGENT_MAGIC */
  uint8_t  version;
  uint8_t  active;
  uint8_t  recipient_cnt;
  uint8_t  reserved0;
  uint8_t  vault[FS_KEY_SZ];   /* vault account address this agent belongs to */
  uint8_t  agent[FS_KEY_SZ];   /* agent key that must authorize payment requests */
  uint64_t epoch;              /* authority generation: +1 on every revocation */
  uint64_t per_tx;
  uint64_t daily;
  uint64_t budget;             /* lifetime cap: spent + reserved <= budget */
  uint64_t threshold;          /* amount > threshold needs owner approval */
  uint64_t valid_until_ns;     /* key unusable at or after this block time */
  uint64_t day;                /* UTC day index of daily_used */
  uint64_t daily_used;
  uint64_t spent;
  uint64_t reserved;           /* sum of pending requests of the current epoch */
  uint64_t next_nonce;         /* replay protection: a request must carry exactly this nonce */
  uint8_t  recipients[FS_MAX_RECIPIENTS][FS_KEY_SZ]; /* allowlisted recipient TOKEN ACCOUNTS */
} fs_agent_t;                  /* 416 bytes */

typedef struct {
  uint32_t magic;              /* FS_REQ_MAGIC */
  uint8_t  version;
  uint8_t  status;             /* enum fs_req_status */
  uint16_t reserved0;
  uint8_t  vault[FS_KEY_SZ];
  uint8_t  agent[FS_KEY_SZ];
  uint8_t  recipient[FS_KEY_SZ];
  uint8_t  mint[FS_KEY_SZ];
  uint64_t amount;
  uint64_t nonce;
  uint64_t epoch;              /* agent epoch at creation */
  uint64_t day;                /* UTC day charged at creation */
  uint64_t created_ns;
  uint64_t expires_ns;
} fs_request_t;                /* 184 bytes */

typedef struct {
  uint64_t per_tx, daily, budget, threshold, valid_until_ns;
} fs_agent_cfg_t;

/* Everything an owner approval is bound to. Must equal the stored request exactly. */
typedef struct {
  uint8_t  vault[FS_KEY_SZ];
  uint8_t  agent[FS_KEY_SZ];
  uint8_t  recipient[FS_KEY_SZ];
  uint8_t  mint[FS_KEY_SZ];
  uint64_t amount;
  uint64_t nonce;
  uint64_t expires_ns;
  uint8_t  op;                 /* must be FS_OP_APPROVE */
} fs_approval_t;
#pragma pack(pop)

_Static_assert(sizeof(fs_vault_t) == 136, "vault layout");
_Static_assert(sizeof(fs_agent_t) == 416, "agent layout");
_Static_assert(sizeof(fs_request_t) == 184, "request layout");
_Static_assert(sizeof(fs_approval_t) == 153, "approval layout");

/* Outcome of a payment request. */
enum fs_decision { FS_DECISION_NONE = 0, FS_DECISION_INSTANT = 1, FS_DECISION_PENDING = 2 };

int  fs_key_eq(uint8_t const a[FS_KEY_SZ], uint8_t const b[FS_KEY_SZ]);
int  fs_key_is_zero(uint8_t const a[FS_KEY_SZ]);
uint64_t fs_utc_day(uint64_t now_ns);

int  fs_vault_init(fs_vault_t *v, uint8_t const owner[FS_KEY_SZ], uint8_t const mint[FS_KEY_SZ],
                   uint64_t vault_id, uint64_t ttl_ns);
int  fs_vault_check_live(fs_vault_t const *v);
int  fs_vault_bind_token(fs_vault_t *v, uint8_t const token_account[FS_KEY_SZ]);

int  fs_agent_set(fs_vault_t *v, fs_agent_t *a, uint8_t const vault_addr[FS_KEY_SZ],
                  uint8_t const agent_key[FS_KEY_SZ], fs_agent_cfg_t const *cfg, uint64_t now_ns, int is_new);
int  fs_agent_revoke(fs_agent_t *a);
int  fs_agent_set_recipient(fs_agent_t *a, uint8_t const recipient[FS_KEY_SZ], int allowed);
int  fs_agent_recipient_allowed(fs_agent_t const *a, uint8_t const recipient[FS_KEY_SZ]);

/* Agent payment request. On FS_OK, *decision says whether to transfer now (INSTANT) or whether
   *req was filled as a new pending request (PENDING). State is modified only on FS_OK. */
int  fs_request(fs_vault_t *v, fs_agent_t *a, uint8_t const vault_addr[FS_KEY_SZ],
                uint8_t const recipient[FS_KEY_SZ], uint64_t amount, uint64_t nonce, uint64_t now_ns,
                fs_request_t *req, int *decision);

/* Owner approval of a pending request, bound to *ap. On FS_OK the caller must transfer req->amount. */
int  fs_approve(fs_vault_t *v, fs_agent_t *a, fs_request_t *req, fs_approval_t const *ap, uint64_t now_ns);
int  fs_reject(fs_agent_t *a, fs_request_t *req);
int  fs_expire(fs_agent_t *a, fs_request_t *req, uint64_t now_ns);

int  fs_set_paused(fs_vault_t *v, int paused);
int  fs_kill(fs_vault_t *v);

#endif
