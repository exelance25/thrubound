// ThruBound SDK — public entry point. Only what is exported here is supported API.
export { ThruBound } from "./client.js";
export type { Address, Limits, Receipt, Permission, PendingRequest } from "./client.js";
export type { Transport, TxRequest, TxResult } from "./transport.js";
export type { Decision } from "./policy.js";
export type { AuthorityReport, Finding, Mover, Status, Evidence, EvidenceKind } from "./authority.js";
export { LocalSimulationTransport } from "./local-simulation.js";
export type { LocalSimulationOptions } from "./local-simulation.js";
