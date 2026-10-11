#!/usr/bin/env python3
"""Run the reproducibility gates and retain immutable, source-bound evidence.

Run from any directory. LAB_BUILD_DIR selects generated outputs; --rtl-dir
selects a replacement core. Browser interaction checks are a separate step.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
CACHE_NAMES = {"build", "__pycache__", ".git", ".pytest_cache", ".venv", "node_modules"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_within(path, directory):
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def tree_hashes(directory, excluded=()):
    """Hash source trees without traversing generated build/cache directories."""
    files = {}
    excluded = {Path(path).resolve() for path in excluded}
    for current, directories, names in os.walk(directory):
        base = Path(current)
        directories[:] = sorted(name for name in directories
                                if name not in CACHE_NAMES
                                and (base / name).resolve() not in excluded)
        for name in sorted(names):
            path = base / name
            if path.suffix == ".pyc" or path.resolve() in excluded:
                continue
            files[path.relative_to(directory).as_posix()] = sha256(path)
    return files


def source_manifest(root, rtl, build, output):
    framework = tree_hashes(root, [root / "rtl", root / "tb", root / "provenance", build, output])
    pin = root / "provenance/snapshot.json"
    if pin.is_file():
        framework["provenance/snapshot.json"] = sha256(pin)
    # A filelist may intentionally share an include outside the selected folder.
    external = {}
    filelist = rtl / "filelist.f"
    if filelist.is_file():
        for line in filelist.read_text().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            path = (rtl / line.strip()).resolve()
            if not is_within(path, rtl) and path.is_file():
                external[str(path)] = sha256(path)
    return {"framework": framework, "rtl": tree_hashes(rtl, [build, output]),
            "tb": tree_hashes(root / "tb"), "external_rtl_dependencies": external}


def source_changes(before, after):
    changes = {}
    for section in sorted(before.keys() | after.keys()):
        old, new = before.get(section, {}), after.get(section, {})
        changed = [name for name in sorted(old.keys() | new.keys()) if old.get(name) != new.get(name)]
        if changed:
            changes[section] = changed
    return changes


def pin_identity(root, manifest):
    pin = root / "provenance/snapshot.json"
    if not pin.is_file():
        return {"status": "unavailable", "path": str(pin)}
    saved = json.loads(pin.read_text())
    identity = {"path": str(pin), "sha256": sha256(pin),
                "captured_at_utc": saved.get("captured_at_utc"),
                "note": "A different replacement core is allowed; pin comparison identifies the selected source."}
    for section in ("rtl", "tb"):
        expected = {key[len(section) + 1:]: value for key, value in saved["files_sha256"].items()
                    if key.startswith(section + "/")}
        actual = manifest[section]
        changed = [key for key in sorted(expected.keys() | actual.keys())
                   if expected.get(key) != actual.get(key)]
        identity[section] = {"matches_snapshot": not changed, "differences": changed,
                             "files_compared": len(expected)}
    return identity


def tool_provenance():
    # Use the harness's resolver so CROSS_COMPILE/SPIKE/VERILATOR overrides
    # identify the tools that the commands actually select.
    import lab
    names = ["riscv32-unknown-elf-" + suffix for suffix in ("gcc", "objdump", "nm", "objcopy")]
    selected = {"python": sys.executable}
    resolvers = {name: lambda name=name: lab.tool(name) for name in names + ["make", "spike", "verilator"]}
    resolvers.update(native_c=lab.native_c_compiler, cxx=lab.cxx_compiler)
    for name, resolve in resolvers.items():
        try:
            selected[name] = resolve()
        except lab.LabError:
            selected[name] = None
    records = {}
    for name, value in selected.items():
        path = shutil.which(value) if value else None
        if not path:
            records[name] = {"available": False, "requested": value}
            continue
        resolved = Path(path).resolve()
        records[name] = {"available": True, "path": path, "resolved_path": str(resolved),
                         "sha256": sha256(resolved)}
    return {"python_version": sys.version, "platform": platform.platform(), "executables": records,
            "versions": "See doctor log; compiler/RTL build identities are also embedded in gate reports."}


def gate_plan(rtl, baseline_only=False):
    import lab
    make_tool = lab.tool("make")
    def make(target, *variables):
        return [make_tool, "--no-print-directory", target, f"PYTHON={sys.executable}",
                f"RTL_DIR={rtl}", *variables]
    gates = [("doctor", make("doctor")),
             ("compare", make("compare", "APP=01_arithmetic")),
             ("smoke", make("test-smoke"))]
    if not baseline_only:
        gates += [("regression", make("test")), ("camera-tests", make("camera-test")),
                  ("visual-tests", make("visual-test")),
                  ("performance-tests", make("perf-test")),
                  ("registration-tests", make("registration-test")),
                  ("course-tests", make("course-test")),
                  ("performance-o0", make("compare", "APP=10_performance", "OPT=O0", "COMMITS=1", "TRACE=1", "CLOCK_MHZ=100")),
                  ("performance-o2", make("compare", "APP=10_performance", "OPT=O2", "COMMITS=1", "TRACE=1", "CLOCK_MHZ=100")),
                  ("viewer-catalog-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests",
                                            "-p", "test_viewer_catalog.py", "-v"]),
                  ("environment-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests",
                                         "-p", "test_environment.py", "-v"]),
                  ("verification-tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests",
                                          "-p", "test_verify.py", "-v"]),
                  ("gallery", make("gallery")),
                  ("registered-starter", make("register", "SOURCE=docs/course/starter/sum.c", "NAME=student-sum", "TITLE=Student sum")),
                  ("images", make("images", "WIDTH=64", "HEIGHT=48", "FRAME=24")),
                  ("export-views", make("export-views"))]
    return gates


def report_paths(name, build):
    patterns = {
        "compare": ["01_arithmetic-O2/*.json"],
        "smoke": ["regression.json"],
        "regression": ["regression.json", "memory_protocol.json"],
        "performance-o0": ["10_performance-O0/*.json", "10_performance-O0/hw.csr.txt"],
        "performance-o2": ["10_performance-O2/*.json", "10_performance-O2/hw.csr.txt"],
        "gallery": ["catalog.json", "0[1-5]*/*.json"],
        "registered-starter": ["catalog.json", "application-*/*.json"],
        "images": ["camera/report.json", "visual-suite.json", "catalog.json", "0[6-9]*/*.json"],
        "export-views": ["catalog.json", "cpu_lab_examples.zip"],
    }
    paths = {path for pattern in patterns.get(name, []) for path in build.glob(pattern) if path.is_file()}
    if name in {"compare", "smoke", "regression", "camera-tests", "visual-tests", "gallery", "images"}:
        paths.update(build.glob("verilator/*/build.json"))
    return sorted(paths)


def copy_reports(name, build, destination):
    """Copy immediately: later gates overwrite regression and application JSON."""
    records = []
    for source in report_paths(name, build):
        relative = source.relative_to(build)
        target = destination / "reports" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        records.append({"source": str(source), "saved": str(target.relative_to(destination)),
                        "sha256": sha256(target), "bytes": target.stat().st_size})
    for target in sorted(destination.glob("*-test-report.json")):
        records.append({"saved": target.name, "sha256": sha256(target), "bytes": target.stat().st_size})
    return records


def execute_gate(command, cwd, environment, logfile):
    """Stream merged output to the terminal and a persistent per-gate log."""
    with logfile.open("w") as log:
        try:
            process = subprocess.Popen(command, cwd=cwd, env=environment, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, errors="replace",
                                       start_new_session=(os.name == "posix"))
        except OSError as error:
            log.write(str(error) + "\n")
            print(error, file=sys.stderr)
            return 127
        try:
            for line in process.stdout:
                log.write(line)
                log.flush()
                print(line, end="", flush=True)
            return process.wait()
        except KeyboardInterrupt:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait()
            log.write("\nVerification interrupted by user.\n")
            return 130
        finally:
            process.stdout.close()


def run_verification(root, rtl, build, output, baseline_only=False):
    output.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    for key in ("MAKEFLAGS", "MFLAGS", "MAKELEVEL"):
        environment.pop(key, None)
    environment.update(LAB_BUILD_DIR=str(build), LAB_RTL_DIR=str(rtl), PYTHONUNBUFFERED="1")
    receipt = {"schema_version": 1, "status": "running", "started_at_utc": utc_now(),
               "lab_directory": str(root), "rtl_directory": str(rtl), "build_directory": str(build),
               "baseline_only": baseline_only, "gates": [],
               "browser_ui": {"status": "not_run", "note": "Browser interaction checks require separate evidence."},
               "environment": {key: value for key, value in environment.items()
                               if key in {"LAB_BUILD_DIR", "LAB_RTL_DIR", "CROSS_COMPILE", "SPIKE", "VERILATOR", "CC", "CXX", "MAKE"}
                               or key.startswith("RISCV32_UNKNOWN_ELF_")}}
    before = None
    exit_code = 1
    started = time.monotonic()
    save_json(output / "receipt.json", receipt)
    try:
        before = source_manifest(root, rtl, build, output)
        save_json(output / "source-before.json", before)
        receipt["snapshot_pin"] = pin_identity(root, before)
        receipt["tools"] = tool_provenance()
        for index, (name, command) in enumerate(gate_plan(rtl, baseline_only), 1):
            destination = output / f"{index:02d}-{name}"
            destination.mkdir()
            env = dict(environment, CPU_LAB_TEST_REPORT=str(destination / "camera-test-report.json"),
                       CPU_LAB_VISUAL_TEST_REPORT=str(destination / "visual-test-report.json"),
                       CPU_LAB_PERF_TEST_REPORT=str(destination / "performance-test-report.json"),
                       CPU_LAB_REGISTRATION_TEST_REPORT=str(destination / "registration-test-report.json"))
            record = {"name": name, "command": command, "cwd": str(root), "status": "running",
                      "started_at_utc": utc_now(), "log": str((destination / "stdout.log").relative_to(output))}
            receipt["gates"].append(record)
            save_json(output / "receipt.json", receipt)
            print(f"\n[{index}] {name}", flush=True)
            gate_started = time.monotonic()
            result = execute_gate(command, root, env, destination / "stdout.log")
            record.update(exit_code=result, finished_at_utc=utc_now(),
                          elapsed_seconds=round(time.monotonic() - gate_started, 3),
                          status="pass" if result == 0 else "fail")
            record["artifacts"] = copy_reports(name, build, destination)
            record["log_sha256"] = sha256(destination / "stdout.log")
            save_json(output / "receipt.json", receipt)
            if result:
                exit_code = result if 0 < result <= 255 else 1
                receipt["failed_gate"] = name
                break
        else:
            exit_code = 0
    except Exception as error:
        receipt["error"] = f"{type(error).__name__}: {error}"
        print(receipt["error"], file=sys.stderr)
    except KeyboardInterrupt:
        receipt["error"] = "Verification interrupted by user."
        exit_code = 130
    finally:
        try:
            after = source_manifest(root, rtl, build, output)
            save_json(output / "source-after.json", after)
            changes = source_changes(before, after) if before is not None else None
            receipt["source_drift"] = {"detected": bool(changes) if changes is not None else None,
                                       "changes": changes}
            if changes:
                exit_code = 1
                print("Source changed during verification; receipt is not a reproducible pass.", file=sys.stderr)
        except Exception as error:
            receipt["source_drift"] = {"detected": None, "error": str(error)}
            exit_code = 1
        receipt.update(status="pass" if exit_code == 0 else "fail", exit_code=exit_code,
                       finished_at_utc=utc_now(), elapsed_seconds=round(time.monotonic() - started, 3))
        save_json(output / "receipt.json", receipt)
        print(f"\nVerification {receipt['status'].upper()}: {output / 'receipt.json'}", flush=True)
    return exit_code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rtl-dir", type=Path, default=Path(os.environ.get("LAB_RTL_DIR", ROOT / "rtl")),
                        help="CPU source directory (default: LAB_RTL_DIR or lab/rtl)")
    parser.add_argument("--baseline-only", action="store_true", help="Run doctor, arithmetic compare, and smoke only")
    parser.add_argument("--output-dir", type=Path, help="New directory for retained evidence; must not exist")
    args = parser.parse_args()
    # Match lab.py: a relative LAB_BUILD_DIR is relative to the lab root.
    build = Path(os.environ.get("LAB_BUILD_DIR") or ROOT / "build").expanduser()
    if not build.is_absolute():
        build = ROOT / build
    build = build.resolve()
    rtl = args.rtl_dir.expanduser().resolve()
    output = (args.output_dir or build / "validation" /
              datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")).resolve()
    if is_within(ROOT, build) or is_within(rtl, build):
        parser.error("LAB_BUILD_DIR must not contain the lab or selected RTL source directory")
    if output.exists():
        parser.error(f"Evidence directory already exists: {output}")
    return run_verification(ROOT, rtl, build, output, args.baseline_only)


if __name__ == "__main__":
    sys.exit(main())
