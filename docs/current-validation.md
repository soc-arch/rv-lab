# Current P1 lab validation — 2026-10-15

The public lab now runs the actual HY-RV P1/F0/Q0 static core. The default is
**ant_j0 / early JAL OFF / ii1 memory adapter**; btfnt_j0 is the active static
comparison. Explicit j1 presets retain the previously implemented early-JAL
comparisons. They do not change the course default.

The [functional summary](current-validation.json) records actual runs against
source SHA-256
`35558e91c602324ddf5b2ab8de893bc0baead18cc9a82c3c336e16c6b3213dd8`.
It is the same source identity as the new real synthesis/Formality runs, rather
than an inherited old-core PASS label.

## Functional and student workflow results

| Actual preset | Full regression | Memory protocol | Camera | Visual | Student / CSR / registration |
| --- | ---: | ---: | --- | ---: | --- |
| ant_j0 | 47/47 | 20/20 | 11 successes + 1 expected negative | 7/7 | PASS |
| btfnt_j0 | 47/47 | 20/20 | 11 successes + 1 expected negative | 7/7 | PASS |
| ant_j1 | 47/47 | 20/20 | 11 successes + 1 expected negative | 7/7 | PASS |
| btfnt_j1 | 47/47 | 20/20 | 11 successes + 1 expected negative | 7/7 | PASS |

The 47 outcomes include 44 positive programs and three correctly detected
negative programs. Camera negatives include the timeout/stale-output check.
Image tests compare complete output bytes with Spike and independent host
references. Identical output, rather than an image's visual similarity, is the
functional criterion.

All **eight lessons / 27 workflow commands** were rerun with ant_j0. Deliberate
Lab 03 failures were detected and then repaired. The same-ELF comparisons, ROI,
CSR, memory profiles, 7×5/16×12 camera frames, 64×48 visual examples, registration,
gallery, and extracted offline export are recorded in
[reference-results.json](reference-results.json). The
[expected-results page](expected-results.md) uses the new measurements and actual
browser captures; previous results are retained as historical material.

See [complete functional receipts](../validation/functional-p1-receipts.zip).
The renderer records the actual selected preset and early JAL mode in its HTML
and downloaded SVG. External or unbound cores do not receive a P1 architecture
claim. Desktop/mobile/browser checks are recorded separately from CPU execution.

## Directed frontend and predictor verification

[Directed results](../validation/core-directed.json) cover all four presets:
transport/ownership and redirect-fault behavior, 930 static-prediction vectors
plus 36 core scenarios, and 723 backend successor/correction checks. The
[directed receipts](../validation/core-directed-receipts.zip) and
[replay harness](../validation/core-directed-harness.zip) preserve the actual run
and reproduction inputs. These runs use the imported RTL source identity.

The actual ant_j0 mul/div trace also contains 876 qualifying edges with
retirement, IR admission, and successor-fetch acceptance together; its longest
consecutive sequence has 11 edges. One measured sequence begins at cycles
6061–6063. This is an observation of that trace, not a promise of whole-program
IPC=1. The summary preserves its trace hash and three sampled PC triplets.

## Actual synthesis and Formality

Fresh real synthesis and RTL-to-gate Formality were rerun for all four imported
presets. [p1-rtl-gate-equivalence.json](../provenance/p1-rtl-gate-equivalence.json)
links actual source/configuration/library/tool/flow hashes, mapped netlist, SVF,
reports and match/verify results.

- Elaborated and mapped latch counts: 0 in every preset.
- Unintended combinational loops and unmapped leaf cells: 0 in every preset.
- Formality: 2,381 successful compare points per preset; failing, aborted and
  unverified points 0; black boxes 0.
- The 32 unmatched reference storage bits are the unused x0 RF storage, reviewed
  explicitly. They are not failed compare points.
- Synthesis warning counts match the prior reviewed source/preset results;
  the record does not claim a warning-free tool run.

Samsung LN28LPP libraries and commercial tool inputs remain private/read-only.
The public provenance includes identities and results, not foundry files or
proprietary netlists. Logical synthesis is not post-layout timing/signoff.

## Reproduction and historical boundary

Select a fresh output root and actual configuration before the documented checks:

```sh
export LAB_BUILD_DIR="$PWD/build/p1-check"
export LAB_CORE_PRESET=ant_j0
export LAB_MEMORY_ADAPTER=ii1
make doctor
make compare APP=01_arithmetic
make test
make camera-test
make visual-test
make perf-test
make registration-test
```

Use the [eight lesson commands](course/index.md) for the full student workflow,
and [reproducibility guide](reproducibility.md) for browser/export gates. Set
`PYTHON=/usr/bin/python3.11` with Make when that is the working interpreter on the
selected host; do not accidentally select an unrelated tool's python wrapper.

The [historical teaching validation](validation.md),
[historical JSON](historical/teaching-validation.json), and
[historical course results](historical/teaching-reference-results.json) are kept
for provenance. Their old one-entry-response-buffer CPU and cycle totals are
not the default implementation or current measurement baseline.
