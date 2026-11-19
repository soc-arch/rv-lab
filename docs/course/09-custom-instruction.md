# Lab 09 — Add a custom instruction

**Goal:** Add one new instruction to the CPU as a building block in the execute stage, prove it on Spike and RTL, and measure what it buys on the same program.
**Prerequisite:** Labs 01, 04 and 05. Background: the lecture *Extending RISC-V with custom instructions* (the five design questions).
**Keep:** Your three TODO edits, a passing `make lab09-check`, and a before/after measurement table.

**Reference:** [Expected result](../expected-results.md#lab-09) · [Extension contract](../../ext/README.md). Run the exercise yourself and record your own results.

This is the first lab that changes the CPU. You work on your own copy in
`student/lab09/rtl`; the bundled `rtl/` and Labs 01–08 stay unchanged.

## Background: how a custom instruction gets into a RISC-V CPU

Read this section before the procedure. It explains every decision behind XDOT4,
from the opcode bits to the cycle in which the result is written. The procedure
in sections 0–8 then asks you to implement exactly these decisions.

### B1. A custom instruction is a contract between layers

One instruction crosses five layers, and each layer asks one question:

```text
 C program        assembler          decoder             execution unit       state
 xdot4(a, b)  ->  .insn emits the -> finds the opcode -> computes the result -> rd is
 (API header)     32-bit word        and claims it       (fu_xdot4)            written
   Q5 compiler                     Q2 operation        Q3 implementation    Q4 operands
                  Q1 baseline core: ISA, pipeline, register-file ports, extension hook
```

| Question | Answer for XDOT4 on this CPU |
|---|---|
| Q1 Baseline | HY-RV P1.F0: RV32IM, machine mode, one instruction in the backend at a time, a register file with **2 read ports and 1 write port** |
| Q2 Operation | Four signed 8-bit products and their sum: the inner step of an int8 dot product |
| Q3 Implementation | A **building block**: a combinational unit beside the ALU, finished in the same cycle |
| Q4 Operands | Two source registers (8 packed int8 values) and one destination: fits 2R1W exactly |
| Q5 Compiler | Level 2: an inline-assembly wrapper in a header; no compiler changes |

Q3 and Q4 decide each other: because the operation needs only two inputs and
one output, it can live inside the pipeline without new ports or state.

### B2. Where custom instructions are allowed: the opcode map

A 32-bit RISC-V instruction has `inst[1:0] = 11`. Bits `inst[6:2]` select one of
32 **major opcodes**:

```text
inst[4:2] ->   000      001       010       011       100      101    110            111
inst[6:5]
   00         LOAD     LOAD-FP   custom-0  MISC-MEM  OP-IMM   AUIPC  OP-IMM-32      (>32b)
   01         STORE    STORE-FP  custom-1  AMO       OP       LUI    OP-32          (>32b)
   10         MADD     MSUB      NMSUB     NMADD     OP-FP    OP-V   custom-2       (>32b)
   11         BRANCH   JALR      reserved  JAL       SYSTEM   OP-VE  custom-3       (>32b)
```

The current specification (version 20260120) sets aside four major opcodes for
non-standard extensions: **custom-0** (`0001011` = `0x0B`), **custom-1**
(`0101011` = `0x2B`), custom-2 (`0x5B`) and custom-3 (`0x7B`). Standard extensions
will not use them. (Older versions of the specification marked custom-2 and
custom-3 as possible RV128 opcodes; you may still see that note in older tables.)
The `reserved` entries and the `inst[4:2] = 111` column (longer instructions) must
not be used. This lab puts XDOT4 in custom-0; Lab 10 gives the whole of custom-1 to
a coprocessor.

### B3. Inside one major opcode: the R-type format

XDOT4 uses the standard R-type layout:

```text
 31      25 24   20 19   15 14  12 11    7 6      0
+----------+-------+-------+------+-------+--------+
|  funct7  |  rs2  |  rs1  |funct3|  rd   | opcode |
+----------+-------+-------+------+-------+--------+
  0000001    rs2     rs1     000     rd    0001011     xdot4 rd, rs1, rs2
```

- `opcode` tells the decoder the instruction is yours.
- `funct7` and `funct3` are 10 bits you define: one R-type opcode holds up to
  1,024 operations. XDOT4 takes `funct7 = 1, funct3 = 0`.
- `rs1`, `rs2`, `rd` are **register numbers**, not data. Keeping them in the
  standard positions matters: this CPU's decoder always reads `rs1 = inst[19:15]`
  and `rs2 = inst[24:20]`, and the register file is read from those fields for
  every instruction. A custom instruction that keeps the fields in place gets its
  operands with no extra hardware, before the decoder has even decided what the
  instruction is.

**MASK and MATCH.** A decoder identifies an instruction with two constants: the
word is XDOT4 when `(word & MASK) == MATCH`. MASK has a 1 in every bit that must
have a fixed value, MATCH holds those values:

| Field | Bits | In MASK | Value in MATCH |
|---|---|---|---|
| funct7 | 31:25 | `0xFE000000` | `0000001` → `0x02000000` |
| rs2, rs1 | 24:15 | — (any register) | — |
| funct3 | 14:12 | `0x00007000` | `000` → `0x00000000` |
| rd | 11:7 | — (any register) | — |
| opcode | 6:0 | `0x0000007F` | `0001011` → `0x0000000B` |
| **Total** | | **`0xFE00707F`** | **`0x0200000B`** |

Worked example, `xdot4 a0, a0, a1` (a0 = x10, a1 = x11):
`0000001 01011 01010 000 01010 0001011` = **`0x02B5050B`**.
Every other custom-0 word (another funct7 or funct3) is still not an instruction
of this CPU and must raise an illegal-instruction exception.

### B4. What XDOT4 computes, and why it has no accumulator

```text
rs1 = 0x04030201  ->  bytes [1, 2, 3, 4]      (byte 0 = bits 7:0)
rs2 = 0x08070605  ->  bytes [5, 6, 7, 8]
rd  = 1*5 + 2*6 + 3*7 + 4*8 = 70 = 0x00000046
```

Each byte is a signed int8 (−128..127), so each product is in −16,256..16,384 and
needs 16 bits; the sum of four is in −65,024..+65,536 and needs **18 bits**
(65,536 does not fit in 17 signed bits). The unit sign-extends the 18-bit sum to 32.

A dot product of N words needs `sum += xdot4(a[i], b[i])`. A "multiply-accumulate"
form `rd = rd + dot4(rs1, rs2)` would save the ADD, but it reads **three**
registers (rs1, rs2 and the old rd). With two read ports there are three choices:
add a third port (CORE-V CV32E40P does this for `cv.sdotsp.b`: area and timing for
every instruction), read in two cycles (an extra stall), or keep the running sum
inside the unit (new private state). XDOT4 takes none of them and leaves the ADD
in software. Lab 10 tries the third choice.

### B5. How the instruction travels through this CPU

The P1 backend holds **one instruction** at a time. A functional view (these are
not separate pipeline stages):

```text
             +-------------------- backend: one instruction register (IR) ------------------+
fetch  --->  | decode  ->  RF read (2 ports, same cycle)  ->  ALU | branch | MUL | DIV | LSU | ---> result mux ---> RF write
(frontend)   |  claim                                    \-> fu_xdot4 (new) ------------+  |      (+1 input)       (1 port)
             +------------------------------------------------------------------------------+
```

The backend's state machine tells how long each instruction occupies the IR:

| State | Used by | Cycles |
|---|---|---|
| `IDLE` | ALU, branch, CSR, **XDOT4**: decode, read, compute and retire in one cycle | 1 |
| `MEM_REQ` → `MEM_RESP` → `MEM_WB` | loads and stores (fast memory) | 3 |
| `MUL_WAIT` | multiply | 2 |
| `DIV_WAIT` | divide | 34 |

XDOT4 joins the one-cycle group, so the change is small: one claim, one unit, one
result-mux input. No new state, no stall logic, and no forwarding: the next
instruction enters the IR only after this one has written its result. You will
see this in the cycle viewer: XDOT4 occupies the execute slot for exactly one
cycle, the loads for three.

### B6. The illegal-instruction path, and the one place that claims an encoding

The shared decoder (`rv32_decoder.sv`) recognizes only standard opcodes and marks
every custom word as illegal. A second check in the backend (`encoding_legal()`)
rejects reserved funct3/funct7 values of standard opcodes. When the instruction
in the IR is illegal, the backend takes a **precise** exception: it does not
retire, writes no register, and traps with `mcause = 2` and `mtval = the
instruction word`.

Adding an instruction therefore means overriding that verdict in **exactly one
place**: `xdot4_match()`. If the claim is too narrow, the CPU traps on XDOT4
(your first failure in step 3). If it is too wide (for example a MASK that ignores
funct7), the CPU executes words that are not XDOT4 and the directed test's nine
"illegal neighbour" checks fail. The same function also tells the backend that
XDOT4 writes rd.

### B7. How software emits the instruction

| Level | What exists | Effort |
|---|---|---|
| 1 Raw encoding | `.insn` in assembly; the assembler builds the word | no tool changes |
| 2 API header | a function such as `xdot4(a, b)` with inline assembly | **this lab** |
| 3 Builtin | the compiler knows the name and `-march` flag | compiler patch |
| 4 Auto-selection | the compiler finds `acc += a[i]*b[i]` patterns itself | cost model, back end |

`ext/include/xdot4.h` is level 2:

```c
__asm__ (".insn r CUSTOM_0, 0, 1, %0, %1, %2" : "=r"(r) : "r"(a), "r"(b));
```

`.insn r opcode, funct3, funct7, rd, rs1, rs2` builds the R-type word; note that
the **argument order is not the bit order**. The constraints let the compiler
choose free registers. Use `.insn`, not `.word`: a disassembler shows `.insn` as an
instruction (`.insn 4, 0x02d7070b`). Without `HAVE_XDOT4` the same function is
portable C (`xdot4_ref()`), which is how `EXT=sw` runs the same program on any
RV32IM core.

### B8. How we know the hardware is right

Every lab run executes the **same ELF** on Spike and on the RTL and compares the
complete result signature. Spike does not know XDOT4, so the lab loads a small
Spike extension (`ext/spike/hyrv_ext.cc`) written from the contract, independently
of the RTL. It registers exactly `MATCH 0x0200000B / MASK 0xFE00707F`; every other
word still traps in Spike, just as it must in your CPU. The directed test adds
hand-computed vectors, 512 random word pairs, register forms (`rd = rs1 = rs2`,
`rd = x0`), dependences, illegal neighbours and interrupts at random points.

### B9. What speedup to expect, before measuring

Amdahl's law: an instruction removes only the time it replaces. Per 32-bit word of
the dot product, from the actual compiled loops:

| | Instructions per word | Cycles per word (fast memory) |
|---|---|---|
| Software `xdot4_ref()` | about 48 (shifts, sign-extensions, 4 × `mul`, adds, loop) | about 64 |
| XDOT4 | 7: `addi`, `addi`, `lw`, `lw`, `xdot4`, `add`, `bne` | about 13 (2 loads × 3 + 4 × 1 + redirect) |

The two loads and the loop control remain, so the kernel becomes about 4.9× faster,
not 21×. Measure it in step 7 and explain the gap from these counts.

## Procedure

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
