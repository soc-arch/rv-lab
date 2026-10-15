# HY-RV P1 static CPU RTL

The default CPU is **HY-RV P1.F0.BP0.LS0.X1**, preset `ant_j0`: RV32IM,
32-bit instructions, one backend execution IR, no frontend response buffer,
and an instruction link with queue depth zero. The 29 compilation-source files
are copied byte for byte from the verified canonical P1 static core. Their
canonical aggregate SHA-256 is
`35558e91c602324ddf5b2ab8de893bc0baead18cc9a82c3c336e16c6b3213dd8`.

See [import provenance](../provenance/p1-static-core.json),
[RTL/gate evidence](../provenance/p1-rtl-gate-equivalence.json), and the
[preserved former teaching CPU](../reference/legacy_teaching_51562ce/rtl/README.md).
The former teaching CPU is a migration reference, not the default implementation.

## Read top down

| File | Responsibility |
|---|---|
| `compat/teaching_cpu.sv` | Stable public CPU wrapper and elaboration parameters |
| `simple/rv_core_simple.sv` | Frontend, instruction link, backend and predictor integration |
| `frontend/rv_frontend.sv` | PC/request control, accepted-fetch tracking, instruction assembly |
| `common/rv_insn_link.sv` | Combinational valid/ready token connection at queue depth zero |
| `simple/rv_backend.sv` | One execution IR, decode/RF, execution, LSU, CSR/traps and retirement |
| `frontend/rv_branch_predictor.sv` | Static ANT/BTFNT selection and optional early JAL prediction |
| `common/mem_if.sv` | Instruction/data request-response transaction channels |
| `common/rv_trace_pkg.sv` | Public observations; compatibility alias in `compat/` |
| `common/fu_*.sv` | ALU, branch, blocking multiply and divide execution units |

Frontend helpers are independent modules. Decode, execute, memory and writeback
are functional responsibilities inside the serialized backend, rather than four
independent pipeline stages. There is only one execution IR.

## Presets and timing

| Preset | Conditional prediction | Early JAL | Model |
|---|---|---:|---|
| `ant_j0` (default) | BP0: always not taken | 0 | P1.F0.BP0.LS0.X1 |
| `btfnt_j0` | BP1: backward taken, forward not taken | 0 | P1.F0.BP1.LS0.X1 |
| `ant_j1` | BP0: always not taken | 1 | P1.F0.BP0.LS0.X1 |
| `btfnt_j1` | BP1: backward taken, forward not taken | 1 | P1.F0.BP1.LS0.X1 |

Select with `make compare PRESET=btfnt_j0` or `LAB_CORE_PRESET=btfnt_j0`.
The runner supplies actual elaboration defines, records effective parameters,
and includes them in the simulator cache key. Early JAL is disabled by default.
JALR remains unpredicted. Positive queue depths and dynamic BP2–BP4 are deferred.

With a ready backend, one-cycle instruction-memory latency, and the default
`ii1` adapter, a rising edge can retire instruction I, admit I+1 into the
execution IR, and accept the I+2 fetch request. This conditional initiation
interval is not a whole-program IPC promise. Fetch depends on token availability
and handshakes rather than directly on a commit pulse. While the backend is
busy, an unconsumed instruction response is held by the memory adapter. The
CPU contains no separate response buffer.

Load/store, multiply and divide retain their multicycle behavior. The backend
checks the actual successor against prediction metadata and redirects on a
mismatch. Redirect/fault handling preserves offered-request stability and drains
obsolete responses without executing them or exposing their fetch faults.

## Public replacement contract

Keep `teaching_cpu`, its I/D `mem_if.master` interfaces, drain/IRQ inputs,
retirement outputs and `teaching_trace_pkg::cpu_trace_t` output when replacing
the implementation. The harness uses no private CPU hierarchy or DPI. The
reset PC is `0x80000000`; SRAM storage belongs to the harness. A parameterless
replacement is identified as an external memory-v1 CPU, without a P1 claim.

Requests and responses transfer only at `valid && ready` rising edges and
remain stable when stalled. Each port has one live transaction using ID 0.
An old response may complete on the same edge as a new request is accepted;
completion precedes replacement ownership allocation. No response is produced
in its own request-acceptance cycle. See the [harness contract](../tb/README.md).

Aligned byte/halfword/word accesses use little-endian byte lanes. Misaligned
halfword/word operations trap before a data request. Loads and stores wait for
their response before normal retirement. Access errors, illegal operations and
misaligned control-flow targets retain precise traps. The runtime, software
signature, Spike comparison, ROI stores and public trace schema remain the same.

`filelist.f` lists paths relative to this directory; preserve its source order.
The runner appends the selected SRAM adapter and testbench. Foundry libraries,
proprietary tool inputs and netlists are not included in this public package.
