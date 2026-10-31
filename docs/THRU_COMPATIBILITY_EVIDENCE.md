# ThruBound — Thru compatibility evidence (2026-10-30)

**Bottom line.** The program compiles with the **official Thru toolchain and official C SDK (v0.4.2)**. The build is reproducible. The **official `thru` CLI's local program-image validation** accepts the binary. The program has **never been executed on a Thru VM or network**, so it is **not** called "Thru-compatible" or "production-ready" here. Execution is the missing evidence.

Raw evidence is in `m2/thrubound-p2/`.

## 1. How the official tools were obtained

| Item | Source | Integrity |
|---|---|---|
| Toolchain `thru-toolchain-Linux-x86_64-v0.4.2.tar.gz` (1,110,898,953 B) | GitHub release v0.4.2 of `Unto-Labs/thru` (published 2026-10-14). `thru dev toolchain install` fails in the cloud workspace (`api.github.com` refused). The linked computer could reach GitHub, so the release asset URL was resolved there and the file downloaded on both machines | sha256 `0b07caad88918696ece94958a9b9525c5bfe4b8dd87d7cbe6440ba165f322686`, identical on both machines. **The release publishes no checksum for this asset** |
| C SDK `thru-program-sdk-c-v0.4.2.tar.gz` | same release | sha256 `74c9a763…`; its `thru-sdk/` is byte-identical (`diff -r`) to `thru/vendor/thru-sdk-c/thru-sdk` |
| CLI | npm `thru` 0.4.2+e47b2a21. The release `.deb` (sha256 `f864c41f…`, matches `thru-cli-SHA256SUMS`) contains only `/usr/bin/thru` | — |
| Local Thru VM / node | **not in the release** and not in the source mirror. The toolchain's `riscv64-unknown-elf-run` is a generic RISC-V simulator, not ThruVM | **BLOCKED** |

The toolchain needs glibc ≥ 2.38, so it runs in the cloud workspace (Ubuntu 24.04) but not in the linked computer's VM.

## 2. Checks

| Aspect | What the official sources say | Evidence for ThruBound | Status |
|---|---|---|---|
| Compiler | `riscv64-unknown-elf-gcc (g5115c7e44) 15.2.0`, configured `--with-arch=rv64imc_zicsr_zba_zbb_zbc_zbs_zknh --with-abi=lp64` | `thru/scripts/build_official.sh`: SDK built per its README ("Manual Setup"), program built with the SDK's make rules | **PASS (compile)** |
| Target and flags | SDK `config/machine/thruvm.mk`:<br>`-march=rv64imc_zba_zbb_zbc_zbs_zknh -mabi=lp64 -mcmodel=medlow -mstrict-align -static-pie -ffreestanding -nostartfiles`, picolibc `thruvm`, `-Werror -Wall -Wextra -Wpedantic -Wconversion`, linker script `config/link.ld`, entry `_start` | built with exactly these flags, warnings as errors | **PASS** |
| Reproducibility | — | two independent builds of the current program give `flowstate_c.bin` sha256 `4f49941902c4a1e0161d29280415d9b13d8f23cdc7eeffa94c17703283615e14` (27,584 B); the official template `hello_c.bin` gives `732d0aad…`, the same as with the earlier fallback compiler | **PASS** |
| Instruction set | must stay within the `-march` above | disassembly: only RV64I/M/C, Zba (`add.uw`, `sh*add`), Zbb (`andn`, `maxu`, `rev8`, `zext.h`), Zbs (`bseti`), Zknh (`sha256*`). No CSR, float or atomic instructions | **PASS (static scan)** |
| Entry point and memory layout | template program as reference | same ELF type, entry `0x3000000`, the same two LOAD segments, GNU_STACK as the template; `.bin` = `objcopy -O binary` of the ELF | **PASS (matches template)** |
| Runtime imports | syscalls go through `ecall` in the SDK (`tn_sdk_syscall.c`) | 0 undefined symbols, 0 dynamic relocations, 8 `ecall` sites (template has 3) | **PASS (static)** |
| Deployment format | CLI `program create <seed> <file>`. Local validation rejects ELF ("upload the ThruVM .bin program image instead") and checks an image version byte (`0x01`) | our `.bin` passed local validation and reached "Step 1: Uploading program to temporary buffer", then stopped at the deliberately unreachable RPC (`127.0.0.1:9`). Control cases: `.elf` rejected; random bytes rejected ("invalid program image version byte") | **PASS (format check only)** |
| Serialization | packed little-endian structs; official ABI YAMLs | instruction and account layouts are our own (`THRU_ACCOUNT_MODEL.md`); token structs follow the official token ABI | **NOT VERIFIED** on chain |
| Account access rules | SDK source (`tn_sdk.c`): writable = fee payer or the read-write range; authorized = fee payer, current program, or a parent's invoke auth list | implemented against the SDK API; tested only in the LOCAL SIMULATION, which re-implements these rules | **SIMULATED** |
| Transaction rollback | `tsdk_revert` aborts the transaction | relied on; modelled in the simulation with full snapshot rollback | **SIMULATED** |
| Compute and memory limits | runtime-defined | unknown for this program | **NOT RUN** |
| Execution on ThruVM | — | none | **BLOCKED**: no VM in the release; network unreachable |
| Deployment | — | none | **BLOCKED** |

## 3. Fallback-compiler binary

The earlier binary (Ubuntu gcc 13.2, picolibc 1.8.6; sha256 `0bdd043f…`) is kept in the record but **superseded**. The current reference build is the official-toolchain build above.
