# Performance monitoring contract

The lab provides two measurement paths: testbench observation of the RTL and
optional software reads of the core's existing performance CSRs. Correctness,
performance counters, and detailed traces are separate outputs. This allows the
same application to run on Spike and RTL while their timing differs.

## Measurements available now

| Measurement | Source and boundary | Appropriate use |
|---|---|---|
| Full-run cycles/retirements | RTL testbench, first active cycle after reset through the retiring completion store | Total application and runtime cost |
| ROI cycles/retirements | Retired begin-marker store excluded; retired end-marker store included | Repeatable workload comparisons with the same marker placement |
| CSR cycle/instret deltas | Software counter reads at `lab_perf_begin()` and `lab_perf_end()` | Target-side instrumentation, reusable when a compatible core replaces this one |
| Retirement log | Public RTL commit observation, throughout execution when `COMMITS=1` | Executed instruction order and decoded instruction analysis |
| Detailed cycle trace | Selected RTL capture window when `TRACE=1` | Per-cycle explanation of execution, stalls, memory, and frontend activity |
| Execution-time estimate | Measured RTL cycles divided by a supplied clock frequency | What-if comparison at an explicitly assumed frequency |

`report.html` displays application output/checks and measurements;
`performance.json` is the machine-readable performance result. `CLOCK_MHZ` is
optional. Without a supplied frequency, report cycles and CPI without inventing
seconds. Timing from Spike and elapsed host simulation time are not predictions
of this CPU's RTL execution time.

## CSR runtime

Enable the optional runtime with `CSR=1` and include
[`lab_perf.h`](../runtime/lab_perf.h). Its public API is:

```c
uint64_t lab_perf_read_cycle(void);
uint64_t lab_perf_read_instret(void);
void lab_perf_begin(void);
void lab_perf_end(void);
```

The read helpers use machine-mode `mcycle`/`mcycleh` and
`minstret`/`minstreth`. The begin/end helpers record a single interval in
`lab_perf_record`, outside the functional result signature. Host reports print
these values without requiring 64-bit target `printf` support. Use one pair per
execution; nested or named multi-region profiling is a future extension.

Each 64-bit RV32 counter read uses **high, low, high**, retrying when the high
halves differ. This prevents a low-half rollover from producing a torn value.
The instruction pattern follows the [RISC-V counter specification](https://docs.riscv.org/reference/isa/v20260120/unpriv/counters.html).
Counter-enabled builds explicitly declare `rv32im_zicsr_zicntr` and ILP32; ordinary
builds keep the RV32IM/ILP32 profile. The helper also uses a local assembler option
for Zicsr. This enables the optional counter exercise without claiming that all
timer, privilege, or counter behavior has passed an ISA-compliance suite.

Reading the two counters sequentially does not create an atomic two-counter
snapshot. Begin/end calls, the counter reads, their control flow, and intervening
record stores add measurement overhead. The cycle and instruction sample windows
also have a small skew. Treat CSR CPI as an instrumented estimate; use the
testbench ROI for cycles and retirements from exactly the same marker interval.
For short kernels, repeat the work, measure an empty interval separately, and
report both raw cost and any stated adjustment. Do not silently subtract a
constant across different cores, compilers, or memory configurations.

Compiler memory barriers help preserve memory operations at the measurement
boundary; they do not make arbitrary pure register computations observable or
create a universal hardware serialization contract. Keep the calculation's
result observable and inspect disassembly. The current core has a serialized
backend and blocking memory operations. A future core must explicitly validate
the ordering required by these helpers. Standard CSR/memory ordering is described
in [Zicsr](https://docs.riscv.org/reference/isa/v20260120/unpriv/zicsr.html).

Do not put counter-dependent values into `lab_check`, `lab_result`, or the
functional `printf` buffer and expect Spike/RTL equality. Use them in the separate
performance record. Functional outputs remain fully compared; timing differences
are not hidden by weakening that comparison.

## Existing core capabilities and limits

This table describes the current P1 static [`rtl/`](../rtl/README.md) snapshot, not every
future HY-RV CPU. The sources are
[`rv32_csr.sv`](../rtl/common/rv32_csr.sv),
[`rv32_pmu.sv`](../rtl/common/rv32_pmu.sv), and
[`rv_backend.sv`](../rtl/simple/rv_backend.sv).

| Facility | Current implementation |
|---|---|
| `mcycle` / `mcycleh` | 64-bit storage, addresses `0xB00` / `0xB80`; increments on every active core clock |
| `minstret` / `minstreth` | 64-bit storage, `0xB02` / `0xB82`; counts the existing normal-retirement event |
| Read-only `cycle` / `cycleh` | `0xC00` / `0xC80`, aliases of the cycle storage |
| Read-only `instret` / `instreth` | `0xC02` / `0xC82`, aliases of the instruction storage |
| `time` / `timeh` | `0xC01` / `0xC81`, aliases of cycle storage; no independent timer in this lab |
| HPM counters | Four 64-bit machine counters, `mhpmcounter3` through `6`; 4-bit selectors; selection zero disables counting |
| `mcountinhibit` | Not implemented; software uses counter differences instead of freeze/start |
| User-mode counter access | Not a validated platform feature; this lab runs in machine mode |

The backend omits successful `MRET` from its current retirement event. Ordinary
trap-free applications are the intended measurement profile. Do not extend these
instruction counts to trap/interrupt handlers or advertise full architectural
retirement compliance without fixing and testing that boundary in the CPU
session. Faulting instructions do not retire; register writeback is not a valid
substitute for retirement because stores and branches may write no register.

The lab CSR write path blocks writes on trap/mret, and its CSR events exclude
illegal or trapped accesses. Recheck these behaviors in the selected source
snapshot before describing the capabilities of a replacement CPU.

Legacy HPM events are not yet a stable cross-core performance ABI. Some count
overlapping busy cycles; others count retired instructions or trap events.
Event meanings also differ across older P0/P1/P2 implementations. Do not sum
these events into a CPI stack or equate memory requests with cache misses.
Unsupported cache or branch-predictor measurements should be N/A, not a measured
zero. The optional student API currently exposes only cycle and instruction
counters.

## CPI and execution time

For the same measurement interval:

```text
CPI                     = cycles / retired_instructions
estimated_seconds       = cycles / assumed_clock_hz
estimated_microseconds  = cycles / assumed_clock_mhz
cycle_speedup           = baseline_cycles / candidate_cycles
```

CPI is undefined when the interval retires no instructions. Lower cycle count is
the direct improvement metric at equal frequency; lower CPI may be accompanied
by more instructions. Compare identical useful work, inputs, memory timing, and
measurement boundaries. Save ELF/source identity, optimization options, core
identity, and memory configuration with the result.

`CLOCK_MHZ=100` means an assumed 100 MHz, so 10,000 measured cycles correspond to
an estimated 100 microseconds. The argument neither changes the cycle model nor
proves that a synthesized CPU meets that frequency. Physical clock claims require
separate implementation/timing evidence. If two implementations use different
validated frequencies, compare `cycles / frequency` for each.

The current `time` alias should not be used as an independent timestamp service.
The ISA permits cycle and time to coincide on some simple platforms, but a real
timebase still needs a defined stable tick period. This lab has no such timer
contract, and writes to its cycle counter affect the alias. A future platform
should define `mtime`/`time`, tick frequency, and behavior during reset, clock
changes, and halt. Standard platform timer and counter-control semantics are in
the [machine-level ISA](https://docs.riscv.org/reference/isa/v20260120/priv/machine.html#_hardware_performance_monitor).

## Instruction records and reproducibility

`COMMITS=1` exports every observed RTL retirement to `commits.jsonl` and decoded
`commits.csv`.
It is independent of `TRACE_LIMIT`, which caps only the detailed cycle capture.
These are dynamic instruction records; `program.dis` is the static ELF
disassembly. A wrong-path fetch can appear in the cycle viewer without appearing
in the retirement stream. A retirement log also does not by itself prove
per-instruction differential equality with Spike: the current application
comparison checks end-of-run functional results.

Keep complete logs for short experiments. For larger workloads, retain full
counter totals and a deliberate detailed trace window, and record any capture
limits. See [reproducibility](reproducibility.md) for source receipts and the
[student workflow](student-workflow.md) for baseline/candidate commands.

## Possible extensions

This software API and report can be a starting point for a common monitoring
layer. The ideas below are possible extensions, not implemented capabilities of
this lab.

The next useful steps are:

1. Define capability/version metadata shared by software, RTL observation, and
   reports: counter width, event meaning/unit, supported events, boundaries,
   clock source, and whether a value is measured or modeled.
2. Validate precise retirement, counter-write ordering, rollover, and optional
   `mcountinhibit` in the CPU session. Freeze/snapshot support can reduce
   multi-counter sampling skew; it is not implemented by this runtime.
3. Add named regions and iteration counts, then event profiles for loads/stores,
   multiply/divide activity, and memory waits with explicit overlap rules.
4. Keep transport separate from measurement. Buffered simulation output works
   now; UART, FPGA collection, or a host snapshot interface can later export the
   same versioned records.

No CPU RTL or public memory/trace interface change is required for the initial
read-only counter helpers. Future CSR, retirement, timer, or event-contract
changes belong to the CPU integration work and require a documented contract
update plus counter-specific tests before the lab advertises the new capability.
