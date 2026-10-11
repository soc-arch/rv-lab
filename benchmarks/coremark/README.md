# CoreMark workload regression

This port runs the original CoreMark workload as a **short functional regression** on an RV32IM CPU. It needs SRAM and the lab runtime, with no UART, timer peripheral, CSR instructions, operating system, or hosted C library. The same application ELF can run on Spike and on the RTL testbench.

This is not a reportable CoreMark score. The target has no timing source in this port, and the usual one-iteration run is intentionally short. The RTL testbench measures a cycle interval; Spike checks architectural results only.

## Source and attribution

The files in `upstream/` are byte-for-byte copies of [EEMBC CoreMark revision `1f483d5`](https://github.com/eembc/coremark/tree/1f483d5b8316753a742cbf5590caf5bd0a4e4777). Their SHA-256 hashes and source URLs are recorded in [upstream_sources.json](upstream_sources.json). The original copyright notices and [license and acceptable use agreement](upstream/LICENSE.md) are retained. CoreMark is a registered trademark of EEMBC.

The pinned upstream `coremark.md5` has a stale checksum for `coremark.h`: five C sources pass its check, but the header does not. Both files are preserved unchanged. Every copied file was instead checked against its pinned Git blob and the SHA-256 manifest; this includes the header.

Only the course port files and entry wrapper are new. `entry.c` includes the original `core_main.c` under a renamed entry point; the benchmark's initialization, loop, and CRC validation are preserved. Do not separately compile `upstream/core_main.c` when linking `entry.c`.

## Integration contract

Compile all of these with the same `-march=rv32im -mabi=ilp32` flags:

```text
entry.c
core_portme.c
upstream/core_list_join.c
upstream/core_matrix.c
upstream/core_state.c
upstream/core_util.c
```

Include this directory, `upstream/`, and the directory containing the framework's `lab.h`. The framework supplies startup code, a linker script, BSS initialization, a stack, and these functions:

```c
void lab_check(uint32_t id, uint32_t actual, uint32_t expected);
void lab_result(uint32_t index, uint32_t value);
void lab_roi_begin(void);
void lab_roi_end(void);
```

`main()` returns zero on successful CRC validation and nonzero on failure. Runtime checks also record missing/duplicate CRC reports, unexpected benchmark errors, and missing timing markers. There is no dependence on `printf`, `malloc`, floating-point support, or 64-bit division helpers.

Build parameters:

| Define | Default | Purpose |
|---|---:|---|
| `ITERATIONS` | `1` | Positive number of workload iterations; zero is rejected because automatic timing calibration is unavailable. |
| `COREMARK_VALIDATION` | `0` | `0`: performance seeds; `1`: validation seeds. |
| `TOTAL_DATA_SIZE` | `2000` | Fixed for the expected CRCs in this port. Other sizes are rejected. |

Both seed profiles should be part of the integration regression. Increasing iterations changes the final accumulated CRC, but the upstream list/matrix/state validation CRCs remain the expected values below.

| Profile | Seeds | Seed CRC | List CRC | Matrix CRC | State CRC |
|---|---|---|---|---|---|
| Performance seeds | `0, 0, 0x66` | `0xe9f5` | `0xe714` | `0x1fd7` | `0x8e3a` |
| Validation seeds | `0x3415, 0x3415, 0x66` | `0x18f2` | `0xe3c1` | `0x0747` | `0x8d84` |

The eight checks use IDs 100–107. Result slots are:

| Slot | Value |
|---:|---|
| 0 | Iterations |
| 1 | Seed CRC |
| 2 | List CRC |
| 3 | Matrix CRC |
| 4 | State CRC |
| 5 | Final accumulated CRC; compare Spike and RTL for the same iteration count |
| 6 | Validation-profile flag |

## Timing without a timer peripheral

`start_time()` and `stop_time()` write the runtime's SRAM markers. The RTL monitor records its cycle count when each marker store retires. The interval is the difference of those observations. Keep the same observation point when replacing the CPU so the measurement contract stays fixed.

```text
Initialization      begin-marker store       workload loop      end-marker store       CRC reporting
                         |<---------- RTL cycle interval ---------->|
```

The interval includes the small amount of marker-call/return work between those stores. It excludes initial data setup and final CRC reporting. Report the precise boundaries rather than claiming an ideal zero-overhead interval.

For a run of `N` iterations and an observed interval of `C` cycles:

```text
cycles per iteration                 = C / N
workload iterations per cycle        = N / C
projected iterations per second      = N * stated_clock_hz / C
```

Use the first two quantities for classroom comparisons. The third is a projection at an explicitly stated clock, not a measured silicon result. CPU changes can alter achievable frequency, so equal-clock cycle improvements alone do not establish a hardware speedup.

The target's `get_time()` and `time_in_secs()` return zero to identify the absence of a target timing source. The unmodified upstream code therefore produces its minimum-duration warning and does not calculate an iterations-per-second score. The port captures and checks that warning; the framework must label this result as a short workload regression. The expected timing warning is separated from CRC or data-type failures, which always fail the application.

For a future reportable benchmark, provide a calibrated elapsed-time source and follow the upstream run/reporting requirements, including the minimum duration, both seed validations, and complete build/memory disclosure. A hardware timer is one option; a cycle counter with known frequency is another. See the [upstream run rules](https://github.com/eembc/coremark/blob/1f483d5b8316753a742cbf5590caf5bd0a4e4777/README.md#run-rules) and [bare-metal timing guidance](https://github.com/eembc/coremark/blob/1f483d5b8316753a742cbf5590caf5bd0a4e4777/barebones_porting.md).

## Check this port in your workspace

From `~/rv-lab`, run both seed profiles with the same ELF on Spike and RTL:

```sh
make compare APP=coremark OPT=O2 ITERATIONS=1
make compare APP=coremark OPT=O2 ITERATIONS=1 VALIDATION=1
```

Require the eight checks and complete signatures to pass in each run. Preserve
the commands, source and ELF identity, tool versions and generated reports as
your verification evidence. `make test-smoke` includes both seed profiles;
`ITERATIONS=0` is rejected at compile time. These are short functional checks,
not official CoreMark performance results.
