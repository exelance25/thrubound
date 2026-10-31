# ThruBound — Phase 7: community validation and network diagnostics (2026-10-31)

**Scope.** No new features. The program, simulation, tests, proof and SDK are unchanged since `78ce2c5`. This phase added:
- documentation;
- a one-command test runner;
- pinned evidence;
- read-only network health checks.

**Not done, as instructed:**
- nothing was posted or sent, and no Discord or social account was used;
- nothing was uploaded, deployed or transacted;
- no wallet, key, fund, paid service, VPS or proxy was used.

## Summary answers

| Question | Answer |
|---|---|
| **Ready for community presentation?** | **Almost, not yet.** The content is ready: an honest README, an intro draft, Q&A, a developer package and pinned evidence. Three owner actions remain: (1) **publish a repository**, since none exists (§A1); (2) **choose a license**, since none exists and two different ones are declared (§A3); (3) review and post the drafts yourself. |
| **Real network access achieved?** | **Read-only only, from the user's own network.** Through the desktop app's built-in browser, both official RPCs answered gRPC-Web health queries: alphanet chain id 1, betanet chain id 2, blocks advancing. **From the two sandbox environments (cloud workspace and linked-computer shell): no access.** No program interaction of any kind. |
| **Cause of the network errors found?** | **Yes, with evidence.** The Thru servers are up. Both sandboxes block the hosts at their egress proxy: the linked-computer proxy says `403 Forbidden, X-Proxy-Error: blocked-by-allowlist`; the cloud gateway answers 403 to `CONNECT`. Neither resolves DNS for outside hosts, which is why the official CLI (gRPC, direct DNS lookup) fails with `dns error`. These are **environment policy** errors, not Thru outages and not our code (§B). |
| **Missing for an independent developer test?** | (1) A public repository URL. (2) An actual independent person: only the author has run the setup. (3) WSL: documented but untested; Windows native unsupported. (4) A clean-OS run: the runner was tested from a fresh clone, but on the author's prepared machine (§D). |
| **Security claims still unverified?** | KSI-1 (token-program authority paths); H2 (serial effect); H3 (monotonic time); execution on a Thru VM; Passkey `invoke` approval; Rate Limiter composition; upgrade authority; current program addresses; that the C code equals the proved model (tested only). **No audit, no formal verification of the program.** (§C) |

## A. Community preparation

### A1. Repository address — none exists

| Place checked | Result |
|---|---|
| Cloud workspace repository | no `git remote` configured |
| User's local copy `C:\Users\<user>\Projects\agentvault` | no remote; branch `mvp-app` at `14f1bf1` |
| The owner's GitHub account | no repository for this project; `thrubound`, `agentvault` and `flowstate` all return 404 |

**Conclusion.** The project is not on GitHub, or at least not publicly under that account. The announcement draft contains a `<REPO_URL>` placeholder. **Creating or pushing a repository is an external action and was not done.** The owner must decide:
- the account;
- public or private;
- whether to publish all branches, including the legacy EVM history, or only `feature/thrubound`.

### A2. Demo page and README currency

| Item | Before | Now |
|---|---|---|
| `README.md` | Legacy EVM AgentVault README with a short ThruBound pointer (onboarding friction F1, only partly fixed) | **Rewritten for ThruBound:** what it does, what it does not do, "not a replacement for Rate Limiter / Passkey Manager", limitations, evidence table, "test results are not network verification". The legacy README was moved unchanged to `docs/legacy/AGENTVAULT_README.md` |
| `thru/demo` | Current. It uses the public SDK and says LOCAL SIMULATION; its API test passes | unchanged |
| `examples/subscription-payer` | Current; passes; the verifier passes on its trace | unchanged |

### A3. License — owner decision needed

There is **no LICENSE file**. Two different licenses are declared:
- `thru/sdk/package.json` and the example app say `Apache-2.0`;
- the root `package.json` (legacy) says `MIT`.

The vendored official Thru C SDK carries its own license. Choosing a license is the owner's call; nothing was added. The README says "not yet decided".

### A4–A7. Drafts

- `docs/community/ANNOUNCEMENT_DRAFT.md`: natural, technical English intro, marked **DRAFT, not sent**. It:
  - states the problem (unbounded signing sessions) and what ThruBound does and does not do;
  - says plainly that it has never run on Thru, and what the proofs are and are not;
  - asks the community three concrete questions: token-program bypass paths, H2/H3, and whether they would use it.
- `docs/community/TECHNICAL_QA.md`: five short answers:
  1. why not the Rate Limiter;
  2. has it run on Thru;
  3. what was proved;
  4. can a leaked agent key drain the vault;
  5. daily limit, concurrency and upgrades.

## B. Network diagnosis (read-only)

The official endpoints were taken from `thru.org/docs` → gRPC API:
- `https://rpc.alphanet.thru.org`
- `https://rpc.betanet.thru.org`

Both serve gRPC and gRPC-Web. Each layer was checked separately. Evidence: `m2/thrubound-phase7/net-*.{txt,json}`.

| Check | Cloud workspace | Linked-computer shell (sandbox VM) | User's own network (desktop app browser) |
|---|---|---|---|
| DNS | **FAIL**: no answer for `*.thru.org`. GitHub resolves (control) | **FAIL**: no answer for any outside host, GitHub included | **PASS** (implied by the HTTP responses; the browser does not expose DNS separately) |
| TCP :443 direct | **FAIL**: `gaierror` (no DNS) | **FAIL**: `gaierror` | PASS (implied) |
| Through the environment's proxy | **FAIL**: gateway `403` to `CONNECT rpc.alphanet/betanet.thru.org:443` ("policy denial or upstream failure") | **FAIL**: `HTTP/1.1 403 Forbidden`, **`X-Proxy-Error: blocked-by-allowlist`**; GitHub through the same proxy: 200 | not applicable |
| TLS | **NOT RUN** (the tunnel is refused before TLS) | **NOT RUN** (same) | **PASS** (HTTPS responses received) |
| Official RPC addresses current? | — | — | **PASS**: both answer as the docs say. A JSON request gets 415 `application/grpc`; a gRPC-Web request gets 200, `grpc-status 0` |
| Official CLI `thru getversion` | **FAIL**: `dns error … Name or service not known` (CLI 0.4.2+e47b2a21) | **FAIL**: `dns error … Temporary failure in name resolution` (CLI 0.4.2+a058dd8e, release `.deb`, checksum matched) | **NOT RUN**: no shell on the user's real OS |
| Network health | — | — | **PASS**. Alphanet: chain id 1, node commit `0b8717c5` (2026-10-24), height 4,180,897 → 4,180,932 in 8.9 s. Betanet: chain id 2, node `ab92c055` (2026-10-29), 9,713,671 → 9,713,706 in 8.9 s |

**Root cause (evidence-based).** The Thru RPCs are up and reachable from the user's own network. Both automation environments are sandboxes whose egress goes through an allowlisting proxy that does not include `*.thru.org`:
- the linked computer states this explicitly (`blocked-by-allowlist`);
- the cloud gateway's 403 says "policy denial or upstream failure". Given that the browser reached the same hosts at the same minute, upstream failure is unlikely, but the gateway does not say which.

The official CLI fails earlier still. Its gRPC client resolves DNS directly instead of using the HTTP proxy, and the sandboxes have no outside DNS.

**Remaining caveats:**
- Protobuf fields were decoded by field number, without `.proto` files.
- "Height" is the documented meaning of field 1, not confirmed from a schema.
- Nothing was checked beyond health: no accounts, programs or transactions.

**Ways to real network work.** None was taken; each needs the owner's decision.
1. Run the official CLI on the user's own OS: Linux, or WSL2 on the user's PC. The browser test shows that network can reach the RPCs.
2. Ask for `*.thru.org` on the sandbox allowlist, where the operator allows it.

Deployment or any transaction still needs separate explicit approval (Phase 6 rule).

## C. Pinned evidence

Everything is in `m2/thrubound-phase7/EVIDENCE_MANIFEST.md`:
- commit `78ce2c5` and source hashes;
- official toolchain gcc 15.2.0 (`g5115c7e44`). The binary was **rebuilt today, byte-identical** (sha256 `4f499419…5e14`);
- CLI 0.4.2;
- C SDK v0.4.2, `@thru/sdk` and `@thru/programs` 0.4.2;
- the full test rerun (11/11 PASS);
- model check depth 6;
- 20,000-trial conformance;
- z3 output with the script hash;
- known vulnerabilities and unverified claims.

**When 92/92 holds.** It holds for the **abstract model** only, for all u64 values, under assumptions H1–H6:
- H1 (failure atomicity) and H4 (account ownership) come from the official docs;
- H5 (token authority) is partly inferred;
- H2 (serial effect) and H3 (monotonic time) are unverified;
- H6 (C = model) is tested, not proved.

It is **not** a formal proof of the C program, the RISC-V binary, the token program or the runtime.

## D. Independent developer package

| Item | Where | State |
|---|---|---|
| Linux install steps | `docs/DEVELOPER_PACKAGE.md` §1 | tested by the author (Ubuntu 24.04) |
| WSL install steps | §2 | **written, not tested** |
| Windows native | §Platform support | **not supported** (stated) |
| One-command run | `bash thru/run_all_tests.sh` (`QUICK=1` for faster) | PASS 11/11; from a fresh `git clone` of the branch into an empty folder, `QUICK=1` run: 10/10 PASS |
| Example app | `examples/subscription-payer` (§4) | PASS |
| Expected output | `thru/run_all_tests.expected.txt` | recorded |

## E. Status

| Evidence level | Claims |
|---|---|
| Real Thru network | **Read-only health only**: both official RPCs up (browser, user's network). Nothing about ThruBound has been verified on a network |
| Official tools | Reproducible build (rebuilt today); CLI image validation |
| Local simulation | All tests, model check, mutation, verifier, SDK, example, demo |
| Mathematical, abstract model | 92/92 SMT obligations under H1–H6 |
| Unverified | KSI-1, H2, H3, VM execution, Passkey `invoke`, Rate Limiter composition, upgrade authority, program addresses, demand, independent onboarding |

**Next steps need the owner.** None was taken.
1. Choose a license.
2. Create and publish the repository.
3. Review and post the drafts yourself.
4. Optionally run the read-only CLI checks on your own machine (WSL).
5. Find one independent developer to follow `DEVELOPER_PACKAGE.md`.
