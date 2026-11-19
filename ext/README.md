# Extending the lab CPU: XDOT4 and XACC

This directory holds everything Labs 09 and 10 add on top of the eight core labs.
Nothing here changes the bundled CPU in `rtl/` or any Lab 01–08 command.

| Path | Contents |
|---|---|
| `include/xdot4.h`, `include/xacc.h` | Software API: inline `.insn` wrappers with a portable C fallback |
| `spike/hyrv_ext.cc` | Spike reference model of both extensions, written from this document |
| `lab09/overlay/` | Files that turn a copy of `rtl/` into the Lab 09 CPU (with TODOs) |
| `lab10/overlay/` | Files that turn a copy of `rtl/` into the Lab 10 CPU + coprocessor (with TODOs) |

`make lab09-init` / `make lab10-init` copy `rtl/` to `student/labNN/rtl` and apply
the overlay. Your edits stay in `student/`, which Git ignores.

## The kernel

Both labs accelerate the same inner product of signed 8-bit values, packed four per
32-bit word (byte 0 = bits 7:0):

```text
dot4(a, b) = a.byte0*b.byte0 + a.byte1*b.byte1 + a.byte2*b.byte2 + a.byte3*b.byte3
```

Each product is in −16,256..16,384, so the sum is in −65,024..+65,536 and needs
18 signed bits. Results are sign-extended to 32 bits.

| a | b | dot4 |
|---|---|---:|
| `0x04030201` | `0x08070605` | 70 (`0x00000046`) |
| `0xFC03FE01` | `0x02FF0403` | −16 (`0xFFFFFFF0`) |
| `0x80808080` | `0x80808080` | 65,536 (`0x00010000`) |
| `0x80808080` | `0x7F7F7F7F` | −65,024 (`0xFFFF0200`) |

## Lab 09: XDOT4, a building block in EX

```text
 31      25 24  20 19  15 14 12 11   7 6      0
 0000001    rs2    rs1    000    rd    0001011      xdot4 rd, rs1, rs2   rd = dot4(rs1, rs2)
```

- Major opcode **custom-0** (`0x0B`), reserved by the RISC-V specification for
  non-standard extensions. `MATCH = 0x0200000B`, `MASK = 0xFE00707F`.
- Every other custom-0 word, and every custom-1/2/3 word, raises an
  illegal-instruction exception (mcause 2, mtval = the instruction word).
- Two register reads and one write: the existing 2R1W register file is enough.
- The Lab 09 CPU executes XDOT4 in one cycle beside the ALU, like an R-type ALU
  instruction. It has no new state, so the pipeline needs no new control.
- Assembler: `.insn r CUSTOM_0, 0, 1, rd, rs1, rs2`. Example: `xdot4 a0, a0, a1`
  is `0x02B5050B`.

## Lab 10: XACC, a coprocessor with private state

The accumulator lives inside the coprocessor (32 bits, reset to 0, wraps modulo 2³²).

```text
 31      25 24  20 19  15 14 12 11   7 6      0
 0000000    00000  00000  000    00000 0101011      xacc.clr            acc = 0
 0000001    rs2    rs1    000    00000 0101011      xacc.dot4 rs1, rs2  acc = acc + dot4(rs1, rs2)
 0000010    00000  00000  000    rd    0101011      xacc.rd   rd        rd = acc
```

| Instruction | MATCH | MASK | Writes rd |
|---|---|---|---|
| `xacc.clr` | `0x0000002B` | `0xFFFFFFFF` | no |
| `xacc.dot4` | `0x0200002B` | `0xFE007FFF` | no |
| `xacc.rd` | `0x0400002B` | `0xFFFFF07F` | yes |

- Major opcode **custom-1** (`0x2B`). Unused fields must be zero. Any other
  custom-1 word is rejected and raises an illegal-instruction exception with no
  change to `acc`. custom-0/2/3 are illegal on the Lab 10 CPU.
- `acc` changes only when an accepted instruction completes.
- Assembler: `.insn r CUSTOM_1, 0, 1, x0, rs1, rs2` (dot4), `.insn r CUSTOM_1, 0, 2, rd, x0, x0` (rd).

### XIF-lite: the coprocessor interface

The Lab 10 core sends every custom-1 instruction to the coprocessor through two
valid/ready channels (`rtl/common/xif_lite_if.sv` in your copy). One instruction is
in the coprocessor at a time, and the core waits for it (blocking).

| Signal | Direction | Meaning |
|---|---|---|
| `issue_valid` / `issue_ready` | core → / ← coprocessor | Offer of one instruction |
| `issue_insn`, `issue_pc` | core → | Instruction word and its PC |
| `issue_rs1`, `issue_rs2` | core → | Source register **values** (read by the core) |
| `issue_accept` | ← coprocessor | In the handshake cycle: 1 = mine, 0 = not mine |
| `issue_writeback` | ← coprocessor | The accepted instruction will write rd |
| `result_valid` / `result_ready` | ← / → | Completion of the accepted instruction |
| `result_data`, `result_we` | ← coprocessor | Value for rd, and whether to write it |

Rules:

1. The core offers only non-speculative instructions. While `issue_valid=1` and
   `issue_ready=0`, all issue fields stay stable.
2. In the handshake cycle the coprocessor answers `issue_accept` combinationally
   from `issue_insn`, and `issue_writeback` (0 for a reject). A reject changes no
   coprocessor state. The core records it
   and raises the illegal-instruction exception in the next cycle, before the
   instruction leaves the core; no coprocessor output reaches the trap logic
   combinationally.
3. The coprocessor returns exactly one result per accepted instruction, no
   earlier than the cycle after acceptance, from registers, held until
   `result_ready`. `result_we` equals the `issue_writeback` promise.
4. The core retires the instruction and writes rd (if `result_we` and rd ≠ x0) in
   the result handshake cycle.
5. An interrupt can preempt the instruction only before the first offer cycle.
   After the offer is visible, the instruction always completes first.

The core's execute states for this are `XIF_REQ` (offer) and `XIF_WAIT` (wait for
the result). The cycle viewer shows both.

`LATENCY` (make variable `XACC_LATENCY`, 1..255, default 1) is the number of cycles
from the issue handshake to `result_valid`. It lets you measure the cost of the
interface without changing the arithmetic.

### How XIF-lite relates to real interfaces

XIF-lite uses CV-X-IF vocabulary to make the comparison easy. It is **not**
CV-X-IF compliant.

| Concern | XIF-lite (this lab) | CV-X-IF 1.0 (CV32E40X, CVA6) | RoCC (Rocket) | PCPI (PicoRV32) |
|---|---|---|---|---|
| Instruction and operands | one issue channel | issue + register channels | `cmd` (inst, rs1, rs2) | `pcpi_insn`, `pcpi_rs1/rs2` |
| Accept/reject | `issue_accept` | issue response `accept` | decoded by funct/flags | unit waits or ignores; core traps after 16 cycles |
| Speculation | never offered speculatively | commit channel: commit or kill | issued from write-back | core waits |
| Result | `result` channel | result channel (id, data, rd, we) | `resp` (rd, data) | `pcpi_wr`, `pcpi_rd`, `pcpi_ready` |
| Outstanding | 1 | many, by `id` | queued | 1 |
| Memory access | none | none in 1.0 | L1 cache / TileLink | none |

A coprocessor must define what the pipeline gives a building block for free:
who can cancel an accepted instruction, when the result is safe, who saves private
state on a context switch (the `XS` field of `mstatus`), and how errors reach
software. XIF-lite answers these by being blocking, non-speculative and
memory-free, and by having the core own the illegal-instruction trap.

## Verification references

- The Spike model (`spike/hyrv_ext.cc`) registers exactly the instructions of
  each lab CPU: `--extension=hyrv_xdot4` for Lab 09, `hyrv_xacc` for Lab 10. The
  lab runner builds it against the installed Spike headers and loads it when
  `EXT=xdot4` or `EXT=xacc` is given.
- `tests/ext_xdot4.c` and `tests/ext_xacc.c` check hand-computed vectors, random
  operands against the C reference, register forms, dependences, wrap-around and
  illegal neighbours (with a small trap handler, so Spike and RTL can still be
  compared by signature). Run them with `make lab09-check` / `make lab10-check`.
- `make ext-compare` runs `docs/course/starter/dot.c` as software, XDOT4 and XACC
  (several latencies) and writes `build/extensions/compare.html`.
