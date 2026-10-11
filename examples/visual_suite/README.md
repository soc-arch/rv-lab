# Visual programs on the teaching CPU

These applications render their output by executing ordinary RV32IM C programs.
The same ELF runs in Spike and RTL. The host extracts the complete RGB image from
the target's SRAM signature and checks every byte against a Python reference.
The displayed target image is always the observed output, including when a
comparison fails.

Run the following commands from the `cpu_lab` directory. Use the Python
interpreter configured for your lab installation.

```sh
python3 lab.py run --app 07_denoise --backend both --trace
python3 lab.py run --app 08_cartoon --backend both --trace
python3 lab.py run --app 09_ball --backend both --frame 23 --trace
python3 lab.py serve
```

Open `http://127.0.0.1:8770/` in a browser to select a report. If the simulator
runs on a remote machine, follow the SSH forwarding instructions in the main
lab README. A generated `build/<application>-O2/trace.html` is also a standalone
cycle explorer that you can download and open locally.

## Applications and useful instruction patterns

| Application | Computation inside the measured region | What to inspect in the cycle explorer |
|---|---|---|
| `07_denoise` | RGB to grayscale, followed by a median over a clamped 3 × 3 neighborhood | Byte loads, coordinate clamping, comparisons, insertion-sort branches, grayscale multiply/add, and output stores |
| `08_cartoon` | Per-channel median, 32-level quantization steps, grayscale/Sobel edges, then darkened edge pixels | Repeated neighborhood accesses, shifts, conditional branches, and the interaction of arithmetic with load/store waits |
| `09_ball` | An integer checkerboard background, shadow, and shaded sphere for one frame index | Integer divide/remainder for scene geometry, multiply/shift shading, and the restoring integer square-root loop |

Grayscale and Sobel alone are already available through the `06_camera`
application and the camera report. The visual applications extend that set with
median filtering, a cartoon pipeline, and procedural rendering. The cartoon
effect is an educational median/posterize/ink pipeline; it does not implement a
bilateral filter.

The denoising input has deterministic impulse noise added **on the host before
execution**. `clean.png` records the source and `input.png` records the actual
noisy target input. Its output is grayscale RGB, not a reconstructed color image.
For the cartoon application, `input.png` is the original target input. The ball
renderer consumes only a frame index and dimensions; it does not consume a source
photograph or a pre-rendered frame.

## Try your own input and compare memory timing

```sh
# P6 PPM needs only Python's standard library. PNG/JPEG input also needs Pillow.
python3 lab.py run --app 07_denoise --input photo.ppm \
  --width 80 --height 60 --noise-seed 7 --backend both --trace

python3 lab.py run --app 08_cartoon --input photo.ppm \
  --width 80 --height 60 --memory-profile stress --backend both --trace

# Choose a frame and focus the trace on the square-root routine.
python3 lab.py run --app 09_ball --frame 48 --width 80 --height 60 \
  --trace-symbol ball_isqrt --backend both --trace

# Run all three applications with their normal per-kernel trace entry points.
python3 lab.py visual --width 64 --height 48
```

The default size is 64 × 48. Supply both width and height to change it; an image
is resized to those dimensions when needed. Interactive image dimensions are
3..160 by 3..120; ball dimensions are 64..160 by 48..120. These limits keep the
buffers comfortably inside the lab's 1 MiB SRAM and keep RTL runs manageable.
The copied kernel library supports larger dimensions, but that wider contract
does not increase this lab runner's limit. The frame index and noise seed are
unsigned 32-bit values.

Changing the memory profile changes RTL timing and may alter the exact captured
cycle window. It must not change the expected pixels. Spike supplies a functional
comparison; its execution time is not this CPU's cycle count. Repeated runs of the
same application, optimization level, and memory configuration replace that build output,
so save reports before making a comparison you want to retain.

## What is measured and verified?

`main.c` initializes the output, scratch storage, and guard bytes before calling
`lab_roi_begin()`. The measured operation is one complete `image_run()` or
`render_frame()` invocation, followed by `lab_roi_end()`. Input checksums,
output checksums, guard checks, and result reporting happen outside the region.

The testbench measures the difference between the retirement cycles of the end
and begin marker stores. This excludes the begin-store retirement edge and
includes the end-store edge. Marker-call return/setup overhead is included;
this is a clearly defined application region, not a measurement of only the
kernel's internal instructions. No target timer peripheral or CSR is required.

Each target run performs eight checks: successful kernel return, four boundary
guards, input immutability, the expected input checksum, and the expected output
checksum. The host additionally compares every output byte against its reference
and compares Spike and RTL signatures. This avoids treating a matching checksum
alone as proof of identical pixels.

The default trace begins at `image_run` or `render_frame` and captures at most
20,000 CPU cycles. `--trace-symbol` can select a different ELF symbol. A trace
limit only bounds the recording: simulation continues to the end, and the ROI
and output image still describe the complete run. A single ball run produces one
frame. Cycling through frame indices demonstrates animation; it does not measure
a video display's frame rate.

Useful generated files are:

| File under `build/<application>-O2/` | Meaning |
|---|---|
| `program.elf`, `program.dis` | The compiled target program and disassembled instructions |
| `build.json` | Compiler options, ELF symbols, input identity, dimensions, and frame or noise configuration |
| `input.png`, `input.rgb` | Target input bytes; the ball input is an unused zero-filled placeholder |
| `sw.output.png`, `hw.output.png` | Actual target output reconstructed from each backend's signature |
| `sw.json`, `hw.json` | Checks, byte comparison, and RTL ROI metrics |
| `trace.jsonl`, `trace.html` | Captured RTL cycles and the offline interactive viewer |

## Source reuse and independent checks

`image_kernels.c/.h` are exact snapshots of HY-RV's `sw/visual_suite` integer
kernels. `render.c/.h` are exact snapshots of `sw/bouncing_ball`. The origins,
repository revision, and actual content hashes are recorded in
`SOURCE_SNAPSHOT.json`. The teaching adapter replaces the original startup,
physical addresses, CSR timing, and host protocol with the lab runtime. Only the
four dimension limits needed by the renderer are retained in the local
`ball_abi.h`; no original application memory map is imported.

`visual_support.py` uses sorted Python neighborhoods and convolution for image
oracles. The ball oracle evaluates the same scene contract in Python and uses
`math.isqrt` to check the target's restoring square root. This is an independent
arithmetic implementation of the shared scene, not a different rendering design.
Neither oracle requires the parent HY-RV repository when the lab is exported.

Run the focused tests with:

```sh
python3 tests/test_visual_lab.py -v
```

They compare the C kernels with Python on small, odd-shaped images and difficult
frame indices, reject a forged pixel and changed input, and run real Spike/RTL
cases with memory waits, full output comparisons, ROI checks, and cycle traces.
The native reference checks need a host C compiler. Set
`CPU_LAB_VISUAL_TEST_REPORT` to retain their firmware evidence at a chosen JSON
path. These tests complement the general ISA, memory protocol, and application
regressions; they are not an exhaustive proof of the CPU or algorithms.
