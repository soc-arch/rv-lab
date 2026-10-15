# Lab 05 — Measure an improvement

**Goal:** Compare correct programs using cycles, retired instructions, and CPI.
**Prerequisite:** Labs 02 and 04.
**Keep:** An O0/O2 measurement table and an explanation based on instructions.


**Reference:** [Expected result and real screenshots](../expected-results.md#lab-05). Run the exercise yourself and record your own results.

## 1. Inspect the two measurement paths

```sh
cd ~/rv-lab
export LAB_BUILD_DIR="$PWD/build/course"
cp docs/course/starter/performance.c student/performance.c
```

Open the file. The sum of 1 through 16 must be 136. Preparation, checks, and
printing sit outside the measurements. The measured section has this structure:

```c
lab_perf_begin();
lab_roi_begin();
uint32_t sum = measured_sum(input, 16);
lab_roi_end();
lab_perf_end();
```

ROI markers let the testbench count cycles and retired instructions between two
retiring stores. `lab_perf_begin/end` read the core's existing machine-mode
`mcycle` and `minstret` CSRs using safe RV32 high/low/high reads. The optional
performance record lives outside the functional signature, so different timing
on Spike and RTL does not weaken the functional comparison.

Use one ROI pair and one CSR pair per execution. The two intervals have different
boundaries and overhead. Their totals should not be expected to match. Neither
path currently creates a named, nested multi-region profile.

## 2. Run both compiler settings

```sh
make compare SOURCE=student/performance.c OPT=O0 CSR=1 COMMITS=1 TRACE=1 CLOCK_MHZ=100
make compare SOURCE=student/performance.c OPT=O2 CSR=1 COMMITS=1 TRACE=1 CLOCK_MHZ=100
```

`CSR=1` links the optional counter runtime and declares the counter-enabled ISA
profile. `COMMITS=1` records every observed RTL retirement in JSONL and decoded
CSV. Open both reports from
[program results](http://127.0.0.1:8771/results.html), and require both comparisons
and the expected-value checks to pass.

Read each report's **ROI** row and fill this table with your measurements:

| Variant | Correct result | ROI cycles | ROI retired instructions | ROI CPI | Estimated time at assumed 100 MHz |
|---|---|---|---|---|---|
| O0 | | | | | |
| O2 | | | | | |

Also record the CSR cycle and instruction deltas in a separate table. Do not mix
a CSR cycle delta with the testbench's ROI retirement count.

## 3. Calculate and explain

Use these formulas for the same interval:

```text
CPI = cycles / retired_instructions
estimated_microseconds = cycles / assumed_clock_mhz
cycle_speedup = baseline_cycles / candidate_cycles
```

`CLOCK_MHZ=100` is an assumed frequency for this calculation. It does not set a
hardware clock or prove that a synthesized design meets 100 MHz. Without a
frequency, report cycles and CPI without inventing elapsed seconds. Spike's
functional counters and the host simulator's elapsed time do not predict this
RTL CPU's execution time.

Open `program.dis` and `commits.csv` from each report directory. The former is a
static instruction listing; the latter records dynamic retirements, including
repeated loop iterations, branches, and stores. Compare the loop's instruction
sequence and explain the change in cycles using your evidence. A smaller CPI
alone does not establish a faster application if it executes more instructions.

## 4. Add the measured program to the gallery

```sh
make register SOURCE=student/performance.c NAME=sum-counters TITLE="Sum with counters" OPT=O2 CSR=1 CLOCK_MHZ=100
```

Use the cycle viewer to connect the loop's loads, additions, and branch with the
retirement log. Printing CSR values with target `printf` would make functional
output differ across backends; read them from the separate performance report.

For an optional exercise, measure an empty interval separately and discuss
instrumentation overhead. Report the raw measurements as well as any proposed
adjustment. Counter reads are sequential, not an atomic two-counter snapshot.
The current `time` CSR aliases cycles; this platform does not provide an
independent timestamp/timebase contract. Use the
[performance contract](../performance-monitoring.md) for the precise limitations.

## Checkpoint

Submit both tables, the cycle-speedup calculation, and one instruction-level
explanation. Preserve the same input and correctness check. State the selected
core, compiler options, memory profile, ROI boundaries, and assumed frequency.
Do not attribute all differences to the CPU when you changed compiler settings.

Next: [Lab 06 — Change memory timing](06-memory.md).
