// LOCAL SIMULATION transport: loads thru/build/host/libflowstate_sim.so (the real program code
// compiled for the host, linked with the simulated Thru runtime in thru/sim) through koffi.
// Everything here is a simulation: there are no signatures, no network and no real tokens.
// Test fixtures (mints, token accounts, balances) stand in for token-program setup instructions.
import { writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import type { Transport, TxRequest, TxResult } from "./transport.js";
import { sha256 } from "./codec.js";

const require = createRequire(import.meta.url);
const koffi = require("koffi");

const hex = (b: Uint8Array) => Buffer.from(b).toString("hex");

export interface LocalSimulationOptions {
  /** Path to libflowstate_sim.so (built by thru/build_host.sh). */
  library: string;
  /** Label from which the simulated program address is derived. */
  programLabel?: string;
  /** Initial chain time in ns. */
  startTimeNs?: bigint;
}

export class LocalSimulationTransport implements Transport {
  readonly kind = "local-simulation" as const;
  readonly programAddress: Uint8Array;
  readonly tokenProgramAddress: Uint8Array;
  private lib: any;
  private fn: Record<string, any>;
  private clockNs: bigint;
  private slot = 1n;
  private trace: object[] = [];

  constructor(opts: LocalSimulationOptions) {
    this.lib = koffi.load(opts.library);
    const L = this.lib;
    this.fn = {
      reset: L.func("void sim_reset(const uint8_t *program)"),
      tokenProgram: L.func("void sim_token_program(_Out_ uint8_t *out)"),
      setClock: L.func("void sim_set_clock(unsigned long slot, unsigned long ns)"),
      put: L.func("int sim_put_account(const uint8_t *addr, const uint8_t *owner, const uint8_t *data, unsigned long sz)"),
      get: L.func("int sim_get_account(const uint8_t *addr, _Out_ uint8_t *owner, _Out_ uint8_t *data, unsigned long cap, _Out_ unsigned long *sz)"),
      exec: L.func("unsigned long sim_exec(const uint8_t *program, const uint8_t *payer, const uint8_t *rw, int rwn, const uint8_t *ro, int ron, const uint8_t *ix, unsigned long sz)"),
      evCount: L.func("int sim_event_count()"),
      ev: L.func("unsigned long sim_event(int i, _Out_ uint8_t *program, _Out_ uint8_t *out, unsigned long cap)"),
    };
    this.programAddress = sha256(new TextEncoder().encode("flowstate-sim-key/" + (opts.programLabel ?? "thrubound-local-sim")));
    this.fn.reset(Buffer.from(this.programAddress));
    const tp = Buffer.alloc(32);
    this.fn.tokenProgram(tp);
    this.tokenProgramAddress = new Uint8Array(tp);
    this.clockNs = opts.startTimeNs ?? 1_900_000_000n * 1_000_000_000n;
    this.fn.setClock(this.slot, this.clockNs);
  }

  async send(tx: TxRequest): Promise<TxResult> {
    const cat = (xs: Uint8Array[]) => Buffer.concat(xs.map((x) => Buffer.from(x)));
    const code = Number(this.fn.exec(Buffer.from(this.programAddress), Buffer.from(tx.feePayer), cat(tx.readWrite), tx.readWrite.length,
      cat(tx.readOnly), tx.readOnly.length, Buffer.from(tx.data), tx.data.length));
    const events: Uint8Array[] = [];
    const n = this.fn.evCount();
    for (let i = 0; i < n; i++) {
      const prog = Buffer.alloc(32), buf = Buffer.alloc(512);
      const len = Number(this.fn.ev(i, prog, buf, 512));
      events.push(new Uint8Array(buf.subarray(0, len)));
    }
    this.trace.push({ label: tx.label ?? "", slot: this.slot, time_ns: this.clockNs, program: hex(this.programAddress),
      fee_payer: hex(tx.feePayer), instr: hex(tx.data), rc: code, events: events.map((e) => ({ program: hex(this.programAddress), data: hex(e) })) });
    return { code, events };
  }

  async getAccount(address: Uint8Array) {
    const owner = Buffer.alloc(32), data = Buffer.alloc(1024), sz = [0];
    if (!this.fn.get(Buffer.from(address), owner, data, 1024, sz)) return null;
    return { owner: new Uint8Array(owner), data: new Uint8Array(data.subarray(0, Number(sz[0]))) };
  }

  async now() { return this.clockNs; }

  // ---------------------------------------------------------------- simulation-only controls
  /** Move the simulated clock (ns). */
  setTime(ns: bigint) { this.clockNs = ns; this.slot += 1n; this.fn.setClock(this.slot, ns); }
  advanceSeconds(s: number) { this.setTime(this.clockNs + BigInt(s) * 1_000_000_000n); }
  /** Fixture: a token mint account laid out per the official token ABI (115 bytes). */
  createTestMint(mint: Uint8Array, authority: Uint8Array, freezeAuthority: Uint8Array | null = null) {
    const d = Buffer.alloc(115);
    d[0] = 6; /* decimals */ Buffer.from(authority).copy(d, 9); Buffer.from(authority).copy(d, 41);
    if (freezeAuthority) { Buffer.from(freezeAuthority).copy(d, 73); d[105] = 1; }
    d[106] = 4; d.write("TEST", 107);
    this.put(mint, this.tokenProgramAddress, d);
  }
  /** Fixture: a token account (stands in for the token program's initialize_account + mint_to). */
  createTestTokenAccount(address: Uint8Array, mint: Uint8Array, owner: Uint8Array, amount: bigint) {
    const d = Buffer.alloc(73);
    Buffer.from(mint).copy(d, 0); Buffer.from(owner).copy(d, 32); d.writeBigUInt64LE(amount, 64);
    this.put(address, this.tokenProgramAddress, d);
  }
  /** Fixture: any account with raw data (e.g. another program's state for analysis tests). */
  createRawAccount(address: Uint8Array, owner: Uint8Array, data: Uint8Array) { this.put(address, owner, Buffer.from(data)); }
  private put(addr: Uint8Array, owner: Uint8Array, data: Buffer) {
    if (this.fn.put(Buffer.from(addr), Buffer.from(owner), data, data.length) !== 0) throw new Error("sim_put_account failed");
  }
  /** Write the executed transactions as JSONL, the format thru/verifier/verify_thru.py checks. */
  saveTrace(path: string, snapshot?: object) {
    // u64 values (ns timestamps) exceed 2^53, so bigints are written as exact JSON integers
    const j = (o: object) => JSON.stringify(o, (_k, v) => (typeof v === "bigint" ? `__u64__${v}` : v)).replace(/"__u64__(\d+)"/g, "$1");
    const lines = this.trace.map(j);
    if (snapshot) lines.push(j({ snapshot }));
    writeFileSync(path, lines.join("\n") + "\n");
  }
}
