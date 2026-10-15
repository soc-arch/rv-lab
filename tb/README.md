# Reusable hardware harness

The default CPU is the verified P1 static core. `PRESET=ant_j0`
(`LAB_CORE_PRESET=ant_j0`) selects ANT with early JAL disabled; `btfnt_j0`
selects BTFNT. Optional `ant_j1`/`btfnt_j1` retain early JAL comparisons.
These are actual elaboration parameters, recorded with source/configuration
hashes in every hardware build receipt and result. `core_config.py` is shared
by application and independent protocol tests.

The default `MEMORY_ADAPTER=ii1` (`LAB_MEMORY_ADAPTER=ii1`) selects
`tb/teaching_sram.sv`, copied unchanged from the verified P1 harness. Select
`MEMORY_ADAPTER=frozen` for the former adapter preserved under
`reference/legacy_teaching_51562ce/tb/teaching_sram.sv`. Adapter selection is
independent of the software and CPU preset and participates in the build key.

Optional student performance collection uses `+perf_addr=<hex>` and
`+perf_file=<path>` to dump the 16-word LPM1 CSR record from SRAM at termination.
The address must be 16-byte aligned and within SRAM. The runner verifies that
this record is outside the functional signature. This reads software-written
SRAM; no CPU hierarchy or new core port is used. Missing/incomplete measurements
remain visibly unavailable. `+commit_file=<path>` records every actual retirement,
independently of the bounded detailed cycle trace. The runner exposes it through
`COMMITS=1` and cross-checks both full-run and ROI log counts against TB counters.

`tb_cpu_lab.sv` connects one complete `teaching_cpu` to one shared synchronous
`teaching_sram` through independent instruction/data memory-v1 request and
response channels. It uses only public CPU ports. `sim_main.cpp` drives clock/reset;
there is no DPI dependency. The Python runner normally supplies all arguments.

| Plusarg | Meaning |
|---|---|
| `+program=path` | Required byte-oriented Verilog hex; `@` indices are offsets from SRAM base |
| `+tohost=hex` | Required address of the aligned 64-bit ELF completion variable |
| `+signature_begin=hex`, `+signature_end=hex`, `+dump_file=path` | Dump the half-open signature region, one 32-bit hex word per line |
| `+result_file=path` | JSON termination summary, cycle/retirement counts and optional ROI |
| `+timeout=N` | Hardware cycle budget, excluding reset; default 1,000,000 |
| `+reset_cycles=N` | Rising edges with reset asserted; default 4, minimum 1 |
| `+trace_file=path`, `+trace_limit=N` | Per-cycle JSONL; default capture limit 20,000 records |
| `+trace_start_pc=hex` | Start capture when that instruction enters execution; omit to include startup |
| `+commit_file=path` | All architectural commits, independent of detailed trace capture limits |
| `+roi_begin_addr=hex`, `+roi_end_addr=hex` | Addresses of 32-bit begin/end marker variables |
| `+wave=path.fst` | Optional detailed waveform; build with `--trace-fst` |
| `+i_latency=N`, `+d_latency=N` | First response edge minus request-acceptance edge; minimum/default 1 |
| `+i_interval=N`, `+d_interval=N` | Minimum spacing between accepted requests on each physical port; minimum/default 1 |
| `+stall_seed=N`, `+stall_max=N` | Independent deterministic request-stall sequences per port; defaults 1 and 0 |
| `+i_error_addr=hex` | Inject an instruction response error at this exact byte address |
| `+d_error_addr=hex`, `+d_error_write=N` | Inject a data response error; access filter -1=both, 0=read, 1=write |
| `+error_once=1` | Inject at most one matching error per port; default 0 repeats matching errors |

Timing values and `stall_max` are bounded at 1,000,000 cycles. Each memory port
reserves one response slot until its response handshake. Consequently the blocking
profile may accept requests less frequently than `interval` alone permits. For
example, latency 3 does not imply one request per cycle when there is only one
live slot. The default II=1 adapter may replace its slot on the response-consumption
edge: it completes the old response before allocating the new accepted request.
An unconsumed response is held and there is still exactly one live owner per port.
The selectable frozen adapter does not reuse its slot on that edge.

The memory performs each array operation once when its service latency expires.
A successful store response means the selected bytes have already been written.
A failed store changes no bytes. Read results contain only the requested byte
lanes; all other lanes are zero. Response data, ID and error remain stable while
`resp_valid && !resp_ready`. Simultaneous I-read/D-write service to the same word
returns the old word on the I port; this is an explicit behavioral-model policy,
not a claim about every FPGA block RAM or SRAM macro.

Memory metrics report request acceptance, response completion/errors, successful
array writes, request wait, response wait and response backpressure separately.
The terminal cycle is included in all counters. A speculative I request can still
be live when an application terminates, so I acceptance and completion totals
need not match at that endpoint. D operations have completed before their stores
retire. Cold reset clears in-flight protocol state and counters but does not undo
array writes or reload the image.

The completion variable's low-word store is recorded on **request acceptance**
(`req_valid && req_ready`) and acted on only **after that store retires**, matched
by the request-owner PC. A held valid request is never counted repeatedly. A high-word store does not terminate.
Low-word value 1 means PASS; any other odd value means failure. Values with bit 0
clear do not terminate. Partial stores are rejected. The application runtime saves
the full `main` return value in the signature; the host process returns 0 for PASS,
1 for a failure, and 2 for timeout.

An out-of-range memory transaction returns a real error response. The CPU then
reports an access-fault trap associated with the original instruction. An
unexpected trap writes a failure summary and signature. The TB does not bypass
the memory response path to stop immediately on an invalid address. Internal
assertion failures remain simulator errors. This is not a
full exception/IRQ validation harness: initial labs intentionally run ordinary
RV32IM applications without interrupt stimulus.

ROI markers are full-word stores of **1**. Zero writes during BSS initialization
are ignored. The count runs from begin-store retirement (excluded) to end-store
retirement (included). It includes call/return and end-marker setup overhead if
markers use function wrappers. `roi_cycles` and `roi_retired` describe the last
completed region, not wall-clock time. Check `roi_complete` before using them.
For the supported one-pair-per-execution contract, `roi_start_cycle` and
`roi_end_cycle` are the absolute retirement cycle numbers of those marker stores,
and `roi_cycles = roi_end_cycle - roi_start_cycle`. An incomplete region has no
valid end measurement. Trace capture can start later or stop earlier without
changing these endpoints.
A timer peripheral or CSR is therefore unnecessary for these simulation counts.
They support short CoreMark correctness/performance experiments, not an official
benchmark score on their own.

Each JSONL record is sampled just before the rising-edge register updates. Cycle
numbers are absolute, starting at 1 after reset, even when capture starts later.
`fetch.accepted` is frontend-to-execution admission, excluding a word discarded
by redirect. It is different from an instruction-memory request handshake.
`memory.response_valid` identifies a pending returned response; writeback marks
an actual RF write.
A store and a branch can retire with writeback inactive. The integer booleans are
0/1. The viewer should use validity/activity flags before displaying stale values.
**Reaching `trace_limit` only stops capture; simulation continues to completion.**

JSONL schema 2 preserves the original `fetch`, `execute`, `memory`, `commit`,
`stages`, `units`, `regs`, `redirect`, and `trap` fields. It adds:

- `ports.instruction` and `ports.data`: request/response valid, ready, accepted,
  ID, complete request payload, response data/error, and accepted-owner PC/address.
  Owner metadata describes the outstanding response, not an unaccepted request.
- `drain.requested` and `drain.done`: public quiescence control.
- `trap.value`: original faulting address or illegal instruction value.

The protocol regression also uses optional TB controls:
`+expected_trap_cause=N`, `+expected_trap_pc=hex`, `+expected_trap_value=hex`
require the specified exception; reaching successful `tohost` instead fails.
`+drain_at=N`, `+drain_when_i_stalled=1`, or `+drain_when_d_stalled=1` initiate
one quiescence request. `+drain_hold=N` retains the request for N acknowledged
cycles before resuming (default 3). These are verification controls, not software
MMIO devices. An already offered request continues through drain.

Run focused protocol tests with:

```sh
python3 tests/memory_protocol.py --output build/memory_protocol.json
```

The standalone driver supplies response backpressure that the blocking CPU does
not generate itself. CPU tests use only public memory/trace/drain ports and
support `--rtl-dir /absolute/path/to/alternative/rtl`. Their scope is the blocking
profile: multiple outstanding IDs, IRQ entry, caches and external buses are
separate future tests.

Manual lint, from the `rtl` directory:

```sh
verilator --lint-only --assert --top-module tb_cpu_lab \
  -f filelist.f ../tb/teaching_sram.sv ../tb/tb_cpu_lab.sv
```

For a manual executable build, add `--cc --exe --build --trace-fst`, choose an
absolute `--Mdir`, and pass the absolute path to `tb/sim_main.cpp`. The normal
course runner handles this and keeps generated files outside the source tree.
