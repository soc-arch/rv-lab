# Follow an instruction through the CPU

The cycle explorer is a local HTML report generated from the **actual RTL trace**.
It embeds its data, diagram, styles, and JavaScript. Open it in a browser; no web
server, package installation, or network connection is required.

**Open the report in a browser tab.** A code editor or file-source panel displays
the HTML source instead of executing the viewer. The lab's `python3 lab.py serve`
command serves the generated gallery over a local HTTP address, which can be
opened in a browser. This is a local viewing convenience, not a remote upload.

From the lab directory, run:

```sh
make hw-sim APP=04_muldiv TRACE=1
```

Or use the runner directly:

```sh
python3 lab.py run --backend hw --app 04_muldiv --trace
```

Open `build/04_muldiv-O2/trace.html`. The runner starts recording at `main` by
default. `--trace-startup` also records the provided startup code.

## Explore the result

1. Start with **Jump to main**. The listing highlights the executing instruction
   in green and the prefetched word in blue.
2. Use **Next** to advance one recorded cycle. Check the operands, execution
   state, memory request/response, and register write enable.
3. At a multiply or divide instruction, watch the execution slot remain occupied.
   The frontend can hold another word at the same time. The timeline shows this
   overlap using separate dynamic instruction occurrences.
4. Use **Next retirement** to skip waiting cycles and inspect the result written
   to the register file. Stores and branches can retire without a register write.
5. Enter a hexadecimal PC and use **Find next** to follow later loop iterations.
   Use **Play** for an animation; it stops at the end rather than wrapping around.

Keyboard shortcuts: left/right arrows step, Space plays or pauses, `R` selects
the next retirement, and `M` returns to `main`. Shortcuts do not intercept typing
inside the address field. The diagram and timeline scroll horizontally on small
screens. The footer links to a standalone, scalable `microarchitecture.svg`.

### Read the cycle boundary correctly

Each record observes signals **immediately before a rising clock edge**. A
retirement, accepted memory transfer, or enabled register write takes effect at
the upcoming edge. Memory acceptance means `valid && ready`. A request that is
valid while ready is low is only offered, and remains stable until accepted.
The instruction-memory response owner, current offered request, and frontend
word can have different PCs. `fetch.accepted` is frontend-to-backend admission;
it is not instruction-memory response acceptance.

The diagram names the functions **fetch, decode, execution, memory access, and
writeback**. They are not five independently occupied pipeline stages. This CPU
overlaps fetch with one serialized backend slot. Decode and register reads are
combinational; a long-running instruction keeps that slot until it finishes.
The left RF-read box and far-right RF-write box are **two views of one physical
2R1W register file**, not two banks. Likewise, the I-memory and D-memory boxes
are two logical ports of one physical RAM. Vertical arrows between the LSU and
D port show request/store data downward and load/completion responses upward.
Solid highlighted memory arrows mean accepted transfers; amber dashed arrows
mean offered transfers waiting for ready. Red response arrows flag errors.

### Clock triangles and RTL hierarchy

An outline triangle on a storage boundary marks state updated on a **rising
clock edge**, subject to its enable. It does not mean that the block writes every
cycle, nor that every circuit inside it is a flip-flop. The SRAM markers describe
the clocked interface/model; they do not prescribe a flip-flop implementation of
the memory array. Reset behavior is not drawn.

The architecture picture is a **functional datapath view**, not a one-box-per-module
elaboration diagram. In particular, the instruction slot and writeback mux are
logic inside the backend; the LSU groups a state machine, response registers and
combinational byte-lane helpers. The actual main instance hierarchy is:

```text
tb_cpu_lab
├── u_cpu : teaching_cpu
│   ├── u_fetch : teaching_fetch
│   │   └── PC/request state, 1-entry response buffer, fresh-response bypass
│   └── u_backend : teaching_backend
│       ├── instruction-slot registers and execution-state logic [inline]
│       ├── u_decoder : rv32_decoder
│       ├── u_rf : rv32_rf                       [one physical 2R1W RF]
│       ├── u_alu_op : rv32_alu_op_decode
│       ├── u_alu : fu_alu
│       ├── u_br : fu_br
│       ├── u_mul : fu_mul
│       ├── u_div : fu_div
│       ├── u_ls_split : rv32_ls_split
│       ├── u_ls_align2 : rv32_ls_align2
│       ├── u_csr : rv32_csr
│       └── load-response registers, writeback/retirement/trap logic [inline]
└── u_mem : teaching_sram                        [one shared array, I/D ports]
```

This tree lists the main module instances and explicitly marks inline logic.
The CSR block contains the PMU; CSR/trap/PMU details and some control muxes are
omitted from the introductory datapath drawing. `insn_supply_if` connects fetch
to the backend and is distinct from the CPU's I/D memory transaction interfaces.

| Diagram region | RTL location | State or logic |
|---|---|---|
| Fetch control | `teaching_fetch`: `next_pc`, `pending_*`, `held_*`, stale flags | Clocked request/PC state plus combinational control |
| Frontend delivery | `teaching_fetch`: `buf_*` and assignments to `insn_if` | One clocked entry plus a combinational bypass/selection path |
| Instruction slot | `teaching_backend`: `pc_pipe_r`, `insn_pipe_r`, `valid_pipe_r`, fetch-fault flags | Clocked; held while the instruction waits |
| Decode | `u_decoder` and inline legality checks | Combinational |
| RF read / RF write | Both are ports of `u_rf` | Asynchronous reads; enabled rising-edge write |
| ALU | `u_alu_op`, operand muxes and `u_alu` | Combinational; also computes load/store addresses as `rs1 + immediate` |
| Branch / jump | `u_br` plus redirect selection | Combinational in this configuration |
| Multiply / divide | `u_mul`, `u_div` and backend wait control | Contain clocked state; these are not extra independently occupied stages |
| Load-store unit | Backend FSM, `load_data_r`, `u_ls_split`, `u_ls_align2`, D-port assignments | Mixed clocked and combinational logic; no standalone `u_lsu` instance |
| Writeback mux | Backend `wb_data` selection and enable logic | Combinational; no additional writeback register stage |
| SRAM I / D | Both are ports of testbench `u_mem` | Clocked request/response model and array access |

`u_ls_split` is a retained byte-lane helper; its name does not mean that this
profile supports split misaligned transactions. Such accesses trap before issue.

### What the frontend word represents

The old **Frontend word** label referred to the instruction-delivery point at
`insn_if`, not to a separate RTL module or an empty space for a future queue.
The diagram now identifies the buffer and bypass explicitly:

1. The frontend associates an accepted I-memory request with `pending_pc`.
2. If a non-obsolete response arrives while the backend can admit the instruction,
   its instruction bits pass directly through the combinational bypass to the
   instruction slot at that edge. They need not spend an extra cycle in `buf_insn`.
3. If the backend cannot admit it, the frontend captures the word, PC and fault
   metadata in `buf_insn`, `buf_pc`, `buf_valid` and the fault flags. This one entry
   holds the instruction until admission or redirect. Drain can also pause
   admission and retain a buffered instruction for resumption.
4. A redirect clears an obsolete buffered instruction. Already offered or accepted
   requests still complete, and obsolete responses are consumed and discarded.

The implementation has one pending memory transaction **or** one valid buffered
word; it asserts that `pending && buf_valid` never occurs. A buffered word may be
admitted at the same edge that the next memory request is accepted. Together with
one instruction in the backend, this provides fetch/execution overlap; it does
not constitute a deep instruction queue.

A larger instruction queue could replace this buffer behind the same
instruction-delivery handshake. It would need explicit capacity, response-space
reservation, redirect/flush and fault-PC handling. More concurrent memory requests
would additionally need request tracking and ID handling; increasing the queue
depth alone does not provide those features.

Highlights represent logical use reported by RTL. They do not measure transistor
switching, propagation delay, energy, or the contents of every register. Register
operands are hidden when that instruction does not use the corresponding field.
In particular, a writeback result with `rd = x0` does not imply a register write.

The instruction timeline groups samples by actual execution-slot occurrences,
including distinct iterations with the same PC. It associates a matching held
fetch word with the next observed admission. A word discarded by redirection is
visible in the selected-cycle details but is not displayed as a retired row.
An occurrence already in flight at the start of a trace can lack its earlier
fetch history. `Mq` / `Mr` are backend FSM phases, not proof of a handshake.
Four separate bus rows show accepted requests (`Q`), accepted responses (`R`),
offered but blocked requests/responses (`q` / `r`), and accepted errors (`ERR`).

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
