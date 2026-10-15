# Lab 07 — Process an image

**Goal:** Connect visible output pixels to a correct, measured RTL computation.
**Prerequisite:** Labs 04–06.
**Keep:** Input/output images, one pixel calculation, and a kernel measurement.


**Reference:** [Expected result and real screenshots](../expected-results.md#lab-07). Run the exercise yourself and record your own results.

## 1. Start with a small generated frame

```sh
cd ~/rv-lab
export LAB_BUILD_DIR="$PWD/build/course"
make camera WIDTH=7 HEIGHT=5
```

This runs copy, grayscale, Sobel, and the combined pipeline with the same input.
The image is intentionally small enough to make cycle inspection practical.
Expect all four modes to pass Spike/RTL result comparison and the independent
host pixel reference checks.

Open [the camera report](http://127.0.0.1:8771/camera/report.html). Select each
mode, inspect the visible output, and click a pixel to read its input/output
values. The displayed PNGs come from the target's dumped output, not from the
reference image used for verification.

## 2. Check one grayscale pixel by hand

Choose an input pixel and write down R, G, and B. Calculate:

```text
gray = (77 * R + 150 * G + 29 * B + 128) >> 8
```

Compare your result with the grayscale output. Then inspect an interior Sobel
pixel and a border pixel. The Sobel output border is black; the interior clamps
`abs(Gx) + abs(Gy)` to 255. The
[camera guide](../../examples/camera/README.md) gives the kernel and memory layout.

## 3. Connect a mode to its trace

Use that mode's cycle-explorer link in the camera report. Each mode has its own
actual RTL trace. Locate loads from the input or grayscale array and stores to
the output array. Check the report's capture-limit notice before treating the
visible trace as the complete computation.

The measured work differs by mode. Sobel prepares grayscale outside its ROI;
the combined pipeline measures grayscale and Sobel together. Compare the stated
ROI descriptions, not only the titles. Preparation and full-run totals are
recorded separately.

## 4. Increase the workload deliberately

```sh
make camera WIDTH=16 HEIGHT=12
```

Record each mode's ROI cycles and calculate cycles per output-frame pixel using
the stated denominator. Keep the 7×5 and 16×12 values in your notebook before
rerunning. The fixed setup and boundary cost can affect small-frame comparisons.
The detailed trace can truncate while the whole image still completes and is
verified.

For a P6 PPM image of your own:

```sh
make camera INPUT=/absolute/path/to/your-frame.ppm
```

Replace that path with a real file. P6 PPM needs only Python's standard library;
PNG/JPEG input or resizing needs Pillow. Preserve the image/input hash with your
results. Accepted dimensions run from 3×3 to 320×240 in this 1 MiB platform.

## 5. Optional visual applications

```sh
make visual WIDTH=64 HEIGHT=48 FRAME=24
```

Explore median denoise, cartoon, and the integer ball renderer in **Image
processing** in the gallery. The ball example needs at least 64×48. `FRAME=24`
selects a scene state for a single render; it is not CPU cycle 24 or a live video
stream. Read the [visual guide](../../examples/visual_suite/README.md) before
comparing their different workloads.

## Checkpoint

Submit one verified image pair, your grayscale calculation, ROI cycles and
cycles per pixel, and the trace window you inspected. Explain why kernel cycles
alone do not establish real-camera frames per second: capture, DMA, display,
off-chip memory, and a validated physical clock are outside this experiment.

Next: [Lab 08 — A reproducible project](08-project.md).
