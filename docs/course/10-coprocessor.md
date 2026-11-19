# Lab 10 — Extend the CPU through a coprocessor interface

**Goal:** Move the same dot product out of the pipeline into a coprocessor with private state, connect it through a handshake interface, and measure what the interface costs.
**Prerequisite:** Lab 09.
**Keep:** Your four TODO edits, a passing `make lab10-check`, the comparison table from `make ext-compare`, and your latency analysis.

**Reference:** [Expected result](../expected-results.md#lab-10) · [Extension contract and interface](../../ext/README.md#lab-10-xacc-a-coprocessor-with-private-state). Run the exercise yourself and record your own results.

## 1. Same kernel, different answers

In Lab 09 the dot product was a building block inside EX. Here the work moves
beside the core, and the running sum moves with it:

| Question | Lab 09: XDOT4 | Lab 10: XACC |
|---|---|---|
| Q3 Implementation | Unit in EX, one cycle | Coprocessor beside the core, behind an interface |
| Q4 Operands | 2 reads, 1 write per word | 2 reads per word; the sum stays **inside** the coprocessor (`acc`) |
| New state | none | `acc`: 32 bits, private to the coprocessor |
| Instructions per word | lw, lw, xdot4, **add**, loop | lw, lw, xacc.dot4, loop |

Three custom-1 instructions use it:

```text
xacc.clr              acc = 0                       0x0000002B
xacc.dot4 rs1, rs2    acc = acc + dot4(rs1, rs2)    0000001 rs2 rs1 000 00000 0101011
xacc.rd   rd          rd = acc                      0000010 00000 00000 000 rd 0101011
```

Keeping the sum in the coprocessor is the "keep the value in the unit" option
for a third operand: no third register read and no ADD, but now there is state
that someone must clear, read out, and save on a context switch.

## 2. Read the interface

Open [XIF-lite](../../ext/README.md#xif-lite-the-coprocessor-interface). The core
side is already written in your copy; you will build the coprocessor side. One
instruction flows like this (latency 1):

```text
cycle         n            n+1           n+2
execute     XIF_REQ      XIF_WAIT       next instruction
issue       valid=1 ready=1 accept=1
result                   valid=1 ready=1  -> retire, write rd if result_we
```

- The core reads rs1/rs2 and **offers** the instruction (`XIF_REQ`). It offers only
  non-speculative instructions, so XIF-lite needs no commit/kill channel.
- The coprocessor answers in the handshake cycle: `issue_accept=1` (mine) or 0.
  A reject becomes an illegal-instruction trap in the core one cycle later.
- The core **waits** (`XIF_WAIT`) until the result handshake, then retires.
- An interrupt can only preempt before the offer is first visible.

Compare these choices with CV-X-IF, RoCC and PCPI in the
[mapping table](../../ext/README.md#how-xif-lite-relates-to-real-interfaces).

## 3. Create your copy and watch it fail

```sh
cd ~/rv-lab
export LAB_BUILD_DIR="$PWD/build/course"
export LAB_CORE_PRESET=ant_j0
export LAB_MEMORY_ADAPTER=ii1
make lab10-init
make compare SOURCE=student/dot.c EXT=xacc RTL_DIR=$PWD/student/lab10/rtl
```

`lab10-init` copies `rtl/` to `student/lab10/rtl` and adds the interface
(`common/xif_lite_if.sv`), the core side (`simple/rv_backend.sv`,
`simple/rv_core_simple.sv`), the wrapper that places the coprocessor next to the
core (`compat/teaching_cpu.sv`), and the coprocessor `coproc/xacc_coproc.sv`.

**Expected (an intended failure):** `HW FAIL`, `trap: cause=2 … value=0x0000002b`.
The first `xacc.clr` was offered and rejected: the skeleton accepts nothing.

## 4. Fill the four TODOs in `coproc/xacc_coproc.sv`

The skeleton already has the decoded `is_clr`/`is_dot4`/`is_rd`, the busy flag,
the latency counter, the captured operands, and a `dot4()` function.

1. `TODO(lab10-1)` **Accept** exactly the three XACC encodings. Everything else
   must be rejected so the core traps.
2. `TODO(lab10-2)` **Promise a write** (`issue_writeback`) only for `xacc.rd`.
3. `TODO(lab10-3)` **Update `acc`** when the instruction completes (in the
   `result_fire` branch): clear, add `dot4(rs1_r, rs2_r)`, or keep it.
4. `TODO(lab10-4)` **Return the result**: `acc` and `result_we=1` for `xacc.rd`;
   `result_we=0` otherwise.

The core checks the protocol with assertions. If one fires, the simulator stops
with a message such as `XIF result_we differs from issue_writeback`; read it
before reading waveforms. Repeat the step 3 command until `COMPARE PASS`.

## 5. Check it properly

```sh
make lab10-check
```

This runs `tests/ext_xacc.c` and `dot.c` at coprocessor latencies 1 and 3, O0/O2,
fast and stressed memory, with interrupts at random points, and once more through a
shim that randomly stalls both XIF channels; then the 17-case smoke regression. The
directed test checks reset and clear, accumulation, that `acc` survives other
instructions and calls, 32-bit wrap-around (65,537 × 65,536), 400 random commands
against a software model, register forms, and eleven words that must be rejected
**without changing `acc`** (wrong funct7/funct3, nonzero unused fields, and the
XDOT4 word, which the Lab 10 CPU does not implement).

**Expected:** `EXT-TEST PASS: 16/16 cases` and `REGRESSION PASS: 17/17 cases`.

## 6. See the handshake

```sh
make view SOURCE=student/dot.c EXT=xacc RTL_DIR=$PWD/student/lab10/rtl TRACE_SYMBOL=dot_kernel
make view SOURCE=student/dot.c EXT=xacc RTL_DIR=$PWD/student/lab10/rtl XACC_LATENCY=4 TRACE_SYMBOL=dot_kernel
```

In the cycle viewer, step through one loop iteration. `xacc.dot4` shows
`XIF REQ` for one cycle and `XIF WAIT` ("W") until the result: one wait cycle at
latency 1, four at latency 4. The loads still take three cycles each.

## 7. Measure: one source, three implementations

With both Lab 09 and Lab 10 complete:

```sh
make ext-compare
```

This runs the starter `docs/course/starter/dot.c` (or your file with
`SOURCE=student/dot.c`) as software on the bundled CPU, software and XDOT4 on your
Lab 09 CPU, and software and XACC on your Lab 10 CPU at latencies 1, 2, 4 and 8. Every run must give the same dot
product. It prints a table and writes `build/course/extensions/compare.html`
(open it with `make serve`).

**Expected shape:** software ≈16,400 ROI cycles; XDOT4 and XACC at latency 1 both
≈3,360 (≈4.9×); XACC then loses a fixed number of cycles for every extra cycle of
latency (≈3.2× at latency 8). XACC always retires 256 fewer instructions than XDOT4.

Explain the two observations from the loop:

- Why do XDOT4 and XACC at latency 1 tie, although XACC executes one instruction
  fewer per word? (Count execute cycles per instruction in the viewer.)
- Measure the slope in cycles per latency step. Why is it 258 and not 256?
  Predict the cycles at latency 16, then measure: `make ext-compare LATENCIES=16`.
- Optional: repeat one latency-1 and one latency-4 run with `MEMORY=stress`
  (`make compare SOURCE=student/dot.c EXT=xacc RTL_DIR=$PWD/student/lab10/rtl MEMORY=stress XACC_LATENCY=4`).
  Why does the coprocessor latency disappear? (Hint: what is the core waiting
  for while the coprocessor works, and when does the next instruction arrive?)
  Run XDOT4 with `MEMORY=stress` too: which implementation is faster now, and why
  does one fewer instruction per word matter more than the handshake here?

## 8. When is a coprocessor the right answer?

Here the coprocessor cannot win on cycles: each command carries only two words
and the core waits for it. Use your measurements and the instructor's synthesis
results in the [expected results](../expected-results.md#lab-10) to argue:

- What did XACC remove from the core compared with XDOT4 (core RTL changes, the
  EX-stage path), and what did it add (interface, wait cycles, private state)?
- Which change to the *operation* (more work per command, data reuse inside the
  coprocessor, a memory port) or to the *interface* (not waiting for commands that
  write no register) would make a coprocessor worth its handshake?
- What would an operating system need before two programs could share `acc`?

## Checkpoint

- Report your `ext-compare` table and the latency at which XACC stops beating
  the software baseline by at least 3×.
- Explain the tie at latency 1 from per-instruction cycle counts.
- Explain why a rejected word must not change `acc`, and how the test checks it.
- Name one system function (speculation, interrupts, context switch, memory
  order) that XIF-lite avoids, and how CV-X-IF or RoCC handles it instead.
