# Write an application, check it, and measure it

For a guided sequence with checkpoints, use the [eight practical exercises](course/index.md).
To publish your own measured run in the interactive gallery, see
[register your program](register-application.md).

You write `main()` in C or assembly. The lab supplies startup, a linker script,
SRAM, a small output library, and program completion. `make compare` builds one
ELF, runs that same ELF on Spike and the RTL CPU, and checks their complete
functional result signatures.

Run commands from `~/rv-lab`.

## 1. Write and check `main`

Save this as `my_main.c`:

```c
#include "lab.h"
#include <stdio.h>

static volatile unsigned input[] = {1, 2, 3, 4, 5, 6, 7, 8};

int main(void) {
    unsigned sum = 0;
    lab_roi_begin();
    for (unsigned i = 0; i < 8; ++i) sum += input[i];
    lab_roi_end();

    lab_check(1, sum, 36);       /* check id, actual value, expected value */
    lab_result(0, sum);         /* optional result slot, 0 through 15 */
    printf("sum=%u\n", sum);    /* outside the measured region */
    return 0;
}
```

```sh
make doctor
make compare SOURCE=my_main.c
make compare SOURCE=my_main.c OPT=O0
```

A failed check, nonzero return from `main`, unexpected RTL trap, timeout, or
different functional signatures makes the command fail. A program with no checks
can terminate successfully without proving that its calculation is correct.
Use known answers and exercise edge cases.

For multiple C files:

```sh
python3 lab.py run --backend both --source my_main.c --source helpers.c
```

The application profile is RV32IM/ILP32. The package is freestanding: there is no
OS or full C library. An assembly `main` must preserve callee-saved registers,
keep the stack 16-byte aligned, and return its status in `a0`.

## 2. Read the output on screen

The command prints checks, output, and RTL performance summaries. Each completed
run also writes `report.html` and `performance.json` in its application build
directory; the command reports the actual output path. The HTML report presents
the buffered console, correctness results, and performance measurements.

```sh
make serve
```

Open [the application result list](http://127.0.0.1:8770/results.html) in a browser
and select the generated report. You can also open the generated HTML file directly in a
browser. If the simulator runs on another computer, forward the server port as
described in the [setup guide](setup.md#6-open-remote-results-through-ssh).

`printf`, `puts`, and `putchar` write into a 1024-byte SRAM buffer. The host
displays it after completion. It is buffered simulation output, so a program that
hangs does not provide a live console. Supported `printf` conversions are `%d`,
`%i`, `%u`, `%x`, `%c`, `%s`, and `%%`, with integer width/zero padding and one `l`
modifier for 32-bit ILP32 integers. Floating-point and `%llu` formatting are not
provided. Overflow is reported as truncated output.

Keep functional console output deterministic. Printing backend-dependent cycle
values into this buffer makes the complete Spike/RTL signature comparison fail.
Use the separate performance report for counters.

## 3. Measure a region and inspect its instructions

The example above places one **region of interest (ROI)** around the loop.
`lab_roi_begin()` and `lab_roi_end()` mark the region with SRAM stores. The
testbench measures cycles and retired instructions between those stores. No CSR
or timer is needed for this simulation measurement.

```sh
make compare SOURCE=my_main.c COMMITS=1 TRACE=1 CLOCK_MHZ=100
```

- `COMMITS=1` records the full RTL retirement stream as `commits.jsonl` and
  exports decoded `commits.csv`.
  It includes completed stores and branches even when they write no register.
- `TRACE=1` generates the detailed cycle viewer with source, disassembly,
  registers, memory activity, and functional-unit state.
- `CLOCK_MHZ=100` asks the report to convert cycles into an **estimate at an
  assumed 100 MHz**. It does not set or measure a hardware clock.

Retirement logging covers the run independently of the detailed trace limit.
The default detailed trace begins at `main` and captures up to 20,000 cycles;
`TRACE_LIMIT=50000` raises that capture limit. Simulation and complete result
checking continue after detailed capture stops. A fetched instruction that is
discarded on a redirect is not a retired instruction.

The report distinguishes the full run, the ROI, and the captured viewer window.
The full run includes startup and reporting. The ROI includes marker-wrapper
overhead: its begin-store retirement is excluded and its end-store retirement is
included. Use one begin/end pair per execution.

## 4. Read performance counters from your application

Use the optional CSR example:

```sh
make compare APP=10_performance CSR=1 COMMITS=1 TRACE=1 CLOCK_MHZ=100
```

The [example source](../examples/10_performance.c) uses
[`lab_perf.h`](../runtime/lab_perf.h):

```c
#include "lab_perf.h"

/* Inside main, around an existing workload: */
lab_perf_begin();
lab_roi_begin();
/* measured computation */
lab_roi_end();
lab_perf_end();
```

`CSR=1` enables the optional counter runtime and host collection. Cycle and
instruction measurements are stored outside the functional signature. The RTL
host collects this record and displays it separately from program results.
Spike executes the same instrumented ELF as a functional reference; its counter
record is not collected or treated as CPU performance. Application results must
still match.
The supplied `10_performance` example enables this runtime automatically;
specify `CSR=1` explicitly for your own source using `lab_perf.h`. Counter-enabled
builds declare `rv32im_zicsr_zicntr` while retaining the ILP32 ABI.

The CSR and marker intervals have different boundaries and instrumentation
costs. They are useful complementary measurements, and their totals need not
match. See [performance monitoring](performance-monitoring.md) for the exact
counter contract, CPI, timing estimates, and current core limitations.

## 5. Show that an optimization helped

1. Save a baseline run with correct results, input, compiler options, memory
   profile, and core identity.
2. Run the modified application with the same input and measurement boundaries.
3. Require Spike/RTL comparison and expected-value checks to pass.
4. Compare ROI cycles and retired instructions; inspect disassembly and the
   retirement/cycle reports to explain the change.
5. Report cycle speedup as `baseline_cycles / new_cycles`. A lower CPI alone
   does not prove that the program runs faster if it executes more instructions.

Separate output roots preserve both versions:

```sh
LAB_BUILD_DIR="$PWD/build/baseline" make compare SOURCE=my_main.c COMMITS=1
# Edit your application, then:
LAB_BUILD_DIR="$PWD/build/experiment" make compare SOURCE=my_main.c COMMITS=1
```

Keep printing and correctness checks outside the ROI. Ensure the workload's
result is used, and inspect the disassembly when changing optimization settings;
the compiler can remove a calculation whose result has no observable use.
For memory experiments, use the same `MEMORY` profile and stall seed. After a
core replacement, follow the [replacement procedure](core-replacement.md) before
accepting its measurements.
