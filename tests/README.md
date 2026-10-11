# Regression after a CPU or memory edit

Run these commands from the CPU laboratory directory. The runner builds the
software and Verilator model automatically. A nonzero process exit means the gate
failed; do not use a previously generated HTML page as evidence for the new RTL.

```sh
make test-smoke       # Fast development loop: 17 existing application scenarios
make test            # Release gate: 47 scenarios plus focused memory tests
make perf-test       # Student main/CSR counters, complete instruction logs, result pages
make camera-test     # Independent image arithmetic, real firmware, stale outputs
make gallery         # Five introductory explorers + delayed-memory example
make camera WIDTH=7 HEIGHT=5  # Four compact image-kernel cycle explorers
```

The first build takes longer. Simulator binaries are cached by source hashes,
compiler identity and simulator flags. Changing RTL, the memory model or the
application testbench selects a new build automatically.

## Application matrix

Every positive scenario executes the **same ELF** on Spike and RTL, checks all
known answers, and compares the complete runtime signature. CoreMark validates
the original workload's CRCs. Camera cases compare every output byte against both
Spike and an independent host implementation.

| Group | Scenarios | Purpose |
|---|---:|---|
| Five examples + assembly ISA contract at O0/O2 | 12 | ALU, all M operations, branches/calls, stack and narrow memory accesses |
| CoreMark performance/validation seed sets | 2 | Longer compiler-generated integer workloads |
| Nonzero return, incorrect answer, infinite loop | 3 | Both simulators must fail for the expected reason |
| Six positive applications at latency2, latency3, stress | 18 | Both I/D ports wait; request stalls and differing issue spacing |
| Memory/control at I=1,D=5 and I=5,D=1 | 4 | Instruction and data delays vary independently |
| Both CoreMark seed sets under stress | 2 | Long wait-enabled workload, same CRCs |
| Copy/grayscale/Sobel/pipeline, 7x5 image under stress | 4 | Measured image regions with independently verified pixels |
| ISA/control under a second stall seed | 2 | A second reproducible ordering of request stalls |
| **Total** | **47** | First 17 form `test-smoke`; all 47 form the application part of `test` |

The full matrix fixes its own memory configurations so a command-line preference
cannot accidentally disable the stress gate. For an individual experiment use:

```sh
make compare APP=isa_contract MEMORY=stress
make view APP=02_memory I_LATENCY=5 D_LATENCY=2 STALL_MAX=4 STALL_SEED=2026
```

`fast`: latency 1, spacing 1, no injected stalls. `latency2`: latency 2,
spacing 1. `latency3`: latency 3, spacing 3. `stress`: latency 5, I/D spacing
2/3, bounded request stalls of up to 4 cycles, seed 17. The alternate seed is
2026. These profiles define behavioral service timing, not silicon timing closure.
The blocking CPU does not claim one new request every cycle; the separate
protocol harness checks channel behavior directly.

## Protocol and failure gate

```sh
make memory-test
```

This gate drives the public memory boundary and the real CPU. It checks offered
versus accepted requests, response holding under backpressure, correct byte lanes,
exactly-once writes, faults, redirect recovery and drain. Instruction errors on a
discarded path must not become architectural traps; live errors must not retire
normally. Unsupported misaligned accesses must fault before a memory side effect.
The emitted `build/memory_protocol.json` lists the actual directed cases and
their results. It is embedded in `build/regression.json` by the full gate.

Application negative tests and protocol fault tests serve different purposes:
the former check the host's pass/fail policy; the latter deliberately inject
hardware faults and check their architectural/protocol consequences.

## Read the evidence

- `build/regression.json`: exact RTL build, timing profiles, ELF hashes and
  complete per-case SW/HW evidence. Previous receipts go to
  `build/regression-history/` before a new run.
- Each application directory: `program.dis`, `build.json`, `sw.json`, `hw.json`,
  signatures and logs. Non-default timing uses a distinct `-mem-...` directory.
- `build/memory_protocol.json` and `.log`: focused channel/fault evidence.
- `build/validation/<run>/receipt.json`: commands, tool identity and gate results
  from `make validate`; `source-before.json` and `source-after.json` record
  source identity and detect drift. Per-gate copies preserve smoke/full evidence
  even when later experiments replace the current application results.

Record status as **running** or **fail** until every required case completes.
Cycle counts may change after a microarchitecture or memory edit. Results and
retirement correctness must not. Spike's wall time or cycle CSR is not an RTL
performance oracle. ROI counters retain their retired-marker-store boundary.

`make validate` also runs the student performance gate and generates O0/O2
`10_performance` reports. The gate checks the same ELF on Spike/RTL, every
instrumentation CSR read against public cycle/retirement observations, marker ROI
counts against the complete retirement log, a user-written `main` without CSRs,
and failure reports. `CPU_LAB_PERF_TEST_REPORT` retains its per-run evidence.
The optional CSR profile requires the machine cycle/instret counters and Zicsr;
a replacement providing only the base application profile cannot claim this
additional capability without running the performance gate.

## Replacement cores and limits

```sh
LAB_BUILD_DIR="$PWD/build/candidate-v1" make validate RTL_DIR=/absolute/path/to/replacement/rtl
```

The replacement supplies the same `teaching_cpu`, memory interface, drain and
observation ports, with its own `filelist.f`. Neither application nor protocol
tests should access CPU implementation hierarchy. A richer CPU can add tests,
but should retain the baseline application and failure gates.

This set is directed verification, not formal proof or complete ISA/privileged
compliance. It does not cover cache coherence, multiple outstanding transactions,
atomics, a full interrupt controller or asynchronous physical SRAM clocking.
Those require additional configurations and tests when implemented.
