# Lab 08 — A reproducible project

**Goal:** Make one improvement claim that another student can reproduce.
**Prerequisite:** Labs 01–07.
**Keep:** A small source-and-evidence package with one justified comparison.


**Reference:** [Expected result and real screenshots](../expected-results.md#lab-08). Run the exercise yourself and record your own results.

## 1. Choose a bounded question

Choose one change: compiler optimization, a software loop transformation,
memory timing, or a small image-kernel transformation. Define the useful work,
input, known expected result, and ROI before starting. Keep CPU RTL unchanged
during this software/environment exercise.

Write a hypothesis such as: “Unrolling this fixed-count loop reduces ROI cycles
while preserving all output values.” State which observations would refute it.
Do not replace a correctness test with a performance target.

## 2. Preserve a baseline

Copy your chosen source to `student/project.c`, adapt its checks, and run:

```sh
cd ~/rv-lab
export LAB_CORE_PRESET=ant_j0
export LAB_MEMORY_ADAPTER=ii1
LAB_BUILD_DIR="$PWD/build/project-baseline" make register SOURCE=student/project.c NAME=project TITLE="Project baseline" COMMITS=1
```

Keep the printed output directory. Preserve the baseline source before editing,
for example as `student/project-baseline.c`. Generated build metadata records
source/ELF identity, but does not substitute for retaining the source itself.
If the application uses `lab_perf.h`, include `CSR=1` in both runs.

## 3. Make one change and measure again

Edit `student/project.c`, then run:

```sh
LAB_BUILD_DIR="$PWD/build/project-candidate" make register SOURCE=student/project.c NAME=project TITLE="Project candidate" COMMITS=1
```

Require correct results on both backends. Compare useful work, ROI cycles,
retirements, and CPI. Keep memory settings and inputs identical unless they are
the independent variable. Use disassembly and actual traces to explain the
observed difference. If there is no improvement, a well-supported negative
result is still useful.

To view either isolated output root, use the matching server selection:

```sh
LAB_BUILD_DIR="$PWD/build/project-candidate" make serve PORT=8772
```

Open [the candidate gallery](http://127.0.0.1:8772/). Use another port or stop
that server before serving the baseline at the same address.

## 4. Assemble the evidence

Keep the following for each variant:

- Exact source and input files, command, compiler options, selected core, and memory settings.
- `build.json`, `result.json`, and `performance.json` from the printed run directory.
- `report.html`, `program.dis`, and the required `commits.csv`/`commits.jsonl` evidence.
- `trace.html` with its trace-start setting and capture limit; raw trace when needed for reanalysis.
- A short table of correctness, ROI cycles, retirements, CPI, and any assumed frequency.

Package the candidate's available viewer pages for offline sharing:

```sh
LAB_BUILD_DIR="$PWD/build/project-candidate" make export-views
```

The archive is `build/project-candidate/cpu_lab_examples.zip`. Extract the entire
archive and open `index.html` in a browser; neighboring files are needed for
navigation. This viewer export is not a source-project backup. Distribute your
source, input, commands, and measurements with it using your course's submission
method. Registration and export do not publish anything externally.

## 5. Explain a future CPU replacement

Your application and its expected results can be reused when staff supply a
compatible CPU. That new CPU must pass its own validation; the old core's PASS
does not carry over automatically. The staff procedure is documented in
[core replacement](../core-replacement.md).

For staff or an approved integration exercise, the selection pattern is:

```sh
LAB_BUILD_DIR="$PWD/build/candidate-core" make validate RTL_DIR=/absolute/path/to/frozen/candidate/rtl
```

The path must point to a supplied compatible, frozen RTL tree. This command is
not a claim that such a candidate is present. Validate the public interfaces,
trace meaning, and counter capability contract before interpreting the new
core's viewer or performance totals. Record any required interface/testbench
adaptation explicitly. Internal CPU/front-end design belongs to the separate
CPU development work.

## Final checkpoint

Submit a one-page argument with the question, controlled settings, correctness
evidence, measurement table, and instruction-level explanation. Report cycle
speedup and distinguish measured cycles from estimated physical time. Include
one limitation and the exact commands needed to reproduce your result.

For a future research monitoring layer, useful next capabilities include named
regions, versioned event meanings, and explicit counter/timebase capabilities.
The current course uses one ROI and optional cycle/retirement CSR reads; do not
present proposed monitoring features as implemented measurements.

Return to [the course index](index.md).
