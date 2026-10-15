# Lab 02 — Your first main

**Goal:** Run your own C application and inspect its output on screen.
**Prerequisite:** Lab 01 passes.
**Keep:** Your C source, output directory, and a passing result report.


**Reference:** [Expected result and real screenshots](../expected-results.md#lab-02). Run the exercise yourself and record your own results.

## 1. Copy the starter

```sh
cd ~/rv-lab
export LAB_BUILD_DIR="$PWD/build/course"
mkdir -p student
cp docs/course/starter/sum.c student/main.c
```

Open `student/main.c`. Its `main()` adds the eight input values, checks the
known answer, saves a result slot, and prints `sum=36`. The lab's startup calls
`main()` and turns its return value into program completion.

The important runtime calls are:

| Call | Purpose |
|---|---|
| `lab_check(id, actual, expected)` | Record a known-answer check; a mismatch fails the run |
| `lab_result(slot, value)` | Save a 32-bit result in slot 0 through 15 |
| `printf`, `puts`, `putchar` | Append deterministic text to the console buffer |
| `lab_roi_begin()`, `lab_roi_end()` | Mark one region of interest for RTL measurement |
| `return 0` from `main()` | Complete successfully if the checks also pass |

## 2. Run each backend, then compare

```sh
make sw-sim SOURCE=student/main.c
make hw-sim SOURCE=student/main.c
make compare SOURCE=student/main.c
```

The runner prints the generated application directory. Custom-source directory
names include a source-path identifier; do not assume that the directory is
named `main`. Success on each backend separately is useful while debugging;
`compare` additionally checks their complete functional signatures.

Expect the console line `sum=36`, one passing check, and result slot 0 equal to
36. In the browser, refresh
[program results](http://127.0.0.1:8771/results.html) and open the new report.
Locate the ELF/build identity, result status, console, and RTL measurements.

## 3. Make a small change

Change the last input value from 8 to 10. Calculate the new answer on paper,
change the expected answer from 36 to 38, and rerun:

```sh
make compare SOURCE=student/main.c
```

Expect `sum=38` and a passing check. Restore the original input and expectation,
then run compare again so later exercises start with the same eight-value sum.

The input array is `volatile` so the compiler must perform its loads. The result
is checked and printed, so the calculation remains observable. In a real
optimization experiment, inspect generated instructions rather than assuming
that source lines translate into particular hardware operations.

## 4. Understand the output limits

The console is a 1024-byte SRAM buffer displayed after execution. It is not a
live terminal or UART. Keep text short. The supported formats include `%d`,
`%u`, `%x`, `%c`, `%s`, and `%%`; floating-point and `%llu` output are not
provided. This freestanding environment does not provide a full operating
system or C library.

Keep output deterministic. Do not print a cycle counter into the functional
console: Spike and RTL have different timing, so their signatures would differ.
Lab 05 provides a separate performance record for those values.

## Checkpoint

Submit the restored passing source and report. State the observed answer before
and after your input change. Explain why an application that prints a plausible
number but has no known-answer check gives weaker correctness evidence.

Next: [Lab 03 — Find a wrong result](03-debugging.md).
