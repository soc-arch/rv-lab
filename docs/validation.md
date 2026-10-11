# Validation record — 2026-10-11

The standalone teaching package passed actual functional execution and student-workflow checks. The machine-readable record is [validation.json](validation.json). These results cover the teaching CPU and its local framework; the full `verify.py` driver, EDA synthesis, Formality, achieved timing, place and route, and tapeout signoff were not performed.

## What passed

- CPU regression: **47/47 expected outcomes**, comprising 44 successful programs and three correctly rejected programs: nonzero return, failed known-answer check, and bounded hang.
- Memory protocol: **20/20** cases.
- Larger images: four camera modes and three integer visual applications at **64×48**, with ball frame 24. Each backend's complete **9,216 RGB bytes** matched the independent reference in every case; architectural signatures also matched.
- Directed images: camera 8 test methods / 12 evidence outcomes (11 successes and one expected timeout with stale-output removal); visual 6 methods / 7 real firmware cases.
- Performance: three host parsing tests and two real student-workflow tests, including O0/O2 CSR values checked against actual instruction retirement, complete retirement-count agreement, and a correctly rejected failed custom program.
- Registration: two lifecycle tests, five successful recorded registrations, and the course sum starter registered with its trace and complete instruction log.
- Documentation browser: all eight lessons, command copying, 1,440 px desktop and 390 px mobile checks passed; no browser errors were recorded.

## Actual performance sample

The sum(1..32) example returned **528** at both optimization levels. Values below are **cycles / retired instructions** for this tested tool/source profile, not fixed answers for other compilers or CPU versions.

| Optimization | Full run | Testbench ROI | CSR interval |
| --- | ---: | ---: | ---: |
| O0 | 23,619 / 10,344 | 1,178 / 486 | 1,571 / 660 |
| O2 | 9,195 / 4,085 | 322 / 143 | 390 / 172 |

The complete retirement logs contained **10,344 instructions at O0** and **4,085 at O2**, matching the testbench. Each contained 12 CSR instructions. CSR reads are sequential and include read/record overhead; they use different boundaries from the testbench ROI. An assumed 100 MHz was used for report projections and does not establish an achieved clock or silicon performance.

## Course starter results

Both backends used the same ELF and agreed on the complete functional signature in all cases, including deliberate failed checks. Equal signatures alone do not make a wrong answer pass.

| Case | Actual / expected | Outcome |
| --- | ---: | --- |
| sum36 | 36 / 36 | PASS |
| debug-expected-failure | 24 / 99 | Expected failure verified |
| debug-oracle-repaired | 24 / 24 | PASS |
| debug-last-element-good | 30 / 30 | PASS |
| debug-introduced-loop-defect | 24 / 30 | Expected failure verified |
| debug-loop-restored | 30 / 30 | PASS |
| performance136 | 136 / 136 | PASS |

The debugging starter's original loop is valid. Its first failure is the intentionally wrong expectation of 99. The last-element loop defect was introduced only in a separate test copy, correctly rejected, and then restored.

## Memory timing sample

The sum starter returned **36** under all three profiles. The loaded program and full functional signature were identical; only the memory service configuration changed.

| Profile | Full cycles | ROI cycles |
| --- | ---: | ---: |
| fast | 8,253 | 114 |
| latency3 | 15,639 | 218 |
| stress11 | 29,824 | 435 |

## Source and tool identity

All **93 selected implementation/input files** had identical hashes before and after both runs. This identity includes framework, RTL, TB, runtime, application/benchmark/test sources, viewer assets and course C starters; generated documentation and metadata are outside the runtime identity. The relative-file manifest SHA-256 is:

`410b8f4133f82d42486fa9b838250849ab294a86c62edddfd9eec768b081fd91`

Actual tool version first lines:

- g++ (GCC) 13.2.1 20231205 (Red Hat 13.2.1-6)
- Python 3.11.13
- riscv32-unknown-elf-gcc (GCC) 15.2.0
- Spike RISC-V ISA Simulator 1.1.1-dev
- Verilator 5.028 2024-08-21 rev v5.028

A fresh simulator build with outer `OPT=O0` passed. The initial full run had already passed all 47 CPU outcomes but could not start the memory cases because its default compiler-cache location was not writable. That failed receipt was preserved. A fresh build/output root with an explicit writable cache passed all 47 CPU and 20 memory cases without source changes.

## Reproduce and evidence

With the documented tools configured, select a new `LAB_BUILD_DIR`; also select a writable `CCACHE_DIR` when running in a restricted environment. Run:

```sh
make compare APP=01_arithmetic OPT=O0
make test
make images WIDTH=64 HEIGHT=48 FRAME=24
make perf-test
make registration-test
make camera-test
make visual-test
```

The following hashes identify retained raw evidence. Raw logs and receipts remain with the maintainer; this public record omits machine paths, addresses and account details.

- `initial_raw_receipt`: `2e867b48a0d4b3a25b9fe302a995b775882f3b86a6722f7c9ba9e2549f69b52a`
- `fresh_rerun_raw_receipt`: `f26b2443e2f277e51c907bb6e820a6c1704e2a619db30446b822cc1f4472b3ad`
- `strict_semantic_summary`: `56a3e596c78fb44ea2a1d575169a5d4a7f84e19f0e670c875f89c0d50f601596`
- `tool_identity_record`: `68fe9709f0bef5f556d6554377e8c27585caf96e35fece8fa48cf8c2a5abdced`
- `browser_raw_receipt`: `6400c26fba0c8d802f06f618e931abcbad5e2a649704d8ad3011e7f429a0371b`

## Laboratory shared tools

A separate server run using only the shared environment selected by
`source /tools/rv-lab/env.sh` passed the same-ELF arithmetic comparison,
**17/17 smoke outcomes**, **47/47 full outcomes** and **20/20 memory protocol cases**.
It used Python 3.11.7, RISC-V GCC 15.2.0, Spike 1.1.1-dev, Verilator 5.028
and host GCC 13.2.1. The shared tool tree contains 1,016 files; the permission
check found no files or parent tool directories inaccessible to other users.
Compiler caching is disabled in this shared environment, so it does not require
a separate compiler-cache executable.
