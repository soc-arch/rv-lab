# Follow the PC through current P1/F0 fetch

This is a static explanation of `rtl/frontend/rv_frontend.sv` and its helpers,
**not a measured waveform**. The viewer shows actual public trace signals only.
Absent internal metadata remains labeled unrecorded.

## Select and track one address

`gen_pc_nxt` is combinational. Unlike the former teaching CPU's registered
`next_pc`, current `pc_nxt` selects the request address with this priority:
held request → pending redirect → boot/reset address → predicted successor →
sequential owner PC + 4. `fetch_ctrl` stores offered-request/restart metadata.
A valid stalled request keeps its address until acceptance even if redirected.

At request valid AND ready, `fetch_tracker` captures owner PC and lookup
metadata. `owner_pc` belongs to that response, independently of a successor
request. Completion releases ownership, and allocation can replace it at the
same edge with the ii1 memory adapter. Each port still has only one live owner.

## Admit a live token through Q0

F0 has **no instruction response buffer**. The memory adapter holds response
bits, ID and error stable until ready. `insn_assemble` forms a token and Q0
`rv_insn_link` forwards it directly. The backend IR captures it at valid AND
ready. A local fetch-address fault has separate metadata, not a general queue.

A response is consumed for token admission or obsolete/killed-work discard.
Redirect suppresses younger tokens while preserving already-offered request
obligations. Accepted stale responses complete and their bits/faults are
discarded. Drain finishes backend and memory work, discards younger tokens, and
resumes from the architectural resume PC; no buffered instruction is preserved.

## Read illustrative edge diagrams

These rows are **design examples, not measured traces**. Each column names a
rising edge. Q = accepted request, R = accepted response, r = valid response
waiting for ready, and A = backend IR admission.

```text
Ideal steady state: response latency 1, memory II=1, backend ready
                                  edge N     edge N+1     edge N+2
Backend retirement                   I         I+1          I+2
Backend IR admission               I+1         I+2          I+3
I-memory response R                I+1         I+2          I+3
I-memory request Q                 I+2         I+3          I+4

Backend busy when the next response becomes available
                                  edge N     edge N+1     edge N+2     edge N+3
I-memory request Q                  J           .            .          J+1
I-memory response                   .           r            r           R
Instruction J token                 .           F            F           A
```

The memory producer holds the second example's response until the final edge;
F0 does not copy it into a buffer. R+A can coincide without an earlier F sample.
Retirement, admission and fetch acceptance are distinct events that can overlap.
Fetch also starts with an empty backend without requiring a commit.

## Prediction and future extensions

The sibling predictor uses static BP0 ANT by default; BP1 BTFNT is selectable.
Both active presets disable early JAL. Prediction metadata travels with the
token, and the backend checks the actual successor on completion and recovers
on mismatch. The predictor and Q0 link are not extra pipeline stages.

Positive-depth queues are future work. Entries must preserve PC, bits, faults
and prediction metadata with capacity/flush rules. More outstanding fetches need
additional owner/ID tracking. When adding frontend stages, remind the designer
to reconsider early JAL with the new handshakes, timing and actual verification;
that reminder does not itself authorize enabling early JAL.
