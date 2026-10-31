#!/usr/bin/env bash
# Host build of the Flowstate program + LOCAL SIMULATION (not the Thru VM), for tests.
# Output: thru/build/host/libflowstate_sim.so  (UBSan: any undefined behaviour aborts)
# sim/sha256_host.c replaces the SDK sha256 (which uses RISC-V Zknh instructions) on the host.
set -euo pipefail
cd "$(dirname "$0")"
OUT=build/host; mkdir -p "$OUT"
SDK=vendor/thru-sdk-c
CFLAGS="-std=c17 -O1 -g -fPIC -Wall -Wextra -Wpedantic -Wconversion -Werror -Wno-pedantic -I$SDK -fsanitize=undefined -fno-sanitize-recover=all"
gcc $CFLAGS -shared -o "$OUT/libflowstate_sim.so" \
  program/flowstate_core.c program/flowstate.c sim/sim.c sim/sha256_host.c
echo "built $OUT/libflowstate_sim.so ($(gcc --version | head -1))"
