# Editable teaching CPU RTL

The teaching CPU implements the **blocking HY-RV memory v1 profile**: one live
instruction transaction and one live data transaction, each using ID 0. Request
acceptance and response completion are real handshakes. No fixed SRAM latency is
assumed in the CPU. Required application target: `-march=rv32im -mabi=ilp32`.

## Read the design in this order

| File | Responsibility |
|---|---|
| `teaching_cpu.sv` | Stable replacement boundary, drain control, observations and protocol assertions |
| `teaching_fetch.sv` | Instruction requests, one buffered response, PC association, redirect discard |
| `teaching_backend.sv` | Decode/RF, execution units, blocking LSU, writeback, traps and retirement |
| `common/rv32_decoder.sv` | Instruction fields and operation classes |
| `common/rv32_rf.sv` | 32 integer registers, two asynchronous read ports and one synchronous write port |
| `common/fu_*.sv` | ALU, branch, multiplier and divider |
| `common/mem_if.sv` | Memory request/response interface |
| `common/insn_supply_if.sv` | Frontend instruction delivery and fetch-fault metadata |
| `teaching_trace_pkg.sv` | Version 2 public observation structure |

Fetch overlaps a serialized backend holding one executing instruction. Decode,
execute, memory access and writeback are **functional responsibilities**, not four
additional independent pipeline stages. The next fetched instruction can wait in
the frontend while a multiply, divide or memory access finishes.

## Public replacement contract

Keep the `teaching_cpu` module, its memory interface instances, commit outputs and
`teaching_trace_pkg::cpu_trace_t` output when replacing the implementation. The
same testbench can then run an edited or alternative core without accessing its
internal hierarchy. The top has clock/reset, I/D `mem_if.master` ports,
`drain_req_i`/`drain_done_o`, IRQ inputs, retirement outputs and trace/event outputs.
The default reset PC is `0x80000000`. The testbench, not the CPU, owns SRAM storage.

Both ports use byte addresses and little-endian data. Requests carry ID, address,
read/write direction, log2 transfer size, data, write strobes, memory type and
privilege. A byte or halfword occupies its addressed lanes in the 32-bit bus word;
load sign/zero extension is performed by the LSU. Read strobes are zero. The
teaching profile maps normal uncached SRAM and runs in machine mode; MMIO routing
and permissions must be added explicitly before connecting peripherals.

A request transfers at a rising edge only when `req_valid && req_ready`; it and
all its payload remain stable while stalled. Every accepted read or write gets
exactly one response, consumed with `resp_valid && resp_ready`. A response cannot
arrive in the acceptance cycle. This core does not reuse an ID on the response
edge; the following cycle is the earliest next request. The memory may delay
acceptance or response by any finite number of cycles. A physical SRAM result
must be buffered by its adapter if the response cannot yet be consumed.

The SRAM model separately controls access latency, initiation interval and
arbitration. These timing properties are not interchangeable. Real macros still
require valid clocking and timing constraints; delaying a protocol response does
not fix a physical timing violation.

## Fetch, redirect and drain

The frontend records the accepted request PC independently from the next request
PC. Its instruction-delivery PC always accompanies the buffered or fresh response.
A branch, trap, return or instruction-fetch synchronization invalidates obsolete
instructions. Already offered requests keep their address/valid until accepted;
accepted obsolete fetches are drained, with their data and errors discarded.
This preserves exactly-once ownership through variable response latency.

Drain stops new instruction admissions and fetch generation, finishes the current
backend instruction, and drains already offered or accepted requests. Responses
continue to be consumed. `drain_done_o` asserts while requested only when both
clients are idle; a fetched instruction may remain buffered for resumption. This
profile has no hidden posted writes or dirty cache lines. Reset must reset the
whole transaction domain coherently, or a system isolation controller must drain
it first. Reset cannot undo external writes.

## Memory instructions, faults and retirement

| Operation | Backend behavior |
|---|---|
| Integer ALU / untaken branch | One execution cycle once admitted |
| Multiply | Dispatch, then multiply completion |
| Divide | Dispatch plus the established 33-cycle blocking divider wait |
| Aligned load/store | `MEM_REQ` until acceptance → `MEM_RESP` until completion → `MEM_WB` |
| Taken branch/jump | Redirect; frontend drains any obsolete transaction before replacement |
| Misaligned load/store | Trap before presenting a data request |
| Access error | Trap on response; no normal retirement or destination write |

A store has a completion response even though it does not write a register. In
this unbuffered profile it retires only after successful memory completion. The
`MEM_WB` state denotes architectural retirement for both loads and stores; only
loads assert register write enable. A device/cache adapter would define its own
completion and visibility policy under the project memory specification.

Unlike the earlier imported SRAM-only snapshot, this profile **does not split
misaligned accesses**. Halfword/word misalignment traps with causes 4/6. Data
response errors trap with causes 5/7; instruction access errors use cause 1.
Misaligned taken branch/JAL/JALR targets use cause 0 and suppress the link write.
Illegal operation encodings trap before a memory request or result commit.
Reserved trace state codes 64/128 remain for compatibility but are never entered.

The extra machine CSR/trap support is retained. An IRQ cannot cancel a stalled or
accepted memory request: it waits for the next safe instruction boundary. CSR
writes are suppressed if a trap preempts the instruction. FENCE is satisfied by
in-order unbuffered data completion here. The retained FENCE.I behavior flushes
prefetched instructions; future caches require a separate maintenance contract.

## Observations and extension points

Trace version 2 retains the original field names and state codes. New I/D request
and response valid/ready/accepted/error/ID fields distinguish offered work from
transferred work. `fetch_accepted` means frontend-to-backend instruction admission;
`fetch_response_accepted` means memory-to-frontend completion. These are different
events. `fetch_pc` is meaningful for a valid instruction slot, while
`fetch_request_pc` names the offered memory request. Stale response consumption
can occur without an instruction admission.

All trace values are sampled before the rising edge and describe actions at that
edge. Stage highlights show logical activity, not transistor switching or power.
Only `commit_valid` counts a retired instruction. The trace includes the faulting
PC, cause and trap value. The testbench accesses no private CPU signals.

To add an instruction, update the class decoder and the backend's
`encoding_legal` function, define operand/result behavior, add an execution unit
if needed, and update dispatch, wait and retirement conditions together. A unit
must not commit a result before it is valid. Preserve request stability and the
non-speculative-store rule when changing pipeline control.

`filelist.f` lists paths relative to this directory; the runner resolves them and
appends the shared testbench sources. `--rtl-dir` selects a student copy.
`SOURCE_SNAPSHOT.json` records import provenance and local adaptation status.
Production/research RTL outside this lab is not migrated by these files.
