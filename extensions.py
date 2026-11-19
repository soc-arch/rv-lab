# =============================================================================
# HY-RV | extensions
# Description: Lab 09/10 support: extension builds, Spike model, student RTL copies, tests, comparison.
#
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
#
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See the applicable manifests and verification records for
# file-specific provenance, revision history, and validation evidence.
# Preserve existing license, copyright, and original author notices.
# =============================================================================

"""Everything here is opt-in. Without EXT=..., an extension RTL directory or an
ext-* command, lab.py behaves exactly as it did for Labs 01-08."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import time

import core_config

ROOT = Path(__file__).resolve().parent
EXT_CHOICES = ("sw", "xdot4", "xacc")
SPIKE_EXTENSION = {"xdot4": "hyrv_xdot4", "xacc": "hyrv_xacc"}
DEFINES = {"sw": [], "xdot4": ["-DHAVE_XDOT4=1"], "xacc": ["-DHAVE_XACC=1"]}
LABS = {"09": "xdot4", "10": "xacc"}
STARTER = ROOT / "docs/course/starter/dot.c"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rtl_extension(args):
    """EXTENSION.json of the selected RTL directory, or None for the bundled/other CPU."""
    rtl = getattr(args, "rtl_dir", None)
    found = core_config.extension_manifest(rtl) if rtl else None
    return found[0] if found else None


def name_suffix(args):
    """Distinct output names for extension builds; empty for every Lab 01-08 run."""
    parts = []
    if getattr(args, "ext", None):
        parts.append("ext-" + args.ext)
    manifest = rtl_extension(args)
    if manifest:
        parts.append("core-lab" + manifest["lab"])
        if manifest["extension"] == "xacc":
            parts.append(f"lat{getattr(args, 'xacc_latency', None) or 1}")
        if manifest.get("variant"):
            parts.append(manifest["variant"])
    if getattr(args, "irq_period", None):
        parts.append(f"irq{args.irq_period}")
    return "".join("-" + p for p in parts)


def compile_flags(ext):
    return ["-I", str(ROOT / "ext/include"), *DEFINES[ext]]


def spike_include(spike):
    if os.environ.get("SPIKE_INCLUDE"):
        return Path(os.environ["SPIKE_INCLUDE"]).expanduser().resolve()
    return Path(spike).resolve().parent.parent / "include"


def spike_plugin(spike, cxx, build, require, error):
    """Compile ext/spike/hyrv_ext.cc against the installed Spike headers (cached)."""
    source = ROOT / "ext/spike/hyrv_ext.cc"
    include = spike_include(spike)
    header = include / "riscv/extension.h"
    if not header.is_file():
        raise error(f"Spike extension headers not found at {include}. Labs 09-10 need the "
                    "headers installed with Spike (include/riscv/extension.h); set SPIKE_INCLUDE.")
    identity = {"source": digest(source), "header": digest(header), "spike": str(Path(spike).resolve()), "cxx": cxx}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out = build / "spike-ext" / key / "libhyrv_ext.so"
    if not out.is_file():
        out.parent.mkdir(parents=True, exist_ok=True)
        require([cxx, "-std=c++17", "-O2", "-fPIC", "-shared", "-I", include, "-I", include / "riscv",
                 source, "-o", out], out.parent / "build.log")
    return out, {**identity, "library": str(out), "library_sha256": digest(out)}


def doctor_line(spike):
    header = spike_include(spike) / "riscv/extension.h"
    return f"Spike extension headers (Labs 09-10): {header if header.is_file() else 'MISSING ' + str(header)}"


# ---------------------------------------------------------------------------
# make lab09-init / lab10-init
# ---------------------------------------------------------------------------
def init(args, error):
    lab = args.lab
    if lab not in LABS:
        raise error("Use --lab 09 or --lab 10")
    overlay = ROOT / "ext" / f"lab{lab}" / "overlay"
    workspace = ROOT / "student" / f"lab{lab}"
    target = workspace / "rtl"
    if target.exists():
        if not args.force:
            raise error(f"{target} already exists and may hold your work. Keep it, or repeat with "
                        f"FORCE=1 to move it aside and start from a fresh copy.")
        backup = workspace / ("rtl.backup-" + time.strftime("%Y%m%d-%H%M%S"))
        target.rename(backup)
        print(f"Moved your previous copy to {backup}")
    workspace.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "rtl", target)
    shutil.copytree(overlay, target, dirs_exist_ok=True)
    receipt = {"schema_version": 1, "lab": lab, "extension": LABS[lab],
               "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "base_rtl_source_hash": core_config.source_hash(ROOT / "rtl"),
               "overlay_files": {str(p.relative_to(overlay)): digest(p) for p in sorted(overlay.rglob("*")) if p.is_file()}}
    (workspace / "init.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Created {target}")
    print(f"  = bundled rtl/ + ext/lab{lab}/overlay ({len(receipt['overlay_files'])} files). Your TODOs:")
    for path in sorted(target.rglob("*.sv")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"TODO\(lab\d\d-\d\)", line):
                print(f"  {path.relative_to(ROOT)}:{number}: {line.strip()}")
    print(f"Use it with: RTL_DIR=$PWD/{target.relative_to(ROOT)}")


# ---------------------------------------------------------------------------
# make ext-test EXT=xdot4|xacc RTL_DIR=...
# ---------------------------------------------------------------------------
def require_matching_rtl(args, error):
    manifest = rtl_extension(args)
    if args.ext not in SPIKE_EXTENSION:
        raise error("ext-test needs EXT=xdot4 (Lab 09) or EXT=xacc (Lab 10)")
    if not manifest:
        raise error("ext-test needs RTL_DIR set to your Lab 09/10 copy (make lab09-init or lab10-init)")
    if manifest["extension"] != args.ext:
        raise error(f"RTL_DIR holds the Lab {manifest['lab']} core ({manifest['extension']}), "
                    f"but EXT={args.ext}. Use the matching pair.")
    return manifest


def directed(args, run, build_hardware, save_json, build, error):
    require_matching_rtl(args, error)
    if args.xacc_latency is not None:
        latencies = [args.xacc_latency]
    else:
        latencies = [1, 3] if args.ext == "xacc" else [None]
    cases = []
    report_path = build / f"ext-test-{args.ext}.json"
    for latency in latencies:
        base = dict(vars(args), xacc_latency=latency, backend="both", trace=False, commit_log=False)
        base["allow_traps"] = True  # the directed programs handle their own illegal-instruction traps
        hardware = build_hardware(argparse.Namespace(**base))
        test = "ext_" + args.ext
        plan = [(test, opt, profile, None) for opt in ("O0", "O2") for profile in ("fast", "stress")]
        # Interrupts at pseudo-random points: results must still match Spike exactly.
        # Gaps of 1..N cycles; N leaves the program time to progress between handlers.
        plan += [(test, "O2", "fast", 300), (test, "O2", "stress", 997)]
        plan.append(("dot", "O2", "fast", None))
        for app, opt, profile, irq in plan:
            case = argparse.Namespace(**base)
            case.app, case.opt, case.memory_profile, case.irq_period = app, opt, profile, irq
            case.source = [str(STARTER)] if app == "dot" else None
            for key in ("i_latency", "d_latency", "i_interval", "d_interval", "stall_seed", "stall_max"):
                setattr(case, key, None)
            ok, out, summary = run(case, hardware)
            taken = None
            if irq:
                taken = json.loads((out / "hw.json").read_text()).get("metrics", {}).get("irq_taken", 0)
                if not taken:
                    ok = False
                    print(f"  FAIL: no interrupt was taken with +irq_period={irq}")
            cases.append({"case": app, "optimization": opt, "memory_profile": profile, "xacc_latency": latency,
                          "irq_period": irq, "irq_taken": taken, "passed": bool(ok), "output": out.name, "result": summary})
            save_json(report_path, {"status": "running", "extension": args.ext, "cases": cases})
    if args.ext == "xacc":
        cases += stall_cases(args, latencies, run, build_hardware, build, save_json, report_path, cases)
    passed = all(c["passed"] for c in cases)
    save_json(report_path, {"schema_version": 1, "status": "pass" if passed else "fail", "extension": args.ext,
                            "rtl_dir": str(Path(args.rtl_dir).resolve()), "cases": cases,
                            "verified_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    print(f"EXT-TEST {'PASS' if passed else 'FAIL'}: {sum(c['passed'] for c in cases)}/{len(cases)} cases "
          f"({args.ext}; latencies {', '.join(str(l) for l in latencies if l) or 'n/a'})")
    print(f"  Report: {report_path}")
    return passed


def stall_rtl(rtl, build):
    """Build copy of a Lab 10 CPU with the verification-only XIF stall shim inserted."""
    rtl = Path(rtl).resolve()
    key = core_config.source_hash(rtl)[:16]
    target = build / "xif-stall" / key / "rtl"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(rtl, target)
    shutil.copy2(ROOT / "tests/xif_stall/teaching_cpu.sv", target / "compat/teaching_cpu.sv")
    shutil.copy2(ROOT / "tests/xif_stall/xif_stall_shim.sv", target / "compat/xif_stall_shim.sv")
    lines = (target / "filelist.f").read_text().splitlines()
    lines.insert(lines.index("compat/teaching_cpu.sv"), "compat/xif_stall_shim.sv")
    (target / "filelist.f").write_text("\n".join(lines) + "\n")
    manifest = json.loads((target / core_config.EXTENSION_FILE).read_text())
    manifest.update(variant="xifstall", display_suffix=manifest.get("display_suffix", "") + " + XIF stall shim (test)")
    (target / core_config.EXTENSION_FILE).write_text(json.dumps(manifest, indent=2) + "\n")
    return target


def stall_cases(args, latencies, run, build_hardware, build, save_json, report_path, previous):
    """Random issue/result stalls between core and coprocessor, with and without IRQs."""
    rtl = stall_rtl(args.rtl_dir, build)
    results = []
    for latency, irq, profile in ((latencies[0], None, "fast"), (latencies[-1], 300, "fast")):
        base = dict(vars(args), rtl_dir=str(rtl), xacc_latency=latency, backend="both", trace=False,
                    commit_log=False, allow_traps=True, irq_period=irq, app="ext_xacc", opt="O2",
                    memory_profile=profile, source=None)
        case = argparse.Namespace(**base)
        for key in ("i_latency", "d_latency", "i_interval", "d_interval", "stall_seed", "stall_max"):
            setattr(case, key, None)
        ok, out, summary = run(case, build_hardware(case))
        log = (out / "hw.log").read_text(errors="replace")
        found = re.search(r"\[XIF-STALL\] issue_stall_cycles=(\d+) result_stall_cycles=(\d+)", log)
        stalls = tuple(int(x) for x in found.groups()) if found else (0, 0)
        if not (found and stalls[0] > 0 and stalls[1] > 0):
            ok = False
            print("  FAIL: the XIF stall shim did not stall both channels")
        results.append({"case": "ext_xacc+xif_stall", "optimization": "O2", "memory_profile": profile,
                        "xacc_latency": latency, "irq_period": irq, "issue_stall_cycles": stalls[0],
                        "result_stall_cycles": stalls[1], "passed": bool(ok), "output": out.name,
                        "result": summary})
        save_json(report_path, {"status": "running", "extension": args.ext, "cases": previous + results})
    return results


# ---------------------------------------------------------------------------
# make ext-compare: the same dot.c on the base core, the Lab 09 core and the Lab 10 core
# ---------------------------------------------------------------------------
def compare(args, run, save_json, build, error):
    source = Path(args.source[0]).resolve() if args.source else STARTER
    lab09 = Path(args.lab09_rtl or ROOT / "student/lab09/rtl").resolve()
    lab10 = Path(args.lab10_rtl or ROOT / "student/lab10/rtl").resolve()
    try:
        latencies = [int(x) for x in args.latencies.split(",") if x.strip()]
    except ValueError:
        latencies = []
    if not latencies or any(not 1 <= n <= 255 for n in latencies):
        raise error("LATENCIES must be a non-empty comma-separated list of 1..255, such as 1,2,4,8")
    variants = [("sw-base", "Software, base P1 core", "sw", None, None)]
    missing = []
    for path, lab in ((lab09, "09"), (lab10, "10")):
        found = core_config.extension_manifest(path) if path.is_dir() else None
        if not found or found[0]["lab"] != lab:
            missing.append(f"Lab {lab} core not found at {path} (make lab{lab}-init, then finish its TODOs)")
    if not any(m.startswith("Lab 09") for m in missing):
        variants += [("sw-lab09", "Software, Lab 09 core", "sw", lab09, None),
                     ("xdot4", "XDOT4 in EX (Lab 09)", "xdot4", lab09, None)]
    if not any(m.startswith("Lab 10") for m in missing):
        variants.append(("sw-lab10", "Software, Lab 10 core", "sw", lab10, 1))
        variants += [(f"xacc-l{n}", f"XACC coprocessor, latency {n} (Lab 10)", "xacc", lab10, n) for n in latencies]
    rows = []
    for key, title, ext, rtl, latency in variants:
        case = argparse.Namespace(**dict(vars(args), ext=ext, rtl_dir=str(rtl) if rtl else None, xacc_latency=latency,
                                         source=[str(source)], backend="both", trace=False, commit_log=False,
                                         opt=args.opt, memory_profile=args.memory_profile))
        ok, out, summary = run(case)
        perf = json.loads((out / "performance.json").read_text())
        hw = json.loads((out / "hw.json").read_text())
        roi = perf["measurements"].get("roi", {})
        rows.append({"key": key, "title": title, "ext": ext, "rtl_dir": str(rtl) if rtl else "rtl (bundled)",
                     "xacc_latency": latency, "status": summary["status"], "report": str(out / "report.html"),
                     "roi_cycles": roi.get("cycles"), "roi_retired": roi.get("retired"), "roi_cpi": roi.get("cpi"),
                     "result": hw.get("results", {}).get("0"), "elf_sha256": summary["elf_sha256"]})
    base = rows[0]
    for row in rows:
        if row["roi_cycles"] and base["roi_cycles"]:
            row["speedup_vs_software"] = base["roi_cycles"] / row["roi_cycles"]
            row["instructions_vs_software"] = row["roi_retired"] / base["roi_retired"]
    results = {r["result"] for r in rows}
    passed = all(r["status"] == "pass" for r in rows) and len(results) == 1 and not missing
    status = "pass" if passed else ("incomplete" if missing and len(results) == 1 and
                                    all(r["status"] == "pass" for r in rows) else "fail")
    report = {"schema_version": 1, "status": status, "source": str(source),
              "source_sha256": digest(source), "optimization": args.opt, "memory_profile": args.memory_profile,
              "same_result_everywhere": len(results) == 1, "missing": missing, "rows": rows,
              "boundary": "RTL marker ROI around dot_kernel(); cycles at the simulated clock, not wall time",
              "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    directory = build / "extensions"
    save_json(directory / "compare.json", report)
    (directory / "compare.html").write_text(compare_page(report, directory))
    print()
    print(f"{'Variant':44} {'ROI cycles':>11} {'retired':>9} {'CPI':>6} {'speedup':>8}")
    for r in rows:
        speed = f"{r['speedup_vs_software']:.2f}x" if r.get("speedup_vs_software") else "-"
        cpi = f"{r['roi_cpi']:.2f}" if r.get("roi_cpi") else "-"
        print(f"{r['title']:44} {r['roi_cycles'] or '-':>11} {r['roi_retired'] or '-':>9} {cpi:>6} {speed:>8}")
    for note in missing:
        print("  NOTE: " + note)
    print(f"EXT-COMPARE {status.upper()}: {len(rows)} runs, "
          f"{'identical' if len(results) == 1 else 'DIFFERENT'} dot-product results"
          + (" (a lab core is missing; this is not a full comparison)" if missing else ""))
    print(f"  Table: {directory / 'compare.html'} (make serve, then /extensions/compare.html)")
    return passed


def compare_page(report, directory):
    esc = lambda value: html.escape(str(value))
    best = max((r.get("speedup_vs_software") or 0) for r in report["rows"]) or 1
    body = []
    for r in report["rows"]:
        speed = r.get("speedup_vs_software")
        width = 0 if not speed else max(2, round(100 * speed / best))
        try:
            href = os.path.relpath(r["report"], directory)
        except ValueError:
            href = r["report"]
        cpi = "-" if not r.get("roi_cpi") else "%.2f" % r["roi_cpi"]
        speed_text = "-" if not speed else "%.2f×" % speed
        body.append(
            "<tr><td><a href='" + esc(href) + "'>" + esc(r["title"]) + "</a></td>"
            "<td>" + esc(r["status"].upper()) + "</td><td class=n>" + esc(r["roi_cycles"]) + "</td>"
            "<td class=n>" + esc(r["roi_retired"]) + "</td><td class=n>" + cpi + "</td>"
            "<td class=n>" + speed_text + "</td><td><div class=bar style='width:" + str(width) + "%'></div></td></tr>")
    notes = "".join("<li>" + esc(n) + "</li>" for n in report["missing"])
    return ("<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Extension comparison</title><style>body{font:15px/1.5 system-ui,sans-serif;margin:24px auto;max-width:980px;padding:0 16px;color:#1d2a36}"
            "table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #d5dde5;padding:6px 8px;text-align:left}"
            ".n{text-align:right;font-variant-numeric:tabular-nums}.bar{height:12px;background:#2f6f9f;border-radius:2px}"
            ".pass{color:#20743a}.fail{color:#a32020}code{background:#eef2f5;padding:1px 4px}</style>"
            "<nav><a href='../results.html'>All program results</a></nav>"
            "<h1>One dot product, three implementations</h1>"
            f"<p class={esc(report['status'])}><strong>{esc(report['status'].upper())}</strong> · "
            f"{'identical results' if report['same_result_everywhere'] else 'results differ'} · "
            f"{esc(report['optimization'])} · memory {esc(report['memory_profile'])}</p>"
            "<p>Speedup = software ROI cycles on the base core ÷ ROI cycles of the variant. "
            "ROI = the measured <code>dot_kernel()</code> call only. Cycles are simulated clock cycles; "
            "a change of clock frequency (see the synthesis notes in the lab) is not included.</p>"
            "<table><thead><tr><th>Variant</th><th>Result</th><th class=n>ROI cycles</th><th class=n>ROI retired</th>"
            "<th class=n>CPI</th><th class=n>Speedup</th><th></th></tr></thead><tbody>" + "".join(body) + "</tbody></table>"
            + (f"<ul>{notes}</ul>" if notes else "") +
            f"<p><small>Source <code>{esc(report['source'])}</code> SHA-256 <code>{esc(report['source_sha256'])}</code>. "
            "Each row links to its full report.</small></p></html>")
