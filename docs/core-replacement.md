# Replace the CPU while preserving the lab

The bundled `rtl/` directory is a fixed teaching CPU used to establish this lab.
It has no source links to another repository. Keep this copy as the reference
while developing a replacement in a separate directory. The copy's origin and
file hashes are recorded in [snapshot.json](../provenance/snapshot.json).

An alternative CPU has **not** been validated merely because the reference
passes. Every replacement needs its own results, source identity, and viewer
checks. A future frontend diagram is a design proposal until the corresponding
implementation and measured traces exist.

## Compatibility boundary

The runner accepts `RTL_DIR=/absolute/path/to/candidate/rtl` (or the Python
option `--rtl-dir`). That directory supplies its own `filelist.f`, with paths
relative to the directory. The runner adds the lab's shared testbench and SRAM
model. Preserve the following boundary, using a wrapper if needed:

| Boundary | Required behavior |
|---|---|
| Top module | `teaching_cpu`, its existing ports, and `RESET_PC` parameter; default reset PC `0x80000000` |
| Software | RV32IM / ILP32, the existing startup/linker/runtime and SRAM signature layout |
| Memory | Independent I/D `mem_if.master` ports into one shared 1 MiB SRAM; blocking memory-v1 profile, one outstanding transaction and ID 0 per port |
| Handshake | Request and response transfer only on `valid && ready`; keep valid and all payload stable under backpressure; one response for every accepted request, including stores |
| Completion | Stores retire only after successful completion; preserve fault PC/cause/value and suppress normal retirement on traps |
| Control | Existing reset, IRQ, drain request/acknowledgment and commit/event ports |
| Observations | `teaching_trace_pkg::cpu_trace_t`, mapped to schema-2 JSONL by the testbench |

The SRAM response occurs after request acceptance, never in the same cycle.
The current blocking model does not reuse its transaction slot on the response
edge. Drain finishes existing work and continues accepting its responses before
acknowledging quiescence. The harness uses public CPU ports, without reaching
into the candidate's internal hierarchy.

The precise contracts are in [RTL documentation](../rtl/README.md),
[testbench documentation](../tb/README.md), and
[viewer documentation](../viewer/README.md). Any replacement must document and
validate its frontend and memory interfaces against the lab's actual harness.

## Trace and measurement meaning

Each sample contains signals immediately **before** the rising-edge state
updates. A reported acceptance, retirement, or RF write takes effect at that
edge. Its resulting state is visible in the next sample. Preserve this convention
when connecting new observation signals.

- `fetch.accepted` / timeline **A** is frontend-to-execution-slot admission.
  It is distinct from instruction-memory response acceptance and retirement.
- **F** means a valid delivered word is available but not admitted. It does not
  prove that a physical buffer already held the word before the edge.
- Bus **Q/R** show accepted requests/responses; **q/r** show offered transfers
  waiting for ready. Response owner addresses identify accepted transactions.
- `commit.valid` counts retirement; `regs.wb_enable` counts a physical RF write.
  A store or branch can retire without writing the register file.
- ROI cycles are the end-marker-store retirement cycle minus the begin-marker
  retirement cycle. The begin edge is excluded and the end edge included.
  Marker wrapper/setup overhead is included. Require `roi_complete`.
- Full-run cycles, captured samples, and ROI cycles have separate meanings.
  Reaching the capture limit stops recording; the program still runs to completion.

The current viewer represents fetch overlapping one serialized execution slot.
It reconstructs dynamic occurrences under that contract. A CPU with multiple
execution slots needs explicit instruction identities and corresponding viewer
changes; mapping arbitrary pipeline stages onto the old fields is insufficient.
The RF read/write regions describe one physical register file, and the I/D
memory regions describe two ports of one physical SRAM.

## Validate a replacement

Freeze or copy the candidate sources before running the gates. Do not run a
release regression against RTL that another session is editing. From `~/rv-lab`,
choose an unused output directory and keep it for the whole candidate run:

```sh
export LAB_BUILD_DIR="$PWD/build/candidate-v1"
export LAB_RTL_DIR=/absolute/path/to/frozen-candidate/rtl
make doctor
make compare APP=01_arithmetic
make test-smoke
make test
make camera-test
make visual-test
make gallery
make camera WIDTH=7 HEIGHT=5
make visual WIDTH=64 HEIGHT=48 FRAME=24
python3 tests/test_viewer_catalog.py -v
make export-views
make serve PORT=8771
```

`make test` includes the focused memory protocol gate. Run the browser checks
described in [reproducibility.md](reproducibility.md) against these candidate
reports. Compare complete signatures and image bytes with Spike and the host
oracles; cycle counts may change with the microarchitecture. Preserve the
candidate's manifests and results before selecting another output directory.

`LAB_RTL_DIR` selects the candidate consistently for the runner and dedicated
camera/visual firmware tests. A Make invocation can also pass `RTL_DIR=...`.
The explicit `camera` and `visual` commands generate candidate reports with
actual firmware, pixel comparisons, and cycle traces.

For a shared interface or TB change, record the changed files and hashes,
affected ports/fields, pre/post-edge convention, applying CPU revision, commands
and results, and required work in the other session. Keep CPU internals in the
CPU development session. There are no new public-interface or testbench changes
required solely to select a compatible replacement.
