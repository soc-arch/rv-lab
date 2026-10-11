# Reproduce the environment and cycle reports

Run commands from `~/rv-lab`. The bundled runtime provides startup,
linking, completion/signature handling, and a buffered console. An application
can supply only C or assembly `main`; the console is SRAM data printed by the
host after completion, rather than a live UART stream.

The same ELF runs on Spike and Verilator. Spike checks software behavior;
hardware timing comes from the RTL testbench's clock counter. Neither host run
time nor Spike timing is the CPU's RTL cycle count.

## Evidence and output directories

[provenance/snapshot.json](../provenance/snapshot.json) identifies the public
source copy. A source hash identifies files; it does not establish a passing
execution. Use each new run's manifests and results to record what was actually
tested, with the selected tools and configuration.

By default, generated files are in `build/`. `LAB_BUILD_DIR` selects another
output directory so baseline and candidate reports remain separate:

```sh
export LAB_BUILD_DIR="$PWD/build/reference-check"
unset RTL_DIR LAB_RTL_DIR
make doctor
make compare APP=01_arithmetic
make test-smoke
```

Leave `LAB_BUILD_DIR` unset to use the default `build/`. Use a fresh directory
when preserving a comparison: rerunning the same application, optimization level,
and memory profile replaces its files. Simulator caches are keyed by source
hashes, compiler identity, and flags; an application record names its ELF hash
and hardware build. Do not copy old PASS labels into a new result.

## Validation gates

After the three baseline checks above, select the checks needed for the claim:

`make validate` runs the lab's repeatable validation workflow and saves a new
receipt. Use it when checking the complete environment after a release or CPU
replacement; retain its reported commands and any explicitly unrun checks.

| Command | Evidence |
|---|---|
| `make test` | 47 application scenarios: 44 positive and 3 expected failures, plus focused memory protocol tests |
| `make camera-test` | Independent image arithmetic, real firmware, trace/ROI consistency, and stale-output rejection |
| `make visual-test` | Native integer kernels versus Python references; real denoise/cartoon/ball firmware, memory waits, and pixel checks |
| `make perf-test` | Student main, software CSR reads versus actual retirements, full instruction logs, and failed-result pages |
| `python3 tests/test_viewer_catalog.py -v` | Host verdicts, relative navigation, invalidated aliases, and stale catalog behavior |
| `make gallery` | Five basic traced examples and a delayed-memory example |
| `make course-test` | Portable manual rendering, local links, escaped content, and loopback-link mapping |
| `make registration-test` | Actual student-program publication, reruns, variants, failed runs, receipt invalidation, and export |
| `make register SOURCE=docs/course/starter/sum.c NAME=student-sum TITLE="Student sum"` | Same-ELF comparison and actual trace published in My applications |
| `make camera WIDTH=7 HEIGHT=5` | Four compact copy/grayscale/Sobel/pipeline runs and their measured cycle reports |
| `make visual WIDTH=64 HEIGHT=48 FRAME=24` | Denoise, cartoon, and one integer ball frame, with actual RTL traces |
| `make export-views` | Portable HTML gallery, cycle reports, and hash manifest in `cpu_lab_examples.zip` |

Run these serially in an output directory. `make test-smoke` is a 17-scenario
development gate; it does not replace the full release gate. Dedicated camera
and visual tests use temporary application outputs and the selected CPU. Retain
their detailed firmware evidence with `CPU_LAB_TEST_REPORT` and
`CPU_LAB_VISUAL_TEST_REPORT`, respectively, set to absolute JSON paths.

For compact denoise/cartoon experiments, run them individually:

```sh
make compare APP=07_denoise WIDTH=7 HEIGHT=5 TRACE=1
make compare APP=08_cartoon WIDTH=7 HEIGHT=5 TRACE=1
```

Image filters accept 3..160 by 3..120 pixels. The ball requires at least 64 by
48 pixels. Consequently, `make images WIDTH=7 HEIGHT=5` cannot complete the ball
run. Use `make images WIDTH=64 HEIGHT=48 FRAME=24` for all seven image modes,
or the separate small camera and 64-by-48 visual commands above.

## Images, traces, and source provenance

Each camera mode has its own ELF, result, and cycle trace. Grayscale preparation
is outside the Sobel-only ROI; pipeline ROI includes grayscale and Sobel.
Denoise adds deterministic host-side impulse noise before the target executes,
then produces grayscale output. Cartoon runs median filtering, quantization,
and edge composition. Ball renders a selected frame from integer geometry;
it consumes no source photograph and provides no physical video frame rate.

The host reconstructs the actual output from the complete SRAM signature and
compares every RGB byte with independent Python arithmetic and with Spike.
The browser displays embedded PNG bytes; it does not recompute the kernel.
`input.rgb`, `hw.output.rgb`, `sw.output.rgb`, and input/output hashes preserve
the connection to the simulated data. Original sources and adaptation details
are recorded in `examples/camera/PROVENANCE.json` and
`examples/visual_suite/SOURCE_SNAPSHOT.json`. These are local snapshots, so the
exported lab does not import source files from the parent repository.

Default traces contain at most 20,000 samples, while execution and ROI counting
continue. Large image kernels normally have truncated traces. The report labels
the captured window and separate full-run/ROI counts. See
[core-replacement.md](core-replacement.md) for the precise edge convention.

## Browser and offline checks

```sh
make serve PORT=8770
```

Open `http://127.0.0.1:8770/` in a browser. The gallery and cycle reports offer
**Group → Example → Open**: **Simple test suite**, **Image processing**, and
**My applications** after a successful custom registration.
Check both built-in groups and My applications when present, a multiply/divide trace, a memory-wait trace, and an image
trace with its actual output. Check step/retirement navigation and confirm the
trace window and ROI labels. An editor's HTML source tab does not render the UI.

For a remote host, forward the port from your own computer:

```sh
ssh -N -L 8770:127.0.0.1:8770 your-user@your-simulation-server
```

The server exposes only the selected output directory. For offline use, extract
all of `cpu_lab_examples.zip` and open `index.html`, preserving its subfolders.
The reports embed their own data and need no CDN or Internet connection.

Optional maintainer checks require Playwright and its Chromium installation;
they are not student viewer dependencies. With the correct `NODE_PATH` set:

```sh
VIEW_BUILD="${LAB_BUILD_DIR:-$PWD/build}"
node viewer/check_browser.cjs \
  "$VIEW_BUILD/04_muldiv-O2/trace.html" "$VIEW_BUILD/browser/cycles"
node viewer/check_browser.cjs \
  "$VIEW_BUILD/02_memory-O2-mem-stress/trace.html" "$VIEW_BUILD/browser/memory"
node viewer/check_reports.cjs "$VIEW_BUILD/index.html" \
  "$VIEW_BUILD/camera/report.html" "$VIEW_BUILD/browser/images" "$VIEW_BUILD"
node viewer/check_student.cjs http://127.0.0.1:8770/ "$VIEW_BUILD/browser/student"
node viewer/check_registration.cjs http://127.0.0.1:8770/ "$VIEW_BUILD/browser/registration"
node viewer/check_navigation.cjs "$VIEW_BUILD/index.html" \
  "$VIEW_BUILD/browser/navigation"
```

These checks produce screenshots and JSON receipts for the real reports,
including mobile layout, transfer highlights, camera mode/trace selection, and
decoded image pixels versus simulator RGB dumps. They also accept local HTTP
URLs. The registration check additionally opens the eight course units and a
student's actual cycle trace. Use the actual server URL for your selected build
root; use a `file:///absolute/extracted/path/` base to repeat it offline.
The navigation check exercises all available groups, opens every cataloged cycle
report, verifies each report's selected example and gallery link, checks remembered
selections, and checks the mobile layout. Generate both gallery and image examples
before running it.

Keep command logs, tool versions, `regression.json`, build/ELF identities,
camera/visual results, browser receipts, and the source hashes together. Record
unrun or failed gates explicitly. A new CPU is unverified until its own
[replacement workflow](core-replacement.md) completes.
