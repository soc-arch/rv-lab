# Register your program in the cycle viewer

Run these commands from the lab directory. You need the tools listed by
`make doctor` and an application with `main()`. Start with
[Lab 02](course/02-first-main.md) or [the application quick reference](student-workflow.md).

## Register a successful execution

```sh
make register SOURCE=my_main.c NAME=my-sum TITLE="My sum"
make serve
```

Open `http://127.0.0.1:8770/`, select **My applications**, and open **My sum**.
The console prints the actual generated folder and HTML paths. If you set
`LAB_BUILD_DIR`, use that same setting for both commands. Refresh an already-open
browser tab after a run; the viewer is a saved report, not a live simulator.

The register command performs these steps:

1. Build one ELF using the supplied C/assembly files and the lab runtime.
2. Execute that ELF on Spike and RTL, require successful checks and matching
   complete functional signatures.
3. Save a real RTL cycle trace and full retirement log, with source/disassembly.
4. Write output, performance, and cycle reports, then add a receipt-bound entry
   to the gallery. A failed comparison is never registered.

`--backend` does not reduce registration to one backend: registration always
performs both executions. Use ordinary `run` commands for isolated debugging.

## Follow the computation

Use Next/Previous to move one captured cycle, or Next retirement to move to a
completed instruction. The CPU diagram highlights the recorded functional-unit
activity, register reads/writeback, memory requests/responses, and execution
state. A highlighted region is activity in this CPU model, not a power estimate.
The baseline has an overlapping fetch frontend and one serialized execution
slot; the diagram does not imply five independently occupied pipeline stages.

The source/disassembly view is compiled with debug information. Optimized C can
map several source lines to one instruction or remove work entirely. Use `OPT=O0`
for an initial walkthrough, then inspect the optimized machine instructions too.
Use the gallery's **Program output & performance results** link for the console,
ROI cycles, retired instructions, CPI, and the complete retirement CSV.

## Control the capture and compare variants

```sh
make register SOURCE=my_main.c NAME=my-sum TITLE="My sum" OPT=O0
make register SOURCE=my_main.c NAME=my-sum TITLE="My sum" OPT=O2
make register SOURCE=my_main.c NAME=my-sum TITLE="My sum" MEMORY=stress
python3 lab.py register --source my_main.c --source helpers.c \
  --name my-filter --title "My filter" --description "A checked integer filter" \
  --trace-symbol filter_kernel --trace-limit 5000
```

By default capture starts at `main` and stops after 20,000 cycles. Execution,
comparison, full retirement logging, and ROI timing continue after this limit.
Choose a reached, non-inlined symbol with `--trace-symbol`, or pass
`--trace-startup` to capture startup. Zero captured cycles cannot be registered.
`__attribute__((noinline))` can preserve a C function for this purpose.
`TRACE_SYMBOL` and `TRACE_LIMIT` are the corresponding Make variables.

Optional software counters use `CSR=1` and `lab_perf.h`; `CLOCK_MHZ=100` supplies
an assumed clock for estimated execution time. See
[performance monitoring](performance-monitoring.md). Keep deterministic program
output separate from backend-dependent counter data.

## Understand names, revisions, and evidence

A name starts with a lowercase letter and contains at most 48 lowercase letters,
digits, underscores or hyphens. `TITLE` is the human-readable label; it need not
be a filename. A name identifies one ordered list of source paths within a build
root. Using the same name for other sources is rejected; choose another name.
Optimization and memory variants are separate entries. Re-registering the same
source paths and variant replaces that run and its displayed title.

The receipt is `<printed-output-folder>/registration.json`. It stores the source
paths, options, ELF identity, and hashes of the build/verification/performance
records, ELF, disassembly, retirement logs, raw cycle trace, and the viewer's embedded recorded data. The
gallery checks this evidence on refresh; template/navigation updates preserve
the recorded-data identity.
The source files stay where you wrote them. Registration does not copy a new
application into the built-in examples and does not modify any CPU RTL or TB.

Any ordinary rebuild/rerun of the same source-path/optimization/memory variant
invalidates its registration first, including a hardware-only run, compilation
failure, or missing source. Re-register after fixing the problem. Other variants
remain explicitly recorded historical runs; editing a source file does not
reexecute them. There is no file watcher and no background execution.

To preserve a baseline before editing, use another output root:

```sh
LAB_BUILD_DIR="$PWD/build/baseline" make register SOURCE=my_main.c NAME=my-sum
# Edit the program, then:
LAB_BUILD_DIR="$PWD/build/experiment" make register SOURCE=my_main.c NAME=my-sum
```

Deleting a generated build root also removes its registrations. Keep sources
and the register command in your project notes; repeat the command to recreate
the gallery. The receipt records the actual options for review, but is not an
automatic cross-machine replay mechanism.

## Share a report

```sh
make export-views
```

Extract the printed `cpu_lab_examples.zip` and open `index.html` in a browser.
The complete course manual, grouped gallery, available output/performance pages,
registered traces, disassembly, logs, and evidence travel together. Navigation
uses relative paths and works without a server or internet connection. Keep the
directory layout intact. Paths inside run metadata describe the original host;
viewing a report does not require those paths. Submit your source files separately
when others need to rebuild the application, including any local headers.
