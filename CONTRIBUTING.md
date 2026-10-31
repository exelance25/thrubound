# Contributing to ThruBound

Thanks for looking. ThruBound is an **early research prototype** (v0.1.0-alpha). The most useful contributions right now are **reviews and evidence, not features**.

## Most wanted

1. **Token-program authority paths (KSI-1).** Is there any way to transfer, burn, close, freeze or delegate a token account owned by a program-derived address without that program authorising it?
2. **Runtime assumptions:**
   - H2: are transactions on the same writable accounts applied serially?
   - H3: is block time monotonic?
3. **Running the program on a real Thru VM or test network.** Report what happens, with logs. Use test tokens only.
4. **Independent setup reports.** Follow `docs/DEVELOPER_PACKAGE.md` and tell us where it broke or was unclear.
5. **Review of the abstract model** (`thru/proof/inductive_smt.py`) against the C code (`thru/program/flowstate_core.c`).

Please open an issue before starting a large change. New features are unlikely to be accepted until the open questions above are answered.

## Ground rules

- **Never** commit private keys, seed phrases, `.env` files, RPC credentials or wallet files. The Thru CLI writes a key file to `~/.thru/cli/config.yaml`; keep it out of the repository.
- **Never** present simulated results as network results. Label evidence `PASS`, `FAIL`, `BLOCKED` or `NOT RUN`, and say where it ran (local simulation, official toolchain, or which network).
- **Do not loosen tests to make them pass.** A failing security test is a finding.
- **All rules must be enforced by the on-chain program**, not by the SDK.

## Before you open a pull request

```bash
bash thru/run_all_tests.sh      # must end with ALL CHECKS PASSED
```

- If you change the program (`thru/program/`), also:
  - regenerate the SDK ABI: `cd thru/sdk && npm run build`;
  - keep the conformance test and the SMT model in step;
  - report the new ThruVM binary hash from `thru/scripts/build_official.sh`.
- Add a test for every bug fix. Security fixes need an adversarial test that fails before the fix.
- Update `CHANGELOG.md`, and `docs/KNOWN_LIMITATIONS.md` if a limitation changes.

## Licensing of contributions

By contributing, you agree that your contribution is licensed under the Apache License 2.0 (see `LICENSE`), as described in section 5 of that license.

## Security issues

Do not open a public issue for a vulnerability. See `SECURITY.md`.
