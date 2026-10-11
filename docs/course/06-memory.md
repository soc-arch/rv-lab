# Lab 06 — Change memory timing

**Goal:** Explain additional execution cycles without changing the useful work.
**Prerequisite:** Labs 04 and 05; the restored eight-value sum passes.
**Keep:** A comparison table and an observed offered-versus-accepted transfer.

## 1. Establish the fast-memory run

```sh
cd ~/rv-lab
export LAB_BUILD_DIR="$PWD/build/course"
make register SOURCE=student/main.c NAME=sum-fast TITLE="Sum: fast memory" MEMORY=fast
```

Keep the input, source, optimization setting, and ROI markers unchanged for this
lesson. Record the ROI cycles, retirements, and CPI from the result report. Its
**Measurement JSON** link includes the exact memory configuration.

## 2. Add response latency

```sh
make register SOURCE=student/main.c NAME=sum-latency TITLE="Sum: memory latency" MEMORY=latency3
```

Require the functional comparison to pass. Compare this run with fast memory.
Both instruction fetches and data transactions can affect execution time, so do
not explain the entire change using the eight input loads alone. Use the
recorded memory configuration in the report/build metadata as your source of
exact settings.

## 3. Inspect backpressure

```sh
make register SOURCE=student/main.c NAME=sum-stress TITLE="Sum: memory stalls" MEMORY=stress STALL_SEED=11
```

Open the new gallery example. Find a valid request waiting for ready, then the
cycle where it is accepted. The offered address and payload must remain stable
while the sender waits. Follow its response separately. In the bus timeline,
lowercase **q/r** indicate offered transfers waiting for ready; uppercase
**Q/R** indicate accepted requests/responses.

The seed makes the selected stall experiment reproducible. Record it. A memory
request is not automatically a cache miss: this exercise uses a shared SRAM
model and does not add a cache. A request becoming valid also does not mean a
store has already changed memory.

## 4. Compare the measurements

| Memory profile | Seed if used | Correct result | ROI cycles | ROI retired instructions | ROI CPI |
|---|---|---|---|---|---|
| fast | | | | | |
| latency3 | | | | | |
| stress | 11 | | | | |

Explain whether the dynamic instruction count changed. If it did, investigate
source, options, input, and measurement boundaries before treating the difference
as a memory effect. Use the same interval for cycles and retirements.

For an optional exercise, try a second stall seed. Keep it as a separate
experiment and state whether a single seed is enough to support a general
performance claim. Preserve both runs using separate output roots if a rerun
would otherwise replace the same application/configuration directory.

## Checkpoint

Submit the table and one annotated transfer showing offered, accepted, and
response cycles. Explain why an active LSU can occupy several cycles while only
one load or store retires. Keep functional correctness as a condition of every
measurement.

Next: [Lab 07 — Process an image](07-images.md).
