#!/usr/bin/env bash
# Build the Flowstate/ThruBound program with the OFFICIAL Thru toolchain and C SDK (v0.4.2).
#   TOOLCHAIN : root of thru-toolchain-Linux-x86_64-v0.4.2 (from `thru dev toolchain install`
#               or the GitHub release asset; sha256 of the tarball 0b07caad88918696…)
#   SDK_SRC   : thru-program-sdk-c-v0.4.2 (release asset, sha256 74c9a763bb898df2…; identical to
#               thru/vendor/thru-sdk-c/thru-sdk)
# Output: <out>/build/thruvm/bin/flowstate_c.bin. Compile only: this does NOT execute the program.
set -euo pipefail
TOOLCHAIN=${TOOLCHAIN:?set TOOLCHAIN}; SDK_SRC=${SDK_SRC:?set SDK_SRC to the extracted thru-program-sdk-c-v0.4.2 release (its thru-sdk/ is identical to thru/vendor/thru-sdk-c/thru-sdk)}
OUT=${OUT:-$(mktemp -d)}
export PATH="$TOOLCHAIN/bin:$PATH"
# 1. build the SDK library exactly as its README's "Manual Setup" describes
( cd "$SDK_SRC" && RISCV_TOOLCHAIN_ROOT="$TOOLCHAIN" make BASEDIR="$OUT/sdk-build" all lib include >/dev/null )
# 2. lay it out as an installed SDK (thru_c_program.mk + config + include + lib)
mkdir -p "$OUT/sdk/thru-sdk"; cp -r "$SDK_SRC/thru-sdk/." "$OUT/sdk/thru-sdk/"
cp -r "$OUT/sdk-build/thruvm/include" "$OUT/sdk-build/thruvm/lib" "$OUT/sdk/thru-sdk/"
# 3. build the program with the SDK's own make rules (flags from config/machine/thruvm.mk)
cp -r "$(dirname "$0")/../program" "$OUT/program"; rm -rf "$OUT/program/build"
( cd "$OUT/program" && RISCV_TOOLCHAIN_ROOT="$TOOLCHAIN" make THRU_C_SDK_DIR="$OUT/sdk/thru-sdk" >/dev/null )
"$TOOLCHAIN/bin/riscv64-unknown-elf-gcc" --version | head -1
sha256sum "$OUT/program/build/thruvm/bin/flowstate_c.bin"
