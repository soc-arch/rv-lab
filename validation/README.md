# Current P1 validation evidence

`functional-p1.json` records the four real elaborated presets and the eight
student lessons rerun on the current P1 RTL. `functional-p1-receipts.zip` contains
the detailed JSON reports, command logs, source snapshots, software hashes and
an archive manifest. Its SHA-256 is recorded in the compact JSON.

The default is `ant_j0` with the `ii1` memory adapter. `btfnt_j0` is the normal
static predictor comparison. `ant_j1` and `btfnt_j1` explicitly enable early JAL
for regression; they do not change the default policy.

Each preset passed 47 application cases (44 positive and three expected negative
outcomes), 20 memory protocol cases, 11 camera cases plus one expected failure,
seven visual cases, and the performance/student/registration gates. The default
preset also completed 27 commands covering all eight lessons, including wrong
expectations, a real loop defect, corrected results, O0/O2 counters and traces,
three memory profiles, images, gallery registration and offline export.

The selected configuration is checked against actual executable startup banners
and distinct source-bound simulator caches. The detailed reports record the same
ELF hash for Spike and RTL. The functional run also checks that executable source
files remain unchanged from the start through the end of the run.

To reproduce from the repository root with the tools described in the setup guide:

```sh
python3 validation/run_p1_validation.py --phase all --workers 2
python3 validation/audit_p1_results.py
```

Use `--build-root /absolute/path/to/a/new/output` for an isolated repetition. Both
commands must use the same build root. The runner limits concurrent preset
workers to two. Generated simulator caches, software and raw traces remain in the
selected output tree; the public archive contains compact receipts rather than
compiled binaries.

The optional viewer browser check consumes a real trace and needs Playwright:

```sh
node viewer/check_browser.cjs build/validation-p1/ant_j0/04_muldiv-O2/trace.html build/validation-p1/browser-muldiv
node validation/check_viewer_profiles.cjs build/validation-p1
python3 validation/audit_p1_results.py
```

The checked trace contained 2,176 samples, six execution states and ten observed
handshake combinations. It also showed 876 edges combining instruction commit,
the next IR admission and the following fetch acceptance, with a maximum of 11
consecutive such edges. These are measured RTL observations for this run.
The profile browser check also opens actual traces for all four presets and
explicit unknown/external display fixtures. The fixtures test reference-view
labels and never represent measurements of an external CPU. Both the embedded
diagram and downloadable SVG follow the recorded P1 predictor/early-JAL values.

This evidence covers functional integration. The separate
[RTL versus gate proof](../provenance/p1-rtl-gate-equivalence.json) records actual
synthesis and Formality evidence. Neither simulation cycle counts nor logical
synthesis establish post-layout timing or tapeout signoff.
