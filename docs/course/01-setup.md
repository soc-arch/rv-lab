# Lab 01 — Setup and baseline

**Goal:** Establish a working baseline before writing your own application.
**Prerequisite:** The tools in the [setup guide](../setup.md) are installed or
provided by staff, and this repository is cloned into your workspace.
**Keep:** Tool versions, the three commands below, and their outcomes.


**Reference:** [Expected result and real screenshots](../expected-results.md#lab-01). Run the exercise yourself and record your own results.

## 1. Select your workspace

Open a terminal and run:

```sh
cd ~/rv-lab
mkdir -p student
export LAB_BUILD_DIR="$PWD/build/course"
```

`student/` holds your editable application files. `LAB_BUILD_DIR` selects all
generated output, including simulator builds, result pages, and the gallery.
Use this same selection in every terminal for the course. Leave `rtl/` unchanged.

## 2. Check the tools

```sh
make doctor
```

Read the paths and versions for the RISC-V compiler, Spike, Verilator, Python,
Make, and the host C++ compiler. The doctor checks availability; it does not
install anything. Resolve missing tools using the environment settings in the
[setup guide](../setup.md#3-check-prerequisites-and-versions) or ask your instructor
for the installed paths.

## 3. Compare one known program

```sh
make compare APP=01_arithmetic
```

The runner compiles one ELF and executes that same file on Spike and the RTL
simulator. Expect successful checks and a matching complete functional
signature. The first RTL run may spend time building the simulator. Later runs
reuse the compatible simulator build.

The functional signature includes checks, result slots, completion status, and
buffered console output. Matching signatures are useful evidence for this test;
they are not proof of every RISC-V instruction or every possible program.

## 4. Run the compact regression

```sh
make test-smoke
```

Expect all 17 cases to meet their expected outcomes. Three cases deliberately
exercise failures; the suite passes when those failures are detected correctly.
Read the suite summary rather than interpreting every printed failure as a
broken installation. If compare or smoke fails unexpectedly, keep the output
directory and logs before making changes.

## 5. Open the manual and result page

Generate the browser edition of these lessons:

```sh
make course
```

In a second terminal:

```sh
cd ~/rv-lab
LAB_BUILD_DIR="$PWD/build/course" make serve PORT=8771
```

Leave it running, then open
[the course manual](http://127.0.0.1:8771/course/index.html) and
[program results](http://127.0.0.1:8771/results.html) in a browser. Select the
arithmetic application and locate its checks and console output. A code editor
can display HTML as source; use a browser to render it.

On a remote machine, forward port 8771 from your laptop using the
[SSH setup steps](../setup.md#6-open-remote-results-through-ssh). A successfully
connected `ssh -N` stays quiet without a shell prompt. Keep the tunnel and result
server running while using the browser. The server serves generated files only;
it does not execute new simulations from the browser. Stop it with Ctrl-C when
finished.

## Checkpoint

Record the selected output directory, tool versions, comparison result, and
smoke summary. Explain in one sentence why running both backends from one ELF is
preferable to compiling them separately. Continue only after the baseline passes.

Next: [Lab 02 — Your first main](02-first-main.md).
