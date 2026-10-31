// Pure, side-effect-free prediction of what the program will decide for a payment request.
// It mirrors fs_request() in thru/program/flowstate_core.c and is checked against the real program
// code by a differential test (test/differential.test.mjs). The program remains the authority:
// this function never replaces an on-chain check.
import { C } from "./abi.generated.js";
import type { AgentState, VaultState } from "./codec.js";

export const NS_PER_DAY = BigInt(C.FS_NS_PER_DAY);
const U64_MAX = 0xffffffffffffffffn;

export type Decision =
  | { outcome: "instant"; reason: null }
  | { outcome: "pending"; reason: null }
  | { outcome: "refused"; reason: string };

const refuse = (code: number): Decision => ({ outcome: "refused", reason: errorName(code) });
export const errorName = (code: number) => {
  for (const [k, v] of Object.entries(C)) if (k.startsWith("FS_ERR_") && v === code) return k.slice(7);
  return `0x${code.toString(16)}`;
};

export function predictRequest(vault: VaultState | null, agent: AgentState | null, vaultAddress: Uint8Array,
  req: { recipient: Uint8Array; amount: bigint; nonce: bigint; nowNs: bigint }): Decision {
  if (!vault) return refuse(C.FS_ERR_NOT_INITIALIZED);
  if (vault.flags & C.FS_VAULT_KILLED) return refuse(C.FS_ERR_KILLED);
  if (vault.flags & C.FS_VAULT_PAUSED) return refuse(C.FS_ERR_PAUSED);
  if (vault.tokenAccount.every((b) => b === 0)) return refuse(C.FS_ERR_TOKEN_NOT_BOUND);
  if (!agent || !agent.active) return refuse(C.FS_ERR_UNKNOWN_AGENT);
  if (!agent.vault.every((b, i) => b === vaultAddress[i])) return refuse(C.FS_ERR_WRONG_VAULT);
  if (req.nowNs >= agent.validUntilNs) return refuse(C.FS_ERR_AGENT_EXPIRED);
  if (req.nonce !== agent.nextNonce) return refuse(C.FS_ERR_BAD_NONCE);
  if (req.amount === 0n) return refuse(C.FS_ERR_ZERO_AMOUNT);
  const allowed = !req.recipient.every((b) => b === 0) && agent.recipients.some((r) => r.every((b, i) => b === req.recipient[i]));
  if (!allowed) return refuse(C.FS_ERR_RECIPIENT_NOT_ALLOWED);
  if (req.amount > agent.perTx) return refuse(C.FS_ERR_PER_TX);
  const today = req.nowNs / NS_PER_DAY;
  const usedToday = agent.day === today ? agent.dailyUsed : 0n;
  const used = usedToday + req.amount;
  if (used > U64_MAX) return refuse(C.FS_ERR_OVERFLOW);
  if (used > agent.daily) return refuse(C.FS_ERR_DAILY);
  const total = agent.spent + agent.reserved + req.amount;
  if (agent.spent + agent.reserved > U64_MAX || total > U64_MAX) return refuse(C.FS_ERR_OVERFLOW);
  if (total > agent.budget) return refuse(C.FS_ERR_BUDGET);
  if (agent.nextNonce === U64_MAX) return refuse(C.FS_ERR_OVERFLOW);
  if (req.amount <= agent.threshold) {
    if (vault.totalPaid + req.amount > U64_MAX) return refuse(C.FS_ERR_OVERFLOW);
    return { outcome: "instant", reason: null };
  }
  return { outcome: "pending", reason: null };
}

/** What the agent can still spend right now, from on-chain state (never negative). */
export function remaining(agent: AgentState, nowNs: bigint) {
  const today = nowNs / NS_PER_DAY;
  const usedToday = agent.day === today ? agent.dailyUsed : 0n;
  const committed = agent.spent + agent.reserved;
  const max0 = (x: bigint) => (x > 0n ? x : 0n);
  return { today: max0(agent.daily - usedToday), lifetime: max0(agent.budget - committed), perTransaction: agent.perTx };
}
