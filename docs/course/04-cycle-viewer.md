# Lab 04 — Register and inspect your application

**Goal:** Add your own application to the gallery and follow real RTL activity.
**Prerequisite:** The restored `student/main.c` from Lab 02 passes comparison.
**Keep:** A registered example and three annotated instruction observations.

## 1. Register your program

```sh
cd ~/rv-lab
export LAB_BUILD_DIR="$PWD/build/course"
python3 lab.py register --source student/main.c --name my-sum --title "My sum" --opt O2
```

The registration command builds your application, compares the same ELF on
Spike and RTL, records the actual RTL cycle trace and full retirement log, and
adds the successful result to **My applications**. It prints the output paths.
The equivalent Make command is:

```sh
make register SOURCE=student/main.c NAME=my-sum TITLE="My sum" OPT=O2
```

Open [the gallery](http://127.0.0.1:8771/). Choose **My applications**, then
**My sum**, and open it. Registration belongs to the selected build directory;
it does not upload the source or make a permanent copy of your source project.
Keep the original source and the run evidence.

The [registration reference](../register-application.md) covers name reuse,
refresh behavior, and the checks that keep a gallery entry tied to its run.

## 2. Follow a load through the CPU

Use **Jump to main**, then **Next** to advance one recorded cycle at a time.
Find the call to `sum_values` in the disassembly, and inspect a load from the
input array. Use **Find next** with its hexadecimal PC to locate later loop
iterations. Record these events:

1. The load becomes the executing instruction and its address is formed.
2. The data-memory request is offered, then accepted when valid and ready agree.
3. The corresponding response returns and the destination register is written.

The selected-cycle panel provides operands and the instruction identity. The
diagram highlights logical use of ALU, branch, multiply/divide, and memory units
from the recorded RTL signals. The highlights are not measurements of electrical
switching, power, or physical delay.

## 3. Separate execution, retirement, and register writes

Use **Next retirement** to skip waiting cycles. Find a branch and a store, for
example one of the ROI marker stores. Record a retirement that does not enable a
register-file write. Why would counting only register writes undercount executed
instructions?

Each sample describes signals immediately before a rising edge. An accepted
memory transfer or enabled register write takes effect at that edge; resulting
state appears in the next sample. The current CPU overlaps fetch with one
serialized execution slot. The functional diagram does not imply five
independently occupied pipeline stages.

The timeline's **A** is admission to the execution slot, not retirement. **F**
means a delivered instruction word is available but not admitted. A word fetched
on a path later discarded by a branch can appear in the trace without retiring.
See the [viewer guide](../../viewer/README.md) for all timeline symbols.

## 4. Focus the capture and update the example

For a shorter trace beginning at the sum function, run:

```sh
python3 lab.py register --source student/main.c --name my-sum --title "My sum" --opt O2 --trace-symbol sum_values --trace-limit 2000
```

Rerun registration after editing your code, then refresh the browser. A failed
new comparison must be fixed before the new run can be registered as successful.
The capture limit bounds the detailed viewer window; it does not stop execution
or shorten the ROI measurement. The retirement log covers the complete run
independently of that limit. Use the result page for full-run and ROI totals.

For a program split across files, repeat `--source`:

```sh
python3 lab.py register --source student/main.c --source student/helpers.c --name my-project --title "My project"
```

This last command is a pattern for a project that actually contains both files;
do not add a nonexistent helper file to the sum example.

## Checkpoint

Submit the command and output directory, plus observations for one load, one
branch, and one store. Identify the PC, relevant cycles, active units, and whether
the instruction writes a register. State whether your trace was truncated and
explain why its sample count need not equal the full execution cycle count.

Next: [Lab 05 — Measure an improvement](05-performance.md).
