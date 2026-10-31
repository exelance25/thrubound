// How the ThruBound client reaches a program. Two kinds exist by design:
//   "local-simulation" : the real program code compiled for the host, inside a model of the Thru
//                        runtime (thru/sim). NO signatures, NO network, NO real tokens.
//   "thru-network"     : NOT IMPLEMENTED. A Thru RPC was never reachable from the development
//                        environment, so no network transport could be built and tested honestly.
export interface TxRequest {
  feePayer: Uint8Array;        // the authorizing account (index 0)
  readWrite: Uint8Array[];
  readOnly: Uint8Array[];
  data: Uint8Array;
  label?: string;
}
export interface TxResult { code: number; events: Uint8Array[] }

export interface Transport {
  readonly kind: "local-simulation" | "thru-network";
  readonly programAddress: Uint8Array;
  readonly tokenProgramAddress: Uint8Array;
  send(tx: TxRequest): Promise<TxResult>;
  getAccount(address: Uint8Array): Promise<{ owner: Uint8Array; data: Uint8Array } | null>;
  /** Current chain time in nanoseconds (Thru block_time). */
  now(): Promise<bigint>;
}
