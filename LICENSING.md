# Licensing map

This repository holds two projects, and they are under different licenses:
- **ThruBound** (Thru-native), licensed under **Apache-2.0**;
- the legacy **AgentVault** EVM research project, which keeps the **MIT** license it was declared under.

Third-party code keeps its own license.

> This file describes the `feature/thrubound` branch of the full AgentVault repository. The proposed public `thrubound` repository contains only the ThruBound paths, so only the Apache-2.0 and third-party rows apply there.

| Path | License | Basis |
|---|---|---|
| `thru/` (except `thru/vendor/`), `examples/subscription-payer/`, `docs/` (except `docs/legacy/`), `m2/thru-*`, `m2/thrubound-*`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, `.env.example` | **Apache-2.0** (`LICENSE`, `NOTICE`) | Written for ThruBound by the project owner. The SDK, demo and example `package.json` files already declared Apache-2.0 |
| `thru/vendor/thru-sdk-c/` | Apache-2.0, Thru Contributors (its own `LICENSE` and `NOTICE`, including the Firedancer notice) | Official Thru C SDK v0.4.2, unmodified (`SOURCE.txt`) |
| `contracts/` (except `contracts/vendor/`), `forge/`, `test/`, `app/`, `notifier/`, `scripts/`, `verifier/`, `experiments/`, `runs/`, other `m2/` folders, root legacy `*.md`, `docs/legacy/`, `hardhat*.config.js`, `foundry.toml`, root `package.json` | **MIT** (legacy, unchanged) | Declared by the root `package.json` (`"license": "MIT"`) since the first commit, and by `SPDX-License-Identifier: MIT` in 12 Solidity and patch files. The MIT license text with a copyright line was never added; see the note below |
| `contracts/vendor/usdc/` | Apache-2.0 (Circle `stablecoin-evm`, of which 6 files are MIT per their SPDX headers: `oz/` and `v1/Ownable.sol`, `v1/Pausable.sol`) | `SOURCE.txt`, own `LICENSE` |
| `vendor/forge-std/` | MIT OR Apache-2.0 (dual) | own `LICENSE-MIT` and `LICENSE-APACHE` |
| `vendor/safe-1.4.1/` | **LGPL-3.0** (Safe contract build artifacts, unmodified) | `SOURCE.txt`, own `LICENSE` |

**Notes:**
- **Legacy MIT text.** The MIT license requires its text and copyright notice to accompany copies. If the legacy AgentVault code is ever published, add an MIT `LICENSE` with the owner's copyright line to those paths. The holder's name is the owner's decision.
- **This map is a description, not legal advice.**
