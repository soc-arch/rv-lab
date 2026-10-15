#!/usr/bin/env python3
# =============================================================================
# HY-RV | run_p1_validation
# Description: Run four actual P1 presets and the eight reusable student lessons.
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See applicable manifests and verification records for provenance.
# Preserve existing license, copyright, and original author notices.
# =============================================================================
"""Reproduce integration evidence; simulation is not synthesis or formal signoff."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core_config
import verify


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def display_path(path):
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def source_identity():
    """Freeze executable laboratory sources while prose can be edited independently."""
    files = [ROOT / name for name in ("Makefile", "lab.py", "core_config.py", "verify.py",
             "applications.py", "camera_support.py", "visual_support.py", "performance.py", "course.py")]
    for directory in ("rtl", "tb", "runtime", "examples", "tests", "viewer", "benchmarks/coremark"):
        files += [path for path in (ROOT / directory).rglob("*") if path.is_file()
                  and "__pycache__" not in path.parts and path.suffix in
                  (".sv", ".svh", ".f", ".c", ".h", ".S", ".ld", ".py", ".cpp", ".html", ".svg")]
    return {str(path.relative_to(ROOT)): digest(path) for path in sorted(set(files)) if path.is_file()}


def execute(command, environment, directory, expected=0):
    directory.mkdir(parents=True, exist_ok=True)
    logfile = directory / "stdout.log"
    started = time.monotonic()
    with logfile.open("w") as log:
        result = subprocess.run(list(map(str, command)), cwd=ROOT, env=environment,
                                stdout=log, stderr=subprocess.STDOUT, timeout=3600)
    record = {"command": list(map(str, command)), "expected_exit_code": expected,
              "exit_code": result.returncode, "status": "pass" if result.returncode == expected else "fail",
              "elapsed_seconds": round(time.monotonic() - started, 3),
              "log": display_path(logfile), "log_sha256": digest(logfile)}
    save(directory / "receipt.json", record)
    print(f"{environment['LAB_CORE_PRESET']} {directory.name}: {record['status']}", flush=True)
    if record["status"] != "pass":
        print(logfile.read_text()[-6000:], flush=True)
        raise RuntimeError(f"Failed command: {logfile}")
    return record


def environment(preset, build):
    env = os.environ.copy()
    for name in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL", "OPT", "MAKEOVERRIDES"):
        env.pop(name, None)
    env.update(LAB_CORE_PRESET=preset, LAB_MEMORY_ADAPTER="ii1", LAB_BUILD_DIR=str(build),
               LAB_RTL_DIR=str(ROOT / "rtl"), PYTHONUNBUFFERED="1", CCACHE_DIR=str(build / "ccache"))
    return env


def run_preset(preset, base):
    build = base / preset
    env = environment(preset, build)
    output = build / "evidence"
    output.mkdir(parents=True, exist_ok=True)
    config = core_config.resolve(preset, "ii1")
    result = {"status": "running", "preset": preset, "configuration": config,
              "configuration_sha256": core_config.configuration_sha256(config),
              "rtl_source_hash": core_config.source_hash(ROOT / "rtl"), "gates": []}
    save(output / "summary.json", result)
    gates = [("full", [sys.executable, "lab.py", "test", "--suite", "full"])]
    for name, pattern in (("camera", "test_camera_lab.py"), ("visual", "test_visual_lab.py"),
                          ("performance", "test_performance.py"), ("student", "test_student_workflow.py"),
                          ("registration", "test_registration.py")):
        gates.append((name, [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"]))
    try:
        for name, command in gates:
            directory = output / name
            directory.mkdir(parents=True, exist_ok=True)
            gate_env = dict(env, CPU_LAB_TEST_REPORT=str(directory / "camera.json"),
                            CPU_LAB_VISUAL_TEST_REPORT=str(directory / "visual.json"),
                            CPU_LAB_PERF_TEST_REPORT=str(directory / "student.json"),
                            CPU_LAB_REGISTRATION_TEST_REPORT=str(directory / "registration.json"))
            result["gates"].append(dict(name=name, **execute(command, gate_env, directory)))
            if name == "full":
                for report in ("regression.json", "memory_protocol.json"):
                    shutil.copy2(build / report, directory / report)
            save(output / "summary.json", result)
        caches = []
        for path in sorted((build / "verilator").glob("*/build.json")):
            receipt = json.loads(path.read_text())
            assert receipt["core_configuration"] == config
            assert receipt["configuration_sha256"] == result["configuration_sha256"]
            assert receipt["rtl_source_hash"] == result["rtl_source_hash"]
            binary = path.parent / "Vtb_cpu_lab"
            caches.append({"key": path.parent.name, "identity": receipt, "receipt_sha256": digest(path),
                           "binary_sha256": digest(binary)})
        assert len(caches) == 1, f"Exactly one actual parameterized CPU cache expected: {caches}"
        result["hardware_builds"] = caches
        regression = json.loads((output / "full/regression.json").read_text())
        memory = json.loads((output / "full/memory_protocol.json").read_text())
        assert regression["status"] == "pass" and len(regression["cases"]) == 47
        assert memory["status"] == "pass" and len(memory["cases"]) == 20
        camera = json.loads((output / "camera/camera.json").read_text())
        visual = json.loads((output / "visual/visual.json").read_text())
        result["counts"] = {"functional": len(regression["cases"]), "memory_protocol": len(memory["cases"]),
                            "camera_positive": sum(c["status"] == "pass" for c in camera["cases"]),
                            "camera_expected_negative": sum(c["status"] == "expected failure" for c in camera["cases"]),
                            "visual": len(visual["cases"])}
        result["status"] = "pass"
    except Exception as error:
        result.update(status="fail", error=f"{type(error).__name__}: {error}")
    result["report_files_sha256"] = {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*.json"))
                                     if p != output / "summary.json"}
    save(output / "summary.json", result)
    return result


def lesson_workflows(base):
    build = base / "ant_j0"
    env = environment("ant_j0", build)
    output = build / "lessons"
    sources = build / "lesson-sources"
    sources.mkdir(parents=True, exist_ok=True)
    records = []
    python = [sys.executable, "lab.py"]
    def run(label, args, expected=0):
        previous = {str(path): path.stat().st_mtime_ns for path in build.glob("*/result.json")}
        record = execute(python + args, env, output / label, expected)
        # Preserve the evidence now: later variants may overwrite run directories.
        evidence = []
        for manifest in sorted(build.glob("*/build.json")):
            directory = manifest.parent
            if not (directory / "result.json").is_file():
                continue
            path = directory / "result.json"
            if previous.get(str(path)) == path.stat().st_mtime_ns:
                continue
            from importlib.util import spec_from_file_location, module_from_spec
            spec = spec_from_file_location("lesson_receipt", ROOT / "tests/artifact_receipt.py")
            module = module_from_spec(spec)
            spec.loader.exec_module(module)
            evidence.append({"directory": str(directory.relative_to(build)), **module.capture(directory)})
        save(output / label / "applications.json", evidence)
        record.update(lesson=label, application_receipt_sha256=digest(output / label / "applications.json"))
        records.append(record)
    run("lab01-doctor", ["doctor"])
    run("lab01-compare", ["run", "--backend", "both", "--app", "01_arithmetic"])
    run("lab01-smoke", ["test", "--suite", "smoke"])
    shutil.copy2(build / "regression.json", output / "lab01-smoke/regression.json")
    main = sources / "main.c"
    main.write_text((ROOT / "docs/course/starter/sum.c").read_text())
    for backend in ("sw", "hw", "both"):
        run("lab02-" + backend, ["run", "--backend", backend, "--source", str(main)])
    original = main.read_text()
    main.write_text(original.replace("7, 8}", "7, 10}").replace("sum, 36", "sum, 38"))
    run("lab02-changed-input", ["run", "--backend", "both", "--source", str(main)])
    main.write_text(original)
    run("lab02-restored", ["run", "--backend", "both", "--source", str(main)])
    debug = sources / "debug.c"
    debug.write_text((ROOT / "docs/course/starter/debug.c").read_text())
    run("lab03-wrong-expectation", ["run", "--backend", "both", "--source", str(debug)], 1)
    debug.write_text(debug.read_text().replace("maximum, 99", "maximum, 24"))
    run("lab03-corrected", ["run", "--backend", "both", "--source", str(debug)])
    correct = debug.read_text().replace("24, 3}", "24, 30}").replace("maximum, 24", "maximum, 30")
    debug.write_text(correct)
    run("lab03-last-element", ["run", "--backend", "both", "--source", str(debug)])
    debug.write_text(correct.replace("i < count", "i + 1 < count"))
    run("lab03-algorithm-defect", ["run", "--backend", "both", "--source", str(debug)], 1)
    debug.write_text(correct)
    run("lab03-defect-fixed", ["run", "--backend", "both", "--source", str(debug)])
    run("lab04-register", ["register", "--source", str(main), "--name", "my-sum", "--title", "My sum",
                           "--trace-symbol", "sum_values", "--trace-limit", "2000"])
    performance = sources / "performance.c"
    performance.write_text((ROOT / "docs/course/starter/performance.c").read_text())
    for optimization in ("O0", "O2"):
        run("lab05-" + optimization, ["run", "--backend", "both", "--source", str(performance), "--opt", optimization,
                                     "--csr-counters", "--commit-log", "--trace", "--clock-mhz", "100"])
    for profile in ("fast", "latency3", "stress"):
        run("lab06-" + profile, ["register", "--source", str(main), "--name", "sum-" + profile,
                                "--title", "Sum: " + profile, "--memory-profile", profile,
                                "--stall-seed", "11"] if profile == "stress" else
            ["register", "--source", str(main), "--name", "sum-" + profile,
             "--title", "Sum: " + profile, "--memory-profile", profile])
    for width, height in ((7, 5), (16, 12)):
        run(f"lab07-camera-{width}x{height}", ["camera", "--trace", "--width", str(width), "--height", str(height)])
    run("lab07-visual", ["visual", "--trace", "--width", "64", "--height", "48", "--frame", "24"])
    project = sources / "project.c"
    project.write_text(main.read_text())
    for optimization in ("O0", "O2"):
        run("lab08-project-" + optimization,
            ["register", "--source", str(project), "--name", "project", "--title", "Reproducible sum",
             "--opt", optimization, "--commit-log"])
    run("lab08-gallery", ["gallery", "--trace"])
    run("lab08-course", ["course"])
    run("lab08-export-views", ["export-views"])
    archive = build / "cpu_lab_examples.zip"
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        metadata = json.loads(bundle.read("manifest.json"))
        for name, expected in metadata["sha256"].items():
            assert hashlib.sha256(bundle.read(name)).hexdigest() == expected
    result = {"status": "pass", "preset": "ant_j0", "records": records,
              "lessons": 8, "export_sha256": digest(archive), "export_integrity": "pass"}
    save(output / "summary.json", result)
    return result


def profile_views(base):
    """Real traces for four profiles plus explicitly scoped render-only fixtures."""
    from viewer.render import generate
    records = []
    for preset in core_config.PRESETS:
        records.append(execute([sys.executable, "lab.py", "run", "--backend", "both", "--app", "04_muldiv",
                                "--trace", "--trace-limit", "4000"], environment(preset, base / preset),
                               base / "profile-views" / preset))
    source = base / "ant_j0/04_muldiv-O2"
    actual = json.loads((source / "hw.json").read_text())
    for name, configuration in (("unknown", None), ("external", {
            "model_id": "external_memory_v1_cpu", "preset": "external",
            "configuration_status": "parameterless_public_contract", "effective_parameters": {}})):
        metadata = {"title": "Render-only fixture; no external CPU measurement",
                    "description": "Reuses a current P1 trace only to test display scope; not measured on an external CPU.",
                    "fixture_source": {"actual_preset": "ant_j0", "rtl_source_hash": actual["rtl_source_hash"],
                                       "elf_sha256": actual["elf_sha256"]}}
        if configuration is not None:
            metadata["core_configuration"] = configuration
        generate(source / "trace.jsonl", source / "program.dis",
                 base / "viewer-profile-fixtures" / name / "trace.html", metadata)
    return {"status": "pass", "commands": records,
            "fixture_scope": "external and unknown are explicit UI fixtures; no external CPU measurement"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", type=Path, default=ROOT / "build/validation-p1")
    parser.add_argument("--phase", choices=("all", "matrix", "lessons", "unit", "profiles"), default="all")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    base = args.build_root.resolve()
    base.mkdir(parents=True, exist_ok=True)
    before = source_identity()
    save(base / (args.phase + "-source-before.json"), before)
    report = {"schema_version": 1, "status": "running", "phase": args.phase,
              "started_at_utc": datetime.now(timezone.utc).isoformat(), "presets": []}
    save(base / (args.phase + "-receipt.json"), report)
    try:
        if args.phase in ("all", "unit"):
            commands = [("course", "test_course.py"), ("viewer", "test_viewer_catalog.py"),
                        ("viewer-identity", "test_viewer_core_identity.py"),
                        ("environment", "test_environment.py"), ("verify", "test_verify.py"),
                        ("profiles", "test_core_profiles.py")]
            report["unit"] = [execute([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern, "-v"],
                                      environment("ant_j0", base / "ant_j0"), base / "unit" / label)
                              for label, pattern in commands]
        if args.phase in ("all", "matrix"):
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                report["presets"] = list(pool.map(lambda p: run_preset(p, base), core_config.PRESETS))
            assert all(item["status"] == "pass" for item in report["presets"])
        if args.phase in ("all", "lessons"):
            report["lessons"] = lesson_workflows(base)
        if args.phase in ("all", "profiles"):
            report["profile_views"] = profile_views(base)
        after = source_identity()
        save(base / (args.phase + "-source-after.json"), after)
        report["source_drift"] = {name: [before.get(name), after.get(name)] for name in sorted(before.keys() | after.keys())
                                  if before.get(name) != after.get(name)}
        assert not report["source_drift"], "Executable laboratory sources changed during validation"
        report["status"] = "pass"
    except Exception as error:
        report.update(status="fail", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        save(base / (args.phase + "-receipt.json"), report)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
