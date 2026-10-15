# Follow an instruction through the current P1/Q0 CPU

The cycle explorer is a local HTML report generated from **actual RTL traces**.
Its data, SVG diagram, styles, and JavaScript are embedded. The report works
without an internet connection. Open HTML in a browser rather than an editor.
`make serve` offers a local HTTP URL for the generated gallery.

```sh
export LAB_CORE_PRESET=ant_j0
export LAB_MEMORY_ADAPTER=ii1
make hw-sim APP=04_muldiv TRACE=1
```

Open the output path printed by the runner. In the default build root this is
`build/04_muldiv-O2/trace.html`. `LAB_BUILD_DIR` selects an isolated output root.
Capture normally starts at `main`; `--trace-startup` includes startup code.

## Read top down

1. **Jump to main**: green identifies the executing instruction; blue identifies
   the delivered instruction token, if valid.
2. **Next**: advance a recorded pre-edge sample and follow operands, the one IR,
   memory requests/responses, and enabled RF writes.
3. At MUL, DIV, or blocking memory access the backend retains its IR. The
   external SRAM adapter can hold the following instruction response.
4. **Next retirement**: inspect architectural completion. A store or branch can
   retire without writing an integer register.
5. A hexadecimal PC and **Find next** select later loop occurrences. **Play**
   stops at the end. Arrow keys step, Space plays, R selects retirement, and M
   returns to main. Shortcuts do not intercept typed addresses.

## Separate the events at an edge

Samples observe signals **immediately before a rising edge**. Accepted transfers,
IR admission, retirement, and RF writes take effect at that upcoming edge; their
new state appears in the next sample. Transfers require valid AND ready.

| Observation | Meaning |
| --- | --- |
| I-memory request Q | Memory accepts a fetch request |
| I-memory response R | Frontend consumes the accepted owner's response |
| Instruction F | A token is available but not admitted; this is not a new stage |
| Instruction A / fetch.accepted | Frontend valid AND backend ready admits through Q0 |
| commit.valid | Current IR instruction retires |
| regs.wb_enable | Physical RF writes a nonzero destination |

There is no instruction response buffer. The SRAM adapter holds a valid response
while the backend waits. `insn_assemble` forms the live token, and depth-zero
`rv_insn_link` forwards it combinationally. A local fault token has separate fault
metadata. Request PC, response-owner PC, delivered PC, and executing PC can differ.

In ideal latency-one/II-one steady state, one edge can retire I, admit I+1, and
accept fetch I+2. Fetch follows token capacity and handshakes, not a commit pulse.
Stalls, redirects, faults and multicycle execution can prevent this overlap.
See [the PC-path explanation](pc_flow.md).

## Module hierarchy and the functional drawing

```text
tb_cpu_lab
├── u_cpu : teaching_cpu [compatibility wrapper]
│   └── u_core : rv_core_simple
│       ├── u_frontend : rv_frontend (F0)
│       │   ├── u_gen_pc_nxt : gen_pc_nxt
│       │   ├── u_fetch_ctrl : fetch_ctrl
│       │   ├── u_fetch_tracker : fetch_tracker
│       │   ├── u_branch_predecode : rv_branch_predecode
│       │   └── u_insn_assemble : insn_assemble
│       ├── u_insn_link : rv_insn_link (Q0, no storage)
│       ├── u_bp : rv_branch_predictor
│       └── u_backend : rv_backend (one execution IR)
│           ├── u_decoder : rv32_decoder
│           ├── u_rf : rv32_rf [one physical 2R1W register file]
│           ├── u_alu_op : rv32_alu_op_decode
│           ├── u_alu : fu_alu
│           ├── u_br : fu_br
│           ├── u_mul : fu_mul
│           ├── u_div : fu_div
│           ├── u_ls_split : rv32_ls_split
│           ├── u_ls_align2 : rv32_ls_align2
│           └── u_csr : rv32_csr
│               └── u_pmu : rv32_pmu
└── u_mem : teaching_sram [one shared array, I/D ports]
```

The frontend, Q0 link, backend and predictor are sibling modules. Module
boundaries do not imply pipeline registers. Static ANT is default, BTFNT is
selectable; active ant_j0/btfnt_j0 presets disable early JAL. The backend checks
the saved predicted successor on completion and recovers on mismatch.

The [SVG diagram](microarchitecture.svg) groups functions. Decode, execution,
LSU and writeback are not four separately occupied pipeline stages. RF read and
write show two views of one 32×32 2R1W RF; I/D SRAM boxes show two ports of one
external array. Dashed identity links are not datapaths. Hover or focus a node
for its actual implementation mapping.

Clock wedges mark positive-edge state or enabled writes, rather than an update
on every clock. Request control includes owner/held/restart state; gen_pc_nxt is
combinational. Assembly/Q0 delivery has no instruction-storage wedge. SRAM
wedges mark its clocked adapter, not an array made of flip-flops. MUL/DIV and LSU
retain their multicycle result/control state.

Solid memory arrows show accepted transfers; amber dashed arrows show offered
transfers waiting for ready; red response arrows show errors. Vertical LSU
arrows carry requests/store data downward and load/completion responses upward.
Highlights report logical activity, not power, physical delay, or a full RF dump.
Unused source-register fields are hidden.

The timeline reconstructs dynamic IR occurrences, with separate loop iterations
at the same PC. F/A associate with the matching occurrence. Discarded tokens can
appear in fetch details without retiring; an active instruction at trace start
can lack fetch history. Mq/Mr are FSM phases. Only the four bus rows identify
actual accepted Q/R or blocked q/r transfers.

### Trace limits

Recording normally stops after 20,000 samples, while execution continues to its
normal completion or timeout. The report distinguishes **recorded cycles** from
**full-run cycles** and displays a notice for a truncated trace. Increase
`--trace-limit` for a longer window; the viewer accepts at most 100,000 samples to
bound browser memory. The machine-readable trace can be longer than this display
limit. A short, focused application is usually easier to study than a long run.

## Generator interface

The renderer uses only the Python standard library:

```python
from viewer.render import generate

artifacts = generate(
    trace_path="build/04_muldiv-O2/trace.jsonl",
    disassembly_path="build/04_muldiv-O2/program.dis",
    output_path="build/04_muldiv-O2/trace.html",
    metadata={
        "application": "04_muldiv",
        "profile": "RV32IM",
        "status": "pass",
        "start_symbol": "main",
        "trace_limit": 20_000,
        "trace_truncated": False,
    },
)
```

The lab runner supplies actual `core_configuration` build metadata. The HTML and
downloaded SVG show that run's preset, static policy, and early-JAL setting.
If direct generator use omits that identity, or declares an external CPU, the
P1-specific diagram and hierarchy are hidden and the downloadable SVG is labeled
reference-only. Pass identity from the actual hardware receipt; do not infer it
from instruction traces or select a convenient preset label.

`generate` also writes `microarchitecture.svg` beside the HTML and returns their
paths, first/last cycle, recorded retirement count, and separate capture/display
truncation flags. Optional `start_pc` overrides `start_symbol`. The disassembly
should come from `objdump -d -S`; C source lines require usable ELF debug
information. Source text is embedded as inert data, not interpreted as HTML.

To generate a report without the runner:

```sh
python3 viewer/render.py --trace trace.jsonl --disassembly program.dis \
    --output trace.html --title "My CPU experiment"
```

### JSONL contract

Each line is one pre-edge sample. Addresses and data are unsigned integers;
booleans can be `true`/`false` or `1`/`0`. Cycle numbers must increase strictly.

| Object | Fields used by the viewer |
|---|---|
| Top level | `cycle`, optional `schema_version` |
| `fetch` | `pc`, `insn`, `valid`, `accepted`, `request_pc` |
| `execute` | `pc`, `insn`, `valid`, `state` |
| `stages` | `fetch`, `decode`, `execute`, `memory`, `writeback` |
| `units` | `alu`, `branch`, `mul`, `div`, `lsu` |
| `regs` | `rs1`, `rs2`, `rs1_value`, `rs2_value`, `rd`, `wb_value`, `wb_enable`; optional `rs1_used`, `rs2_used` |
| `memory` | `valid`, `write`, `addr`, `data`, `wstrb`, `read_data`, `response_valid` |
| `commit` | `valid`, `pc`, `insn`, `rd`, `rd_data`, `rd_we` |
| `redirect` | `valid`, `pc` |
| Optional `trap` | `valid`, `cause`, `pc`, `value` |
| Schema 2 `ports.instruction` and `ports.data` | See the transaction fields below |
| Optional `drain` | `requested`, `done` |

Schema 2 port objects contain `req_valid`, `req_ready`, `req_accepted`, `req_id`,
`req_addr`, `req_write`, `req_size`, `req_wdata`, `req_wstrb`, `req_memtype`,
`req_priv`, `resp_valid`, `resp_ready`, `resp_accepted`, `resp_id`, `resp_rdata`,
`resp_error`, `owner_pc`, and `owner_addr`. Request size is log2(bytes).
Response owner PC/address describe the corresponding accepted request and are
used only when response-valid is asserted. The viewer shows an error response's
data as unusable. It does not turn request-valid into a store side effect.

Schema 1 remains readable, with a visible legacy notice: memory-ready,
acceptance, and errors were not recorded. The viewer does not invent these
signals or display handshake arrows for a legacy record.

`fetch.accepted` excludes a discarded word on redirection. `memory.valid` means a
request, not an entire pending transaction. `commit.valid` means instruction
retirement; `regs.wb_enable` means the actual register-file write. The state names
are `IDLE`, `MEM_REQ`, `MEM_RESP`, `MEM_WB`, `MUL_WAIT`, `DIV_WAIT`, `MEM_REQ2`, and
`MEM_RESP2`. Missing source-use flags are inferred only for ordinary RV32IM
opcodes; an extended decoder should supply its own flags.

This view follows the teaching core's single-slot contract. A future CPU with
multiple executing instructions needs a richer trace containing per-stage or
per-instruction identifiers and a matching viewer; this renderer must not be
used to imply that those cores have the same internal timing.

## Optional maintainer browser check

The generated report itself has no browser dependencies beyond a modern browser.
For automated checks, install Playwright separately and run:

```sh
NODE_PATH=/path/to/playwright/node_modules node viewer/check_browser.cjs \
    build/04_muldiv-O2/trace.html /tmp/cpu-lab-viewer-check
```

The check consumes the real report. It verifies navigation, state highlighting,
finite playback, main/PC jumps, zero external network requests, node-label fit,
left/right RF placement, vertical memory arrows, store retirement without RF
write, and offered/accepted/error states present in the supplied trace,
and a mobile viewport. It writes desktop/mobile screenshots, a division-wait
view when present, and a JSON result. No synthetic timing data is generated.

## Gallery and image-processing results

The runner can generate an entry page for the available examples:

```python
from viewer.render import generate_gallery

generate_gallery(
    [{"title": "Multiply and divide",
      "description": "Follow a multi-cycle instruction and the held fetch word.",
      "href": "04_muldiv/trace.html"}],
    "build/showcase/index.html",
)
```

Optional entry fields are `id`, `kind` (`camera` or `cycles`), `cycles`,
`trace_cycles`, `retired`, `checks`, `status`, and `eyebrow`. Only supplied
measurements and status labels appear. Optional gallery metadata sets `title`,
`description`, `profile`, `open_command`, and a `preview_href` for a static image.
An empty entry list creates a startup page with commands to generate the first
examples. It does not fabricate successful runs or stop a fresh installation.

For a camera/image-kernel experiment:

```python
from viewer.render import generate_camera_report

generate_camera_report(metadata, frames, "build/showcase/camera/images.html")
```

`frames` contains actual input and output images, for example `input`, `copy`,
`grayscale`, and `sobel`. Each frame supplies `id`, `title`, and a PNG `data_url`
(`data:image/png;base64,...`). Optional `width` and `height` are checked against
the PNG header. All images must have equal dimensions. A frame can supply
`description`, `trace_href`, `full_cycles`, `roi_cycles` (or `cycles`), and
`pixels_processed`. Give **each processing mode its own `trace_href`**, for
example `copy-trace.html`, `grayscale-trace.html`, `sobel-trace.html`, and
`pipeline-trace.html`. Selecting a mode updates both the full-page cycle link
and the optional inline explorer. The iframe is loaded only when requested;
it runs the same cycle explorer with that mode's actual trace. The input image
needs no trace. A legacy global `metadata.trace_href` is labeled as a shared
reference trace rather than as a separate run for every mode.
When frames come from separate benchmark runs, provide each frame's `full_cycles`
so selecting it also selects the corresponding run's total and ROI measurement.

The report embeds those images. Selecting a processing step changes the displayed
output and its measured cost. Clicking either image or using the coordinate
controls inspects the corresponding input/output pixel. Keyboard arrows move the
pixel; arrow keys also select neighboring processing tabs when a tab has focus.
The inspector reads the decoded PNG bytes. It never recomputes grayscale or
edges in JavaScript, so the displayed result remains the runner's output.

Camera metadata supports `application`, `title`, `status`, `backend`, `cycles`,
`roi_cycles`, `roi_description`, `description`, `source_note`, `trace_href`, and
`gallery_href`. Absent timing appears as **Not recorded**, not zero. Derived
cycles/pixel uses the supplied cycle count and `pixels_processed`, or explicitly
all pixels in the output frame, including the border. Full-run cycles and kernel
region cycles remain distinct. These measurements do not imply a physical camera
frame rate.

To check the gallery, mode selection, pixel controls, each supplied mode's
embedded cycle explorer, and mobile layout:

```sh
NODE_PATH=/path/to/playwright/node_modules node viewer/check_reports.cjs \
    build/index.html build/camera/report.html /tmp/cpu-image-report-check build
```

The optional final `build` argument also compares every decoded report pixel with
the actual input and simulator RGB dumps from the four O2 camera runs. Both
browser check scripts accept local HTTP URLs as well as filenames, so delivery
through `lab.py serve` can be checked separately from opening a local file.
