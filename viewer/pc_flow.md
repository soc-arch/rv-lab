# Follow the PC through instruction fetch

The PC path in [the datapath drawing](microarchitecture.svg) expands the actual
logic in `rtl/teaching_fetch.sv`. It is a static explanation of the RTL. It does
not claim that internal register values absent from the trace were measured.

## A register output and a next-state value are different

Despite its name, **`next_pc` is a register output (Q)**. It is assigned inside
`always_ff @(posedge clk or negedge rst_n)`. There is no separately declared
combinational `pc_nxt` signal in this implementation.

The memory address is selected from registered state:

```systemverilog
imem_if.req_addr = held ? held_pc : next_pc;
```

Normally the request uses `next_pc`. When a request is offered but the memory
is not ready, `held_pc` preserves its address until acceptance. This also keeps
the offered address stable if a branch redirect changes `next_pc` meanwhile.

The following equations describe register updates; they are not additional RTL
modules. Reset has priority over the normal clocked behavior.

| Register | Update at the edge |
|---|---|
| `next_pc` | Reset: `RESET_PC`; otherwise redirect: `redirect_pc`; otherwise an accepted, non-obsolete request: `req_addr + 4`; otherwise hold |
| `pending_pc` | Capture `req_addr` when `req_valid && req_ready` |
| `held_pc` | Capture `req_addr` when a request is first offered with `req_ready == 0` |
| `buf_pc` | Capture `pending_pc` with a fresh response that cannot be admitted |
| `pc_pipe_r` | Capture `insn_if.pc` when the backend admits the instruction |

Thus the SRAM address and `pending_pc` input carry the same accepted address.
**The SRAM address is not generally the D input of `next_pc`.** For a normal
sequential fetch, the SRAM receives address P while the next-PC register receives
P + 4 at that acceptance edge. A redirect overrides the sequential update.
An obsolete held request still completes, but does not advance the redirected PC.

The viewer's **request mux output** is the recorded `req_addr`. The accepted
response owner, delivered frontend word and executing instruction can have
different PCs. In particular, `req_addr` is not a reliable proxy for `next_pc`
while `held` selects a previous request.

## Memory response, frontend delivery, and admission

`pending_pc` associates a response with the request that caused it. If the response
is fresh and the backend is ready, its instruction and PC bypass the response
buffer and enter the backend at that edge. Otherwise the frontend stores the
instruction, PC and fault metadata in its one-entry response buffer.

The buffer and accepted in-flight transaction share one capacity reservation:
the RTL asserts that `pending && buf_valid` never occurs. A buffered word can
be admitted at the same edge that the next request is accepted. The frontend
does not accept a replacement request at the edge completing its pending response.
Even a minimum-latency memory therefore does not turn this implementation into
a one-request-per-cycle fetch stream.

Redirects invalidate buffered obsolete instructions. Offered requests remain
stable until acceptance; accepted requests finish, and obsolete responses and
their faults are discarded. Drain stops new instruction admission and requests,
finishes previously offered or accepted requests, and can preserve a buffered
word for resumption.

## What F and A mean in the timeline

Every record is sampled immediately **before** a rising edge. These labels
describe the actions at that upcoming edge.

| Label | Meaning |
|---|---|
| I-memory `Q` | A request is accepted: `req_valid && req_ready` |
| I-memory `R` | A response is accepted: `resp_valid && resp_ready` |
| Instruction `F` | A valid frontend word is available but not admitted |
| Instruction `A` | The word is admitted into the backend: `insn_if.valid && insn_if.ready` |
| Instruction `D/X` | The word already occupies the backend and uses decode/execution logic |

`F` does not mean an instruction is still being read from SRAM. It also does
not prove that the word was already in `buf_insn`: the first unadmitted fresh
response is captured only at the upcoming edge. A successful fresh response
can produce **`R` and `A` in the same sample, with no preceding `F`**.

For example, these sample columns correspond to distinct rising edges:

```text
Memory ready; backend ready:
                         edge N   edge N+1   edge N+2
I-memory request            Q         .          .
I-memory response           .         R          .
This instruction            .         A         D/X

Backend busy when the response arrives:
                         edge N   edge N+1   edge N+2   edge N+3   edge N+4
I-memory request            Q         .          .          .          .
I-memory response           .         R          .          .          .
This instruction            .         F          F          A         D/X
```

These are illustrative single-instruction rows; another request can appear
elsewhere in the real trace. The viewer associates F/A cells with the next
matching execution-slot occurrence. An instruction discarded before execution
is shown in fetch details rather than as a retired instruction row. A trace
that starts during execution may omit that instruction's earlier fetch history.

## Can an instruction FIFO replace the response buffer?

Yes. A deeper FIFO can replace the one-entry delivery buffer behind the existing
instruction-valid/ready boundary. Each entry must retain the instruction's PC,
bits and fault metadata. Capacity reservation must account for responses still
in flight, and redirect/flush logic must discard the correct entries.

The FIFO does **not** replace the PC generator, held-request handling, request
ownership or obsolete-response handling. Increasing FIFO depth alone also does
not increase the number of outstanding memory requests. That change requires
additional request tracking and, where applicable, transaction IDs or epochs.
