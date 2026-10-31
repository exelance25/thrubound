/* Flowstate on Thru — instruction and event wire formats (packed, little-endian).
 * One instruction per transaction: [u8 op][op-specific packed struct][optional u32 proof_sz + proof bytes].
 * Account indices refer to the transaction account list (0 = fee payer, 1 = program, 2.. = inputs).
 * Clients: thru/client (TypeScript) and thru/tests/fsclient.py build exactly these bytes. */
#ifndef FLOWSTATE_ABI_H
#define FLOWSTATE_ABI_H

#include "flowstate_core.h"

#define FS_OP_INIT_VAULT     0
#define FS_OP_BIND_TOKEN     1
#define FS_OP_SET_AGENT      2
#define FS_OP_REVOKE         3
#define FS_OP_SET_RECIPIENT  4
#define FS_OP_REQUEST        5
#define FS_OP_APPROVE        6
#define FS_OP_REJECT         7
#define FS_OP_EXPIRE         8
#define FS_OP_SET_PAUSED     9
#define FS_OP_KILL           10
#define FS_OP_WITHDRAW       11

#define FS_NO_ACCOUNT        0xFFFFu

/* Seeds for program-defined accounts: seed = sha256(tag || fields); address = sha256(program || 0 || seed). */
#define FS_SEED_TAG_VAULT    "flowstate/vault/v1"
#define FS_SEED_TAG_AGENT    "flowstate/agent/v1"
#define FS_SEED_TAG_REQUEST  "flowstate/request/v1"

/* Official token program (thru.program.token v0.1.0) — instruction tag and account layout. */
#define FS_TOKEN_IX_TRANSFER 2
#define FS_TOKEN_ACCOUNT_SZ  73   /* mint[32] owner[32] amount u64 is_frozen u8 */
/* TokenMintAccount (ABI, size-discriminated: 115 bytes): decimals u8 | supply u64 | creator[32] |
 * mint_authority[32] | freeze_authority[32] | has_freeze_authority u8 | ticker{len u8, bytes[8]} */
#define FS_TOKEN_MINT_SZ     115
#define FS_MINT_HAS_FREEZE_OFF 105

#pragma pack(push, 1)
typedef struct { uint8_t op; uint16_t vault_idx, owner_idx; uint8_t mint[32]; uint64_t vault_id, ttl_ns; uint32_t proof_sz; } fs_ix_init_vault_t;
/* mint_idx = FS_NO_ACCOUNT skips the mint check; otherwise the mint account must have no freeze authority. */
typedef struct { uint8_t op; uint16_t vault_idx, owner_idx, token_acct_idx, mint_idx; } fs_ix_bind_token_t;
typedef struct { uint8_t op; uint16_t vault_idx, owner_idx, agent_acct_idx; uint8_t agent[32];
                 uint64_t per_tx, daily, budget, threshold, valid_until_ns; uint8_t create; uint32_t proof_sz; } fs_ix_set_agent_t;
typedef struct { uint8_t op; uint16_t vault_idx, owner_idx, agent_acct_idx; } fs_ix_revoke_t;
typedef struct { uint8_t op; uint16_t vault_idx, owner_idx, agent_acct_idx; uint8_t recipient[32]; uint8_t allowed; } fs_ix_set_recipient_t;
typedef struct { uint8_t op; uint16_t vault_idx, agent_acct_idx, agent_signer_idx, request_acct_idx,
                 vault_token_idx, recipient_token_idx, token_program_idx; uint64_t nonce, amount; uint32_t proof_sz; } fs_ix_request_t;
typedef struct { uint8_t op; uint16_t vault_idx, owner_idx, agent_acct_idx, request_acct_idx,
                 vault_token_idx, recipient_token_idx, token_program_idx; fs_approval_t approval; } fs_ix_approve_t;
typedef struct { uint8_t op; uint16_t vault_idx, agent_acct_idx, request_acct_idx, actor_idx; } fs_ix_reject_t;
typedef struct { uint8_t op; uint16_t vault_idx, agent_acct_idx, request_acct_idx; } fs_ix_expire_t;
typedef struct { uint8_t op; uint16_t vault_idx, owner_idx; uint8_t paused; } fs_ix_set_paused_t;
typedef struct { uint8_t op; uint16_t vault_idx, owner_idx; } fs_ix_kill_t;
typedef struct { uint8_t op; uint16_t vault_idx, owner_idx, vault_token_idx, dest_token_idx, token_program_idx; uint64_t amount; } fs_ix_withdraw_t;

/* Token program transfer instruction (official ABI). */
typedef struct { uint8_t tag; uint16_t source_idx, dest_idx; uint64_t amount; } fs_token_transfer_ix_t;
typedef struct { uint8_t mint[32]; uint8_t owner[32]; uint64_t amount; uint8_t is_frozen; } fs_token_account_t;

/* Events: [u8 kind][payload]. */
enum fs_event_kind { FS_EV_VAULT_INIT = 1, FS_EV_TOKEN_BOUND = 2, FS_EV_AGENT_SET = 3, FS_EV_AGENT_REVOKED = 4,
                     FS_EV_RECIPIENT = 5, FS_EV_PAID = 6, FS_EV_REQUESTED = 7, FS_EV_REJECTED = 8,
                     FS_EV_EXPIRED = 9, FS_EV_INVALIDATED = 10, FS_EV_PAUSED = 11, FS_EV_KILLED = 12, FS_EV_WITHDRAWN = 13 };
typedef struct { uint8_t kind; uint8_t vault[32]; uint8_t owner[32]; uint8_t mint[32]; } fs_ev_vault_init_t;
typedef struct { uint8_t kind; uint8_t vault[32]; uint8_t token_account[32]; uint8_t mint_unfreezable; } fs_ev_token_bound_t;
typedef struct { uint8_t kind; uint8_t vault[32]; uint8_t agent[32]; uint64_t per_tx, daily, budget, threshold, valid_until_ns, epoch; } fs_ev_agent_set_t;
typedef struct { uint8_t kind; uint8_t vault[32]; uint8_t agent[32]; uint64_t new_epoch; } fs_ev_agent_revoked_t;
typedef struct { uint8_t kind; uint8_t vault[32]; uint8_t agent[32]; uint8_t recipient[32]; uint8_t allowed; } fs_ev_recipient_t;
typedef struct { uint8_t kind; uint8_t vault[32]; uint8_t agent[32]; uint8_t recipient[32]; uint64_t amount, nonce; uint8_t approved; } fs_ev_paid_t;
typedef struct { uint8_t kind; uint8_t vault[32]; uint8_t agent[32]; uint8_t recipient[32]; uint64_t amount, nonce, expires_ns; } fs_ev_requested_t;
typedef struct { uint8_t kind; uint8_t vault[32]; uint8_t agent[32]; uint64_t nonce; } fs_ev_closed_t; /* REJECTED / EXPIRED / INVALIDATED */
typedef struct { uint8_t kind; uint8_t vault[32]; uint8_t flag; } fs_ev_flag_t;                    /* PAUSED (flag=paused) / KILLED */
typedef struct { uint8_t kind; uint8_t vault[32]; uint8_t dest[32]; uint64_t amount; } fs_ev_withdrawn_t;
#pragma pack(pop)

_Static_assert(sizeof(fs_token_transfer_ix_t) == 13, "token transfer ix");
_Static_assert(sizeof(fs_token_account_t) == FS_TOKEN_ACCOUNT_SZ, "token account");

#endif
