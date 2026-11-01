#!/usr/bin/env bash
# Mutation check: each mutant removes ONE security check from the program; the test suites
# (functional + adversarial + property) must fail for every mutant. LOCAL SIMULATION only.
set -u
cd "$(dirname "$0")/.."
SDK=vendor/thru-sdk-c
CF="-std=c17 -O1 -g -fPIC -I$SDK -fsanitize=undefined -fno-sanitize-recover=all -w"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
declare -A M=(
  [core:no_per_tx]='program/flowstate_core.c|if (amount > a->per_tx) return FS_ERR_PER_TX;|'
  [core:no_daily]='program/flowstate_core.c|if (used > n.daily) return FS_ERR_DAILY;|'
  [core:no_budget]='program/flowstate_core.c|if (total > n.budget) return FS_ERR_BUDGET;|'
  [core:no_nonce]='program/flowstate_core.c|if (nonce != a->next_nonce) return FS_ERR_BAD_NONCE;|'
  [core:no_recipient_check]='program/flowstate_core.c|if (!fs_agent_recipient_allowed(a, recipient)) return FS_ERR_RECIPIENT_NOT_ALLOWED;|'
  [core:no_key_expiry]='program/flowstate_core.c|if (now_ns >= a->valid_until_ns) return FS_ERR_AGENT_EXPIRED;|'
  [core:no_epoch_check]='program/flowstate_core.c|if (req->epoch != a->epoch) return FS_ERR_STALE_REQUEST; |'
  [core:no_approval_binding]='program/flowstate_core.c|ap->amount != req->amount |0 && ap->amount != req->amount '
  [core:no_approve_daily]='program/flowstate_core.c|if (n.daily_used > n.daily) return FS_ERR_DAILY; |'
  [core:revoke_keeps_reserved]='program/flowstate_core.c|a->reserved = 0;           |'
  [core:release_double]='program/flowstate_core.c|if (req->epoch == a->epoch) a->reserved -= req->amount;|if (a->reserved >= req->amount) a->reserved -= req->amount;'
  [core:unpause_after_kill]='program/flowstate_core.c|if (v->flags \& FS_VAULT_KILLED) return FS_ERR_KILLED;   /\* kill is irreversible: no unpause \*/|'
  [core:allow_budget_below_spent]='program/flowstate_core.c|if (cfg->budget < committed) return FS_ERR_INVALID_CONFIG;|'
  [core:allow_daily_below_used]='program/flowstate_core.c|if (a->day == fs_utc_day(now_ns) \&\& cfg->daily < a->daily_used) return FS_ERR_INVALID_CONFIG;|'
  [adapter:create_not_writable]='program/flowstate.c|REQUIRE(tsys_set_account_data_writable(idx) == TSDK_SUCCESS, FS_ERR_ACCOUNT_CREATE);|'
  [adapter:no_freeze_check]='program/flowstate.c|REQUIRE(md[FS_MINT_HAS_FREEZE_OFF] == 0, FS_ERR_MINT_FREEZABLE);|'
  [adapter:no_signer_auth]='program/flowstate.c|REQUIRE(tsdk_is_account_authorized_by_idx(idx), FS_ERR_UNAUTHORIZED);|'
  [adapter:no_token_program_check]='program/flowstate.c|REQUIRE(fs_key_eq(addr_of(token_program_idx)->key, TOKEN_PROGRAM), FS_ERR_WRONG_TOKEN);|'
  [adapter:no_vault_token_check]='program/flowstate.c|REQUIRE(fs_key_eq(addr_of(ix.vault_token_idx)->key, v.token_account), FS_ERR_WRONG_TOKEN);|'
  [adapter:no_owner_check]='program/flowstate.c|REQUIRE(tsdk_is_account_owned_by_current_program(idx), FS_ERR_BAD_ACCOUNT);|'
)
# Equivalent mutants: removing the check cannot change behaviour in any reachable state. Each one is
# listed with its argument; they are reported, never counted as "caught".
declare -A EQUIV=(
  [core:no_approve_daily]="same-day branch of fs_approve: daily_used <= daily already holds in every reachable state (request-time DAILY check + CE-1 / I-16), so 'daily_used > daily' can never be true there; kept as defence in depth. Bounded model check (depth 6) finds no state where it fires."
)
fail=0
for name in $(printf '%s\n' "${!M[@]}" | sort); do
  IFS='|' read -r file from to <<< "${M[$name]}"
  rm -rf "$TMP/src"; mkdir -p "$TMP/src/program" "$TMP/src/sim"
  cp program/*.c program/*.h "$TMP/src/program/"; cp sim/*.c "$TMP/src/sim/"
  python3 - "$TMP/src/$file" "$from" "$to" <<'PY' || { echo "$name: pattern not found -> ERROR"; fail=1; continue; }
import sys
p, a, b = sys.argv[1], sys.argv[2].replace("\\|", "|").replace("\\&", "&").replace("\\*", "*"), sys.argv[3]
s = open(p).read()
n = s.count(a)
if n == 0: sys.exit(1)
open(p, "w").write(s.replace(a, b))
PY
  gcc $CF -shared -o "$TMP/lib.so" "$TMP/src/program/flowstate_core.c" "$TMP/src/program/flowstate.c" "$TMP/src/sim/sim.c" "$TMP/src/sim/sha256_host.c" 2>"$TMP/cc.log" || { echo "$name: build failed"; fail=1; continue; }
  if [ "${MC:-0}" = 1 ]; then
    # judge the mutant with the bounded model checker alone (depth ${MC_DEPTH:-5})
    out=$(cd tests && FS_SIM_LIB="$TMP/lib.so" timeout 900 python3 model_check.py "${MC_DEPTH:-5}" 2>&1 | grep -E "^(PASS|VIOLATION)" | head -1 | cut -c1-110)
    if echo "$out" | grep -q "^PASS"; then echo "$name: not caught by model check ($out)"; else echo "$name: caught by model check ($out)"; fi
    continue
  fi
  # full campaign (30 seeds): a reduced campaign can fail its coverage gates, which is NOT a detection
  log=$(cd tests && FS_SIM_LIB="$TMP/lib.so" timeout 900 python3 -m unittest test_functional test_adversarial test_properties test_scenarios test_model_conformance 2>&1)
  out=$(echo "$log" | grep -E '^(OK|FAILED)' | tail -1)   # unittest verdict line (summary prints may follow it)
  only_cov=$(echo "$log" | grep -c "AssertionError: {.*} != {}")
  if echo "$out" | grep -q "^OK"; then
    if [ -n "${EQUIV[$name]:-}" ]; then echo "$name: EQUIVALENT (not counted) - ${EQUIV[$name]}"; else echo "$name: MISSED ($out)"; fail=1; fi
  elif [ "$only_cov" -gt 0 ] && [ "$(echo "$log" | grep -c '^FAIL:\|^ERROR:')" -eq 1 ]; then
    echo "$name: NOT DETECTED (only a coverage gate failed: $out)"; fail=1
  else echo "$name: caught ($out)"; fi
done
exit $fail
