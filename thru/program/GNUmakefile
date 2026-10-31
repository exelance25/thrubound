# Flowstate on Thru — RISC-V build with the official Thru C SDK make system.
#   THRU_C_SDK_DIR      installed SDK (contains thru_c_program.mk, include/, lib/)
#   RISCV_TOOLCHAIN_ROOT toolchain root (bin/riscv64-unknown-elf-gcc, picolibc/thruvm)
# See docs/DEPLOYMENT.md. Output: build/thruvm/bin/flowstate_c.bin
BASEDIR:=$(CURDIR)/build
THRU_C_SDK_DIR?=$(HOME)/.thru/sdk/c/thru-sdk
include $(THRU_C_SDK_DIR)/thru_c_program.mk
