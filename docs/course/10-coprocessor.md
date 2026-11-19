# Lab 10 — Extend the CPU through a coprocessor interface

**Goal:** Move the same dot product out of the pipeline into a coprocessor with private state, connect it through a handshake interface, and measure what the interface costs.
**Prerequisite:** Lab 09.
**Keep:** Your four TODO edits, a passing `make lab10-check`, the comparison table from `make ext-compare`, and your latency analysis.

**Reference:** [Expected result](../expected-results.md#lab-10) · [Extension contract and interface](../../ext/README.md#lab-10-xacc-a-coprocessor-with-private-state). Run the exercise yourself and record your own results.

## Background: extending a CPU through a coprocessor interface

This section explains the design of XACC and of the XIF-lite interface: which
opcode, which signals, when the core hands an instruction over, why the core
waits, and what a non-blocking design would need. The procedure then asks you to
build the coprocessor side.

### C1. Building block or coprocessor?

Both paths start at the decoder; they differ in where the unit sits and who
controls the instruction.

| Aspect | Building block (Lab 09) | Coprocessor (Lab 10) |
|---|---|---|
| Location | a unit inside EX | a separate module beside the core |
| Control | the pipeline controls it | the unit has its own decode, state and control |
| Call overhead | none | a handshake for each command |
| Core timing | the unit is in the EX path | only the interface touches the core |
| Operands | register-file ports only | register values, **private state**, possibly memory |
| Core changes | decoder, EX, result mux | decoder + interface, once; later units reuse it |
| Flush, exceptions, interrupts | the pipeline handles them | the interface must define them |

Rule of thumb: small and stateless → inside the core; large, stateful or
memory-bound → beside the core. XACC is deliberately small, so you can see the
interface cost clearly; the same interface would carry a much larger unit.

### C2. Same kernel, new operand home

Lab 09 kept the running sum in a register and paid one ADD per word. XACC keeps
the sum in the coprocessor (**`acc`**, 32 bits). That is the third way to get a
third operand (B4 of Lab 09): no third read port and no ADD, but new
**architectural state** that someone must clear, read out, and (in a real
system) save and restore.

```text
Lab 09 loop per word:  lw, lw, xdot4 t, a, b, add sum, sum, t, (loop)
Lab 10 loop per word:  lw, lw, xacc.dot4 a, b,                 (loop)
after the loop:        xacc.rd sum
```

### C3. Opcode: the whole of custom-1 belongs to the coprocessor

The core does not know the individual XACC commands. It sends **every custom-1
word** (`opcode = 0101011 = 0x2B`) to the coprocessor, and the coprocessor decides
whether the exact word is one of its instructions. That is how real coprocessor
interfaces work: CV-X-IF offers instructions the core does not recognize, RoCC
routes the custom opcodes to the accelerator. A new command then needs no core
change.

```text
 31      25 24  20 19  15 14 12 11   7 6      0
 0000000    00000  00000  000    00000 0101011      xacc.clr            acc = 0
 0000001    rs2    rs1    000    00000 0101011      xacc.dot4 rs1, rs2  acc = acc + dot4(rs1, rs2)
 0000010    00000  00000  000    rd    0101011      xacc.rd   rd        rd = acc
```

| Command | MATCH | MASK | Fixed fields | Writes rd |
|---|---|---|---|---|
| `xacc.clr` | `0x0000002B` | `0xFFFFFFFF` | all | no |
| `xacc.dot4` | `0x0200002B` | `0xFE007FFF` | funct7, funct3, rd = 0, opcode | no |
| `xacc.rd` | `0x0400002B` | `0xFFFFF07F` | funct7, rs2 = 0, rs1 = 0, funct3, opcode | yes |

Unused register fields **must be zero**. A strict decode keeps those encodings
free for future commands and catches garbage words. `acc` wraps modulo 2³²; reset
clears it. custom-0 (Lab 09's XDOT4) is not implemented on this CPU and traps.

### C4. XIF-lite: the interface definition

XIF-lite (`rtl/common/xif_lite_if.sv` in your copy) has two channels. Each uses
**valid/ready**: a transfer happens in a cycle where both are 1; until then the
sender keeps `valid` high and every payload signal stable.

```text
            issue channel (core -> coprocessor)
         +---------------------------------------------------------+
         | issue_valid  ->          <- issue_ready                 |
  CORE   | issue_insn, issue_pc ->  <- issue_accept (handshake cyc)|   COPROCESSOR
 (P1 +   | issue_rs1, issue_rs2 ->  <- issue_writeback             |   (xacc_coproc)
 XIF     +---------------------------------------------------------+
 logic)  | result_ready ->          <- result_valid                |   private acc
         |                          <- result_data, result_we      |
         +---------------------------------------------------------+
            result channel (coprocessor -> core)
```

| Signal | Dir. | Meaning |
|---|---|---|
| `issue_valid` | core → | An instruction is offered |
| `issue_ready` | ← cop. | The coprocessor can take an instruction now (XACC: when not busy) |
| `issue_insn`, `issue_pc` | core → | The 32-bit word and its PC |
| `issue_rs1`, `issue_rs2` | core → | Source **values**, read by the core from its register file |
| `issue_accept` | ← cop. | In the handshake cycle: 1 = "mine", 0 = "not mine" (combinational from `issue_insn`) |
| `issue_writeback` | ← cop. | In the handshake cycle: the accepted instruction will write rd (0 when rejected) |
| `result_valid` | ← cop. | The accepted instruction has completed |
| `result_ready` | core → | The core takes the result now |
| `result_data`, `result_we` | ← cop. | Value for rd and whether to write it; `result_we` must equal `issue_writeback` |

Contract rules:

1. The core offers only **non-speculative** instructions (C5), one at a time.
2. While `issue_valid = 1` and `issue_ready = 0`, all issue fields stay stable.
3. A rejected word changes no coprocessor state; the core turns it into an
   illegal-instruction exception.
4. Exactly one result per accepted instruction, **no earlier than the cycle after
   acceptance**, driven from coprocessor registers and held until `result_ready`.
5. The core retires the instruction and writes rd (when `result_we` and rd ≠ x0)
   in the result handshake cycle.
6. An interrupt can preempt the instruction only before the offer is first
   visible; afterwards the instruction always completes first.

### C5. When does the core hand an instruction over?

Follow one `xacc.dot4` through the P1 backend:

1. **Fetch and admission.** The frontend fetches the word. When the previous
   instruction retires, the word enters the instruction register (IR) in the same
   edge. A custom-1 word without a fetch fault goes directly to state `XIF_REQ`,
   just as a load goes to `MEM_REQ`.
2. **Offer (`XIF_REQ`).** In that cycle the register file is read through the
   instruction's rs1/rs2 fields (asynchronous read), and the core drives
   `issue_valid` with the word, its PC and the two values. If `issue_ready` is
   low, the core keeps offering the same payload.
3. **Answer.** In the handshake cycle the coprocessor sets `issue_accept`:
   - accept → the core goes to `XIF_WAIT` and records `issue_writeback`;
   - reject → the core records the reject in a register and, **in the next
     cycle**, takes an illegal-instruction exception (`mcause = 2`,
     `mtval = word`). The instruction is still in the IR, so the trap is precise.
4. **Wait (`XIF_WAIT`).** The core sets `result_ready` and waits.
5. **Retire.** In the result handshake cycle the instruction retires, rd is
   written if promised, and the next instruction enters the IR.

**Why "non-speculative" is automatic here.** The backend holds only one
instruction, and the next one enters the IR only when the previous one has
retired. A mispredicted branch redirects the frontend when it completes, and the
wrong-path word never enters the IR. So the instruction in the IR is always on the
correct path, and every older instruction has already finished: nothing can cancel
it later except an interrupt, and rule 6 handles that. A pipelined core such as
CV32E40X offers instructions from decode, while older instructions may still
branch or trap; that is why CV-X-IF needs a separate **commit** channel ("commit"
or "kill" each offered instruction). XIF-lite does not.

**Why the reject is registered.** A combinational path from the coprocessor's
`issue_accept` into the core's trap and redirect logic would make the core's
timing depend on the coprocessor's decoder, and in simulation such a cross-module
path caused an evaluation loop. One flop breaks it, at the cost of one cycle on an
illegal word only.

### C6. Blocking, and what non-blocking would need

XIF-lite is **blocking**: after the offer, the core waits until the result. One
instruction at a time, no instruction IDs.

What that buys:

- Exceptions stay precise: the instruction is the only one in flight.
- No scoreboard: no later instruction can read rd before the result is written.
- No result ordering or write-port conflict: the result uses the core's single
  write port while the core is idle.
- Interrupts have a clear boundary (rule 6).

What it costs: the core does nothing useful while the coprocessor works. You will
measure it: every extra cycle of `XACC_LATENCY` adds one cycle per `xacc.dot4`.

A **non-blocking** interface would let the core continue after the offer. Each
item below is a feature that real interfaces add for that:

| Problem | Typical solution |
|---|---|
| Several instructions in flight | an **ID** per offer (CV-X-IF `id`), results matched by ID |
| A later instruction reads rd before the result | a **scoreboard** on rd; stall that reader |
| The result and a core instruction both need the write port | write-port arbitration, or a second port |
| An older instruction traps after the offer | **commit/kill** of speculative offers (CV-X-IF commit channel) |
| Software must know when all commands are done | a **busy** signal and a fence (RoCC `busy`, Gemmini `fence`) |
| A fault found after the instruction retired | imprecise exception or interrupt from the coprocessor |

`xacc.dot4` writes no register, so it is the easy case: a non-blocking core could
"fire and forget" it and only wait at `xacc.rd`. This is one of the discussion
questions.

### C7. Cycle by cycle

Latency 1, `xacc.dot4` accepted:

```text
cycle        n                    n+1                       n+2
state        XIF_REQ              XIF_WAIT                  next instruction
issue        valid=1 ready=1      -
             accept=1 wb=0
result       -                    valid=1 ready=1 we=0
             coproc captures      acc <= acc + dot4(..)
             rs1/rs2              instruction retires
```

`xacc.dot4` occupies the IR for **2 cycles** at latency 1 and `1 + LATENCY` in
general. XDOT4 took 1 cycle but needed an extra ADD (1 cycle), so the two tie at
latency 1. That tie is exactly what you measure in step 7.

Latency 3: the coprocessor counts down from 2 after acceptance; `XIF_WAIT` lasts
3 cycles. Rejected word (for example `0x0600002B`):

```text
cycle        n                    n+1                              later
state        XIF_REQ              XIF_REQ (offer withdrawn)        handler runs
issue        valid=1 ready=1      -
             accept=0             illegal-instruction exception:   after the frontend
                                  mcause 2, mtval 0x0600002B,      has fetched from
                                  redirect to mtvec, IR emptied    mtvec (variable)
```

### C8. Inside the coprocessor: the parts you will complete

```text
          issue_insn --> [ decode: is_clr / is_dot4 / is_rd ] --> issue_accept, issue_writeback   (TODO 1, 2)
                                                         |
 issue_valid & issue_ready & issue_accept  ---------------+--> busy_r = 1, count_r = LATENCY-1,
                                                              capture op and rs1/rs2
 every cycle while busy: count_r - 1  ---------------------> result_valid = busy_r & (count_r == 0)
 result handshake: busy_r = 0, update acc  ----------------> (TODO 3)
 result_data / result_we from registers  -----------------> (TODO 4)
```

Two design rules to notice:

- **State changes only at completion.** `acc` is updated in the result handshake,
  never at acceptance. If an instruction could be cancelled before completing,
  nothing would have to be undone.
- **Capture the operands.** The core keeps them stable while it waits, but a
  coprocessor that captures its inputs at acceptance does not depend on that,
  and could accept the next instruction early in a non-blocking design.

### C9. What a real system would still need

| Function | Question | XIF-lite / XACC answer |
|---|---|---|
| Speculation | Can the core cancel an accepted instruction? | Never needed: only non-speculative offers |
| Completion | When is the result safe to use? | At the result handshake; the core waits |
| Interrupts | Can a long operation delay an interrupt? | Yes. Once the offer is visible, an interrupt waits for the `issue_ready` stall (if any), the `LATENCY` cycles, the retirement and the arrival of the next instruction |
| Context switch | Who saves `acc` when the OS switches programs? | Saving is easy (`xacc.rd`), restoring is not: there is no `xacc.wr`. An OS could only rebuild a value by replaying `xacc.clr` and many `xacc.dot4` (for example `dot4(0x80808080, 0x80808080) = 65,536` steps plus `dot4(1, 1) = 1` steps), so in practice one program owns the unit. A real design adds a write command, and RISC-V's `mstatus.XS` field lets an OS track whether such extension state is dirty |
| Memory | May the unit access memory? | No memory channel (like CV-X-IF 1.0). RoCC and NICE have one |
| Faults | How does software see an error? | Only the illegal-instruction reject |

### C10. Comparison with real coprocessor interfaces

| | XIF-lite (this lab) | CV-X-IF 1.0 (standard) | RoCC (Rocket, BOOM) | PCPI (PicoRV32) | NICE (Nuclei, E203) |
|---|---|---|---|---|---|
| Offer | issue: insn + rs values | issue + register channels | `cmd`: inst, rs1, rs2 | every unknown insn + rs values | request: insn, rs values |
| Accept/reject | `issue_accept` | issue response `accept` | by custom opcode and funct | `pcpi_wait`/`pcpi_ready`; no reply in 16 cycles → illegal | — |
| Speculation | never | commit / kill channel | Rocket: sent from write-back; BOOM: after the point of no return | core waits | issued at dispatch; E203 keeps running independent instructions |
| In flight | 1 (blocking) | many, by ID | queued | 1 | tracked as long-latency operations (E203) |
| Result | data + we | id, data, rd, we | `resp`: rd, data | `pcpi_wr`, `pcpi_rd` | response: data, error |
| Memory | none | none in 1.0 | L1 cache / TileLink | none | through the core's data bus |

XIF-lite is a teaching subset with CV-X-IF vocabulary; it is not CV-X-IF compliant.
Cores advertise specific CV-X-IF revisions: CV32E40X, for example, documents its
own revision, which still has a memory channel. Always compare against the
revision a core actually implements.

### C11. Expected performance

Per word, the XACC loop has 6 instructions: `addi`, `addi`, `lw`, `lw`,
`xacc.dot4`, `bne`. At latency L the IR is busy for about `3 + 3 + (1 + L) + 3`
cycles plus the branch redirect, so each extra cycle of latency costs one cycle
per word. With 256 words plus `xacc.clr` and `xacc.rd`, predict the slope before
you measure it in step 7.

## Procedure

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

## 4. Fill the four TODOs in the coprocessor

Edit only `coproc/xacc_coproc.sv` in your copy. The skeleton already has the decoded `is_clr`/`is_dot4`/`is_rd`, the busy flag,
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
