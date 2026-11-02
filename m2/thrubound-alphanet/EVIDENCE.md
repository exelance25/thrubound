# ThruBound on the Thru alphanet — live test evidence (2026-11-01)

**Real network.** These are real transactions on the Thru **alphanet** (test network, chain id 1), run by the public GitHub Actions workflow `alphanet-e2e` in `exelance25/thrubound` (run 41294408870, commit 702d43e). They used:
- throw-away test keys, generated in memory and never printed or saved;
- native THRU from the official faucet;
- a test mint created without a freeze authority.

Nothing touched mainnet. No real funds were used. This is not an audit.

| | |
|---|---|
| Program binary | official toolchain v0.4.2 built on GitHub, **byte-identical** to the pinned sha256 `e0843ea2ac3ef917b765df9f7c8d5706a1d9938888a1a0019bc4726809b127a6` |
| Deployed program | `taSNdMRdDn4VhJzVwTmD7XQeA9rWEv6UPl9tPa5vrCHLGQ` (managed program, official deploy workflow; the upgrade authority was a throw-away key that no longer exists) |
| Result | **42/42 checks PASS** |

**Independent check (2026-11-01, official explorer scan.thru.org, network thru-alphanet):** the program account exists, is flagged Permanent and Program, holds **27,616 bytes** (the exact size of our binary), owner `taMGRmPo…xxHytqmu` (the manager program). It was last updated 2026-11-01 12:45:24 GMT+3.

Explorer: transaction signatures (`ts…`) and addresses (`ta…`) can be looked up at https://scan.thru.org.

## Transactions

| Result | Step | vmError | user error | Signature |
|---|---|---|---|---|
| executed | create EOA owner | 0 | 0x0 | `tsoDSQmufsUc2SuP1CLwvqT7Ut9qJxjNnNVTZOoCaVQd_5AKaOHRz5BFN_QnG7ESb4QfWo4QGH-9pp6bgvnpo6AiD3` |
| executed | create EOA agent | 0 | 0x0 | `tsYqKaHWzvxVEY_NS1KYdrxFJcZtLRqv_vZ972XNfp2wHedAdBGd-jrGgaUMe6UL69In422g0PYgVy6wgH_02kByC_` |
| executed | create EOA vendor | 0 | 0x0 | `ts8u3pGiXv_lzhshvIvbll1T8YUYRmCRczPP5Q_5TtUOqwOaKAsT6cBLFOruMNzWbd2SZnEhL6rZRyQjbI5MZUACFb` |
| executed | create EOA stranger | 0 | 0x0 | `ts0XHFPErlKma4DAXfdkP0vqrm9Y68cO9OzUp_pYnw2YSEmnltqWkV6NZq6F_KifrkuWaUxn53b3EWDprDmnHtCSQ9` |
| executed | faucet native 10000 -> owner (fee 0) | 0 | 0x0 | `tsNULMfSeMvSHeK-zbNLloNIRrvlYzziJWnS1bwvt0vwANcVEIcK-QL7NLxS_d_dQO6C3NHfHi-TCntsODeVODCB-T` |
| executed | faucet native 10000 -> agent (fee 0) | 0 | 0x0 | `tszicG4tgrk1zbIiba99thvCLobm1EOO0PyWL11LhcdIgoObBUec6Xv6xttnsLSvQbwRt7m5kIi4z-41elBDlRBR_m` |
| executed | faucet native 10000 -> stranger (fee 0) | 0 | 0x0 | `tsyX-qG4I5NCCznZqApByMYpzU2CIJsuxyscukXbiP0UuJXEohn_6fCZ3FVE0OESJ5I9qgJeKJku4NwOWSvlMICB77` |
| executed | token initialize_mint (no freeze authority) | 0 | 0x0 | `tszF6s1tkLaO6v5ZxKh85WjAHkzVp6O6kLPQyJKDoKCqHAvCkg-QrSohf-D9arjH52z7msNTNJ5K3lkgepDP5HAh9G` |
| executed | ThruBound INIT_VAULT | 0 | 0x0 | `tslgplwN5jVBaybhoQwcyjIZubv5y8U0WQxCwOL-ykeGMqL5TLSC59gSa-lC1v7Vqjex9diU6hUVdVfqogLXt0DBwe` |
| executed | token initialize_account vaultToken | 0 | 0x0 | `tsjyhWwtu_AVlO0woQyhUv2MAvUUvfbzRE2fdOi27mrX7aBY5rkQP3GCWzS-9_1B3DGqg2u6-lwNl-GzjnZeloDR84` |
| executed | token initialize_account vendorToken | 0 | 0x0 | `tsuRRBB1tIrEKxFTtBLugzifC_cdVrXBzN757YJivqlMnHM9t5Ny1ZmAuZy-W1q4l111kTix94O-T-_yAaPQxnCB4k` |
| executed | token initialize_account strangerToken | 0 | 0x0 | `tsXDN3GFo9hG99hU8vO9-8rluHvCfR27qWPNhcZi14o4ODN7CGIrheCyCONliI_2Rv6V9ekQin-avm6cPRqFfrBx-1` |
| executed | token initialize_account ownerToken | 0 | 0x0 | `tsGpq4oIeQkfND-uQxxs2QKpyDoHS2Rl-xRYHm_U03I7gBcaJufGc4DQsxQmkUaRhpBddgzn-rrmueIyaRrjJcDR0q` |
| executed | token mint_to 1000 -> vaultToken | 0 | 0x0 | `tsIiNof-IqTvaKA96UiQ0Sv4KvNeIIfs_22eZAYbSgbXStFT9Dlyr9KykvNZ8-3z_QmGRkpP_mjdqo6PZMJi-uCx-_` |
| executed | ThruBound BIND_TOKEN (+ mint unfreezable check) | 0 | 0x0 | `tsP-woMDaZFhfkSg6gtSavYoJv98PoItOmhYwjlmNFZ2Ebis5NuQ-ihhokNACEaoiMKuNsH5R9Fh2yDE6k8nrTAhug` |
| executed | ThruBound SET_AGENT (create) | 0 | 0x0 | `tsXKXZSocDYD9c0kvR_w7ktbGM0sa8gIYJRZ991XTZABqhTMsP7v1caxXfufyo0lKcl1krM1CEdnYDteNec5s4BCBV` |
| executed | ThruBound SET_RECIPIENT vendorToken | 0 | 0x0 | `tsgSsx4sctZ3awuv3OJ4Qm1FnWxYjZ6zx4HrckGCiY5n1lf2_wo_0PDC8Q9-wgkKD6WqxP6_pJYOeJcnQ5HLiIAiDM` |
| executed | agent pays vendor 5 (instant) | 0 | 0x0 | `tsB60ApdnH5LaiJR3cbD-WKYQK6Ymqpx68jSx-iPVMqMKV1rbX3DJmpO_zsgo0f1XLSutEZAkTUfm7zjjnPULGBCEH` |
| refused | agent tries 11 (> per-payment 10) | -765 | 0x100f | `tsxQa3XPnQw00x3zq4PvsRdguvUBdJaKWAHlzxSkMcEHQ4kgxn3lG458bEiqvkbkc_uLRRmLffZizyEvxrp-VCBx9n` |
| refused | agent pays a stranger | -765 | 0x100e | `tspseDffOurvMYZM_GYhb5VUQ0LPmFJnAQ8nVOWx_OnImyr9e8WJGZGbogSFe2gSBC6Wgx_Rhmua3ZQKjs7Uz5CiFd` |
| refused | agent replays nonce 0 | -765 | 0x100c | `tsakW_gCepA3_IvxRk2UipHgk6FFQAhRMWJyc4tdS1CdQ45QExAr8zuFiWps1NZuR8y9zbxi87UNI0Wa-JabzfBxw0` |
| refused | stranger signs as the agent | -765 | 0x1004 | `ts92hyNctEcUSG-6g1ozaXSLMmAAXHJ3__IIsdm5kUC7lppq97A3K8m72JY0FwsvKChP4uQsg9LZQFL4BF-y9XARy2` |
| executed | agent asks 9 (above threshold 5 -> pending) | 0 | 0x0 | `tsX11BesQNHG7pkzLl25V_P9UQ0VOXV3BEmIC_2pIQLAEaygZ9mSx5bJ-WN_kuE_tFXQimlHs4fFEpOtQUFMe3DxvA` |
| refused | owner approves a tampered amount (8) | -765 | 0x1017 | `tsDI2oy5FOcMyeQwjFL46aaIc-x4IwZDfHVWOwMybIY_mBpYqraIjEgTFb7Lk8p-L5Aa1EvA_Jt0GgN0FuN99IBR7_` |
| executed | owner approves exactly the pending request | 0 | 0x0 | `tsshFhkmX3mfe6Fn65OFiIw7wJ7r0GLE8H4EnJ5oYlqYYyIyB6OzM4YotHUxK6slhiiUYSznynMsCNUPZpb-g_BB0c` |
| refused | owner approves the same request again | -765 | 0x1013 | `tszFV51LTydIiz2vqQsGSGljAKIr7-UR0XmRIHhwnTInanDnKEcJsmvpCfgBcJ07sdm-vi6NMsBP_zXwZM0Z0uDB9T` |
| refused | token transfer vault->owner, owner signs | -765 | 0x7 | `tsELNwAdgS7HuC-k4EvaqAygLPWdsTr-d36X-8lzdy9XRXbb9UCJsieAN1HQRtigYa78LD7Sn1alOQxPig5wB4BB9F` |
| refused | token burn vault, vault PDA named as authority (unsigned) | -765 | 0x7 | `tstpqh9Wlwdl1aKQkS3u1MLQBoBCjDxMQnXkn1oRtmphFKJrZAJ-xAw5GjgISUe1-b3ysAoHh5Oh5jpUujMHxUChuf` |
| refused | token burn vault, owner as authority | -765 | 0x5 | `tsRzmKNQRNKHo-ZWW7PwLtVbrFj81xFXT6OhH3SFzGUKUq4DGtoALlQ-xnIJoNWSFRqmPsvEhW05hETNAKlZbjChy_` |
| refused | token close_account vault -> owner | -765 | 0xb | `ts-dTyKriKUTLfi5XRkBGW8ZSTbh1__edHUFdf0M9VEVguvARWHE6qnkSOxTO0sFsQ1N6beNyyZvRnUhGu8Vr1CiFj` |
| refused | token freeze vault (mint has no freeze authority) | -765 | 0x12 | `tsSSTvfNxNQHzXagJfusxg5p3oa46fUs7py-Ao4fJQfTxfWvBbbBBwRs2qqJsgRt9f6wodc37dzB0F1F_2rTMYBSCI` |
| refused | token transfer vault->agent token, agent signs | -765 | 0x7 | `tsbEMk7rplUlk4ipqffiVEIf2bP90qt3kI3JZCG2AgVdGLvBHw1srV5Lwr2eTwaNCucAo3sWf0qEnNpTgEkHJkCyAB` |
| executed | ThruBound REVOKE | 0 | 0x0 | `ts5uW1l5yxEUWM0H2NZsjAxzP9IQ-iimJO7w327CokUfiZKDa6iEDtFXvjlrMLMEs1scJ6LcJN3w3F36Ewf-ZYCyC1` |
| refused | revoked agent tries to pay 1 | -765 | 0x100a | `tsX2GmsVF2BUh0J422LOQXqfI--aTg2_B7W5vGUsSrN3vwxJ1onDeuKQEUALDMmXlwA7iKNjMoMTph-sxYv4PsAx9i` |
| executed | ThruBound WITHDRAW 100 | 0 | 0x0 | `tsJCdM5Vy9-vc-WIUMUVNOIXu93WNtIiWKSybpUCkwvP3e5c7UnKVFBOMhDHD8G80ckWwxY7GwVgYUGoYMWJknBhvN` |

## Checks

| Result | Check | Detail |
|---|---|---|
| PASS | create EOA owner succeeds | vmError=0 user=0 |
| PASS | create EOA agent succeeds | vmError=0 user=0 |
| PASS | create EOA vendor succeeds | vmError=0 user=0 |
| PASS | create EOA stranger succeeds | vmError=0 user=0 |
| PASS | faucet native THRU to owner | vmError=0 user=0 |
| PASS | faucet native THRU to agent | vmError=0 user=0 |
| PASS | faucet native THRU to stranger | vmError=0 user=0 |
| PASS | token initialize_mint (no freeze authority) succeeds | vmError=0 user=0 |
| PASS | test mint has no freeze authority | {"decimals":0,"supply":"0","creator":"taX10LLQwX8ZXbZjK7U0poVaJ7GS153YJqn6PYFznglKBI","mintAuthority":"taX10LL |
| PASS | program deployed via official deploy workflow | program=taSNdMRdDn4VhJzVwTmD7XQeA9rWEv6UPl9tPa5vrCHLGQ sha256=e0843ea2ac3ef917b765df9f7c8d5706a1d9938888a1a001 |
| PASS | deployed image hash equals local build | e0843ea2ac3ef917b765df9f7c8d5706a1d9938888a1a0019bc4726809b127a6 vs e0843ea2ac3ef917b765df9f7c8d5706a1d9938888 |
| PASS | ThruBound INIT_VAULT succeeds | vmError=0 user=0 |
| PASS | token initialize_account vaultToken succeeds | vmError=0 user=0 |
| PASS | token initialize_account vendorToken succeeds | vmError=0 user=0 |
| PASS | token initialize_account strangerToken succeeds | vmError=0 user=0 |
| PASS | token initialize_account ownerToken succeeds | vmError=0 user=0 |
| PASS | token mint_to 1000 -> vaultToken succeeds | vmError=0 user=0 |
| PASS | ThruBound BIND_TOKEN (+ mint unfreezable check) succeeds | vmError=0 user=0 |
| PASS | ThruBound SET_AGENT (create) succeeds | vmError=0 user=0 |
| PASS | ThruBound SET_RECIPIENT vendorToken succeeds | vmError=0 user=0 |
| PASS | agent pays vendor 5 (instant) succeeds | vmError=0 user=0 |
| PASS | vendor received 5 |  |
| PASS | over-limit payment is refused on chain | vmError=-765 userErrorCode=0x100f expected 0x100f |
| PASS | payment to a non-allowlisted recipient is refused on chain | vmError=-765 userErrorCode=0x100e expected 0x100e |
| PASS | replayed nonce is refused on chain | vmError=-765 userErrorCode=0x100c expected 0x100c |
| PASS | request signed by someone else is refused on chain | vmError=-765 userErrorCode=0x1004 expected 0x1004 |
| PASS | agent asks 9 (above threshold 5 -> pending) succeeds | vmError=0 user=0 |
| PASS | tampered approval is refused on chain | vmError=-765 userErrorCode=0x1017 expected 0x1017 |
| PASS | owner approves exactly the pending request succeeds | vmError=0 user=0 |
| PASS | vendor balance 14 after approval |  |
| PASS | second approval is refused on chain | vmError=-765 userErrorCode=0x1013 expected 0x1013 |
| PASS | KSI-1 direct transfer by the owner key is refused on chain | vmError=-765 userErrorCode=0x7 |
| PASS | KSI-1 burn with the vault as unsigned authority is refused on chain | vmError=-765 userErrorCode=0x7 |
| PASS | KSI-1 burn by the owner key is refused on chain | vmError=-765 userErrorCode=0x5 |
| PASS | KSI-1 close of the vault token account is refused on chain | vmError=-765 userErrorCode=0xb |
| PASS | KSI-1 freeze of the vault token account is refused on chain | vmError=-765 userErrorCode=0x12 |
| PASS | KSI-1 direct transfer by the agent key is refused on chain | vmError=-765 userErrorCode=0x7 |
| PASS | vault balance unchanged by the KSI-1 probes (986) |  |
| PASS | ThruBound REVOKE succeeds | vmError=0 user=0 |
| PASS | payment after revocation is refused on chain | vmError=-765 userErrorCode=0x100a expected 0x100a |
| PASS | ThruBound WITHDRAW 100 succeeds | vmError=0 user=0 |
| PASS | final balances vault 886 / vendor 14 / owner 100 | {"vault":"886","vendor":"14","owner":"100"} |

## Codes

- **ThruBound revert codes:** 0x1004 NOT_AGENT, 0x100a UNKNOWN_AGENT (revoked), 0x100c BAD_NONCE, 0x100e RECIPIENT_NOT_ALLOWED, 0x100f PER_TX, 0x1013 NO_PENDING, 0x1017 APPROVAL_MISMATCH (`thru/program/flowstate_core.h`).
- **Token program refusals (KSI-1 probes):** 0x5, 0x7, 0xb and 0x12 are the token program's own error codes. Their meanings are not documented publicly; what matters is that each probe reverted and the vault balance stayed at 986.
- **Runtime codes:** vmError -765 = VM_REVERT (the program refused). Every refused step reverted completely (H1).
