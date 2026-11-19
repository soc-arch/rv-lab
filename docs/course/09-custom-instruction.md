# Lab 09 — Add a custom instruction

**Goal:** Add one new instruction to the CPU as a building block in the execute stage, prove it on Spike and RTL, and measure what it buys on the same program.
**Prerequisite:** Labs 01, 04 and 05. Background: the lecture *Extending RISC-V with custom instructions* (the five design questions).
**Keep:** Your three TODO edits, a passing `make lab09-check`, and a before/after measurement table.

**Reference:** [Expected result](../expected-results.md#lab-09) · [Extension contract](../../ext/README.md). Run the exercise yourself and record your own results.

This is the first lab that changes the CPU. You work on your own copy in
`student/lab09/rtl`; the bundled `rtl/` and Labs 01–08 stay unchanged.

## 0. Check the extra tool requirement

Labs 09–10 build a small Spike model of the new instructions, so Spike's headers
must be installed next to Spike. Run `make doctor` and find the line
`Spike extension headers (Labs 09-10): …/include/riscv/extension.h`. If it says
`MISSING`, ask your TA (or set `SPIKE_INCLUDE` to Spike's `include` directory).

## 1. Read the contract

The kernel is an inner product of signed 8-bit numbers, four packed per word.
The proposed instruction does one word pair at a time:

```text
xdot4 rd, rs1, rs2      rd = rs1.byte0*rs2.byte0 + rs1.byte1*rs2.byte1
                           + rs1.byte2*rs2.byte2 + rs1.byte3*rs2.byte3

 31      25 24  20 19  15 14 12 11   7 6      0
 0000001    rs2    rs1    000    rd    0001011     (custom-0)
```

Answer the five design questions for it before you touch the RTL:

| Question | XDOT4 answer |
|---|---|
| Q1 Baseline | This CPU: RV32IM, register file with 2 read ports and 1 write port |
| Q2 Operation | Four int8 products and their sum: about 21 RV32IM instructions in software |
| Q3 Implementation | Building block: a new unit beside the ALU, finished in one cycle |
| Q4 Operands | 2 register reads, 1 write — fits the existing ports, no new state |
| Q5 Compiler | Level 2: a header with inline `.insn` (`ext/include/xdot4.h`) |

Open [the contract](../../ext/README.md#lab-09-xdot4-a-building-block-in-ex) and
check the two test vectors by hand: `0x04030201 · 0x08070605 = 70` and
`0xFC03FE01 · 0x02FF0403 = -16`. Note the range of the sum (−65,024..65,536)
and why 18 bits are enough.

## 2. Measure the software baseline

```sh
cd ~/rv-lab
export LAB_BUILD_DIR="$PWD/build/course"
export LAB_CORE_PRESET=ant_j0
export LAB_MEMORY_ADAPTER=ii1
cp docs/course/starter/dot.c student/dot.c
make compare SOURCE=student/dot.c EXT=sw COMMITS=1
```

`dot.c` computes a 1024-element dot product. Only `dot_kernel()` is inside the
ROI; the golden value comes from a separate plain C loop outside it. With
`EXT=sw`, `xdot4()` is the portable C function `xdot4_ref()`, so this is the
same algorithm in software.

**Expected:** `COMPARE PASS`, `kernel: software xdot4_ref()`, and an ROI of about
16,400 cycles and 12,300 retired instructions. Open the report and look at the
most frequent PCs within the ROI: shifts, sign-extensions, four `mul` and the adds
per word. That is the time the instruction can remove (Amdahl: the loads and the
loop control stay).

## 3. Try the instruction before the CPU has it

```sh
make compare SOURCE=student/dot.c EXT=xdot4
```

`EXT=xdot4` defines `HAVE_XDOT4`, so `xdot4()` emits one custom-0 word. The lab
also loads the Spike model of XDOT4, so Spike knows the instruction.

**Expected (an intended failure):** `SW PASS`, `HW FAIL`, and a line such as
`trap: cause=2 pc=0x800008b8 value=0x02d7070b`. Cause 2 is an illegal
instruction; the value is the instruction word (the registers inside it depend
on the compiler). The report page shows the same trap table. Find the word in
`program.dis`: the disassembler prints it as `.insn 4, 0x…` because it does not
know the name. The unmodified CPU is behaving correctly: an encoding it does not
implement must trap.

## 4. Create your CPU copy

```sh
make lab09-init
```

This copies `rtl/` to `student/lab09/rtl` and adds three files from
`ext/lab09/overlay`: `common/fu_xdot4.sv` (new unit), a prepared
`simple/rv_backend.sv`, and `filelist.f`. The command lists your three TODOs.
The plumbing is already there: the backend instantiates `fu_xdot4`, treats
XDOT4 as a one-cycle ALU-like instruction, and marks it as writing rd.

## 5. Fill the three TODOs

Edit only the lines marked `TODO(lab09-N)`.

1. **Claim the encoding** (`simple/rv_backend.sv`, `TODO(lab09-1)`). The shared
   decoder reports every custom-0 word as illegal. `xdot4_match()` is the one place
   that overrides it. Set `XDOT4_MASK` to the bits that identify XDOT4 (opcode,
   funct3, funct7), `XDOT4_MATCH` to their values, and return
   `(w & XDOT4_MASK) == XDOT4_MATCH`. Do not include rd/rs1/rs2 in the mask.
2. **Compute** (`common/fu_xdot4.sv`, `TODO(lab09-2)`). Four signed 8×8 products,
   an adder tree, sign-extension to 32 bits. `a[8*i +: 8]` selects byte *i*;
   `$signed()` makes it signed.
3. **Write back** (`simple/rv_backend.sv`, `TODO(lab09-3)`). Add one input to the
   result multiplexer: `else if (is_xdot4) wb_data = xdot4_result;`.

After each step, run the same program on your CPU:

```sh
make compare SOURCE=student/dot.c EXT=xdot4 RTL_DIR=$PWD/student/lab09/rtl
```

| What you see | Most likely cause |
|---|---|
| `unexpected_trap`, cause 2 | TODO 1: the word is not claimed (check MASK/MATCH) |
| HW check 1 fails, value 0 or wrong | TODO 2 (arithmetic) or TODO 3 (mux) |
| Verilator build error | A syntax or width problem in your edit; read `build.log` |

## 6. Check it properly

```sh
make lab09-check
```

This runs `tests/ext_xdot4.c` on Spike and your RTL at O0/O2 with fast and
stressed memory, twice more with interrupts arriving at random points, plus
`dot.c`, then the original 17-case smoke regression on your CPU. The directed test checks hand-computed vectors, 512 random word pairs
against the C reference, register forms (`rd = rs1 = rs2`, the exact word
`0x02B5050B`, `rd = x0`), back-to-back dependences, and nine illegal neighbours
that must still trap: other funct7/funct3 values and the other custom opcodes.

**Expected:** `EXT-TEST PASS: 7/7 cases` and `REGRESSION PASS: 17/17 cases`. Do
not measure performance before this passes.

## 7. Measure the improvement

```sh
make compare SOURCE=student/dot.c EXT=xdot4 RTL_DIR=$PWD/student/lab09/rtl COMMITS=1
make compare SOURCE=student/dot.c EXT=sw    RTL_DIR=$PWD/student/lab09/rtl
```

Fill in this table from the two reports and step 2:

| Build | CPU | ROI cycles | ROI retired | CPI |
|---|---|---:|---:|---:|
| `EXT=sw` | bundled `rtl/` | | | |
| `EXT=sw` | your Lab 09 CPU | | | |
| `EXT=xdot4` | your Lab 09 CPU | | | |

**Expected:** about 16,400 → 3,350 ROI cycles (≈4.9×) and 12,300 → 1,800
instructions, with the same dot product. Software on your Lab 09 CPU takes exactly
the same cycles as on the bundled CPU: the new unit did not slow other instructions.

Why not 21×? Per word, software needs two loads, about 21 arithmetic instructions
and loop control; XDOT4 needs two loads, one XDOT4, one add and the same loop
control. Count them in the hot-PC table and explain the measured ratio from the
remaining work. Then view one iteration:

```sh
make view SOURCE=student/dot.c EXT=xdot4 RTL_DIR=$PWD/student/lab09/rtl TRACE_SYMBOL=dot_kernel
```

XDOT4 occupies the execute slot for one cycle, like `add`; the loads take three.

## 8. What it costs

Cycles are only half of performance: time = cycles × clock period. XDOT4 puts four
multipliers and an adder tree in the same cycle as the register read and the
write-back. The [expected results](../expected-results.md#lab-09) include the
instructor's logical synthesis of the bundled CPU and the Lab 09 CPU (area, and the
longest path under a tight clock). Read them and answer: if the clock period grew
by the reported fraction, would XDOT4 still pay off for this kernel? For a program
that never uses XDOT4?

## Checkpoint

- Explain why the unmodified CPU's trap in step 3 is correct behavior.
- Give your MASK and MATCH and explain each set bit.
- Report the table from step 7 and explain the ratio from instruction counts.
- State one reason to keep XDOT4 out of the core even though it is fast.
