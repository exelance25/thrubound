#!/usr/bin/env bash
# ThruBound — run every local check with one command.
# Environment: Linux x86-64 (or WSL2 Ubuntu). LOCAL SIMULATION only: no network, keys or tokens.
#   bash thru/run_all_tests.sh            # full run (about 2-3 minutes)
#   QUICK=1 bash thru/run_all_tests.sh    # skips the slow mutation check
set -uo pipefail
cd "$(dirname "$0")"
ROOT=$(pwd)
LOG=${LOG:-$ROOT/build/run_all_tests.log}
mkdir -p "$(dirname "$LOG")"; : > "$LOG"
results=(); fail=0

need() { command -v "$1" >/dev/null 2>&1 || { echo "MISSING prerequisite: $1 ($2)"; exit 2; }; }
need gcc "sudo apt install build-essential"
need python3 "sudo apt install python3"
need node "Node.js 22: https://nodejs.org or nvm"
need npm "comes with Node.js"
node -e 'process.exit(+process.versions.node.split(".")[0] >= 20 ? 0 : 1)' || { echo "Node.js >= 20 required (tested with 22)"; exit 2; }

step() {   # step "<name>" "<success regex in output>" command...
  local name=$1 want=$2; shift 2
  local out; out=$("$@" 2>&1); local rc=$?
  { echo "===== $name (exit $rc)"; echo "$out"; } >> "$LOG"
  local line; line=$(echo "$out" | grep -E "$want" | tail -1)
  if [ $rc -eq 0 ] && [ -n "$line" ]; then results+=("PASS  $name  —  ${line:0:90}"); else results+=("FAIL  $name  (exit $rc; see $LOG)"); fail=1; fi
}

step "host build (real program code + simulated Thru runtime)" "built " bash build_host.sh
step "Python: functional, adversarial, property, scenarios, model conformance" "^OK" \
  bash -c "cd tests && python3 -m unittest test_functional test_adversarial test_properties test_scenarios test_model_conformance 2>&1 | grep -E '^(Ran |OK|FAILED)'"
step "independent verifier over all traces" "^PASS" python3 verifier/verify_thru.py
step "verifier tamper tests" "^OK" bash -c "cd verifier && python3 -m unittest test_verifier 2>&1 | grep -E '^(Ran |OK|FAILED)'"
step "bounded model check (depth 5)" "^PASS" bash -c "cd tests && python3 model_check.py 5 | grep -E '^(PASS|VIOLATION)'"
if python3 -c "import z3" 2>/dev/null; then
  step "SMT proofs of the abstract model (z3)" "^PASS" bash -c "python3 proof/inductive_smt.py | tail -1"
else
  results+=("SKIP  SMT proofs (pip install z3-solver to run)")
fi
step "SDK: install, build, tests" "^# fail 0" bash -c "cd sdk && npm ci --silent && npm run build --silent >/dev/null && npm test 2>&1 | grep -E '^# (pass|fail)'"
step "independent example app (7 gate steps + authority analysis)" "All demo checks passed" \
  bash -c "cd ../examples/subscription-payer && npm install --silent && node index.mjs"
step "example trace through the independent verifier" "^PASS" bash -c "cd ../examples/subscription-payer && python3 ../../thru/verifier/verify_thru.py out/trace.jsonl"
step "demo page API test" "^# fail 0" bash -c "cd demo && npm install --silent && npm test 2>&1 | grep -E '^# (pass|fail)'"
if [ "${QUICK:-0}" != 1 ]; then
  step "program mutation check (20 mutants)" "^mutants caught" bash -c "out=\$(bash tests/mutation_check.sh 2>&1); rc=\$?; echo \"\$out\"; echo \"mutants caught: \$(echo \"\$out\" | grep -c ': caught'), equivalent: \$(echo \"\$out\" | grep -ci 'equivalent')\"; exit \$rc"
fi

echo
echo "ThruBound local checks — LOCAL SIMULATION (not a Thru network)"
printf '%s\n' "${results[@]}"
echo
[ $fail -eq 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED — details in $LOG"
exit $fail
