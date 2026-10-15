# Lab 03 — Find a wrong result

**Goal:** Use checks and output to diagnose a small, intentional failure.
**Prerequisite:** Lab 02.
**Keep:** The initial failure, your explanation, and a passing corrected run.


**Reference:** [Expected result and real screenshots](../expected-results.md#lab-03). Run the exercise yourself and record your own results.

## 1. Run the debugging starter

```sh
cd ~/rv-lab
export LAB_BUILD_DIR="$PWD/build/course"
export LAB_CORE_PRESET=ant_j0
export LAB_MEMORY_ADAPTER=ii1
cp docs/course/starter/debug.c student/debug.c
make compare SOURCE=student/debug.c
```

This command is expected to fail. The program finds the maximum of
`{7, 2, 19, 4, 24, 3}`, prints `maximum=24`, and checks it against an intentionally
wrong expectation of 99. Open its report from
[program results](http://127.0.0.1:8771/results.html).

Locate check ID 301 and its actual/expected values. Both backends can calculate
the same answer and still fail because the answer does not satisfy the declared
check. A failed check makes the command fail even when `main()` returns zero.

## 2. Form a hypothesis and correct the expectation

Read the six inputs and calculate the maximum independently. Change only the
expected value in check 301 to 24, then rerun:

```sh
make compare SOURCE=student/debug.c
```

Expect a passing comparison and `maximum=24`. Record why this was a faulty
expectation rather than evidence that both simulators were wrong.

## 3. Exercise a real algorithm defect

Change the input to `{7, 2, 19, 4, 24, 30}` and set the expected answer to 30.
Run compare to establish that the valid loop handles a last-element maximum.
Then change the loop condition from `i < count` to `i + 1 < count` and rerun.

The second run should fail with actual 24 and expected 30: the last element is
never inspected. Restore `i < count` and rerun successfully. Your test has now
detected a computation defect, rather than merely checking a printed message.

## 4. Choose useful next checks

For another small test, try an array whose largest value is first, then one with
equal values. Update the expected value before each run. Save the input with the
result so someone else can reproduce the case. The starter's maximum function
requires a nonempty array; do not call it with zero elements without first
defining what that case should mean.

A result page distinguishes failed checks, backend errors, traps, and timeouts.
If a program times out, its buffered output is not a live progress indicator.
Use a smaller input, a bounded loop, and a cycle trace to inspect execution.
Lab 04 introduces that trace. This environment does not currently provide an
interactive source-level breakpoint debugger.

## Checkpoint

Keep one failed and one corrected result in your notebook. List the symptom,
hypothesis, changed line, and confirming check for each defect. Restore a passing
program before moving on; never compare the performance of an incorrect variant
as though it were a valid optimization.

Next: [Lab 04 — Register and inspect your application](04-cycle-viewer.md).
