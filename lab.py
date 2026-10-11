#!/usr/bin/env python3
"""One freestanding ELF, two execution backends, one result contract."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent

def build_directory():
    """Keep candidate outputs independent; relative overrides are lab-relative."""
    directory = Path(os.environ.get("LAB_BUILD_DIR") or "build").expanduser()
    if not directory.is_absolute(): directory = ROOT / directory
    return directory.resolve()

BUILD = build_directory()
RAM_BASE, RAM_BYTES = 0x80000000, 0x100000
EXAMPLES = ["01_arithmetic", "02_memory", "03_control", "04_muldiv", "05_functions"]
VISUAL_EXAMPLES = ["07_denoise", "08_cartoon", "09_ball"]
MEMORY_PROFILES = {
    "fast": dict(i_latency=1, d_latency=1, i_interval=1, d_interval=1, stall_seed=1, stall_max=0),
    "latency2": dict(i_latency=2, d_latency=2, i_interval=1, d_interval=1, stall_seed=1, stall_max=0),
    "latency3": dict(i_latency=3, d_latency=3, i_interval=3, d_interval=3, stall_seed=1, stall_max=0),
    "stress": dict(i_latency=5, d_latency=5, i_interval=2, d_interval=3, stall_seed=17, stall_max=4),
}

class LabError(Exception):
    pass

def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def memory_configuration(args):
    """Runtime RTL timing, independent of the compiled software and Spike ISA."""
    name = getattr(args, "memory_profile", "fast")
    if name not in MEMORY_PROFILES:
        raise LabError(f"Unknown memory profile: {name}")
    config = dict(MEMORY_PROFILES[name])
    for key in config:
        value = getattr(args, key, None)
        if value is not None: config[key] = value
        minimum = 0 if key in ("stall_seed", "stall_max") else 1
        if not isinstance(config[key], int) or not minimum <= config[key] <= 1000000:
            raise LabError(f"{key} must be an integer from {minimum} through 1000000")
    return config

def memory_suffix(args):
    config = memory_configuration(args)
    if config == MEMORY_PROFILES["fast"]: return ""
    for name, profile in MEMORY_PROFILES.items():
        if config == profile: return "-mem-" + name
    return "-mem-" + hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:8]

def source_label(path):
    try: return str(path.relative_to(ROOT))
    except ValueError: return str(path)

def tool(name):
    override = os.environ.get({"spike": "SPIKE", "verilator": "VERILATOR"}.get(name, name.upper().replace("-", "_")))
    candidates = [override] if override else []
    if name.startswith("riscv32-unknown-elf-"):
        suffix = name[len("riscv32-unknown-elf-"):]
        if os.environ.get("CROSS_COMPILE"):
            candidates.append(os.environ["CROSS_COMPILE"] + suffix)
    candidates += [name, str(Path.home() / "tools/riscv/bin" / name)]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return str(Path(resolved).absolute())
    raise LabError(f"Missing {name}. See README prerequisites and tool environment variables.")

def cxx_compiler():
    preferred = "/opt/rh/gcc-toolset-12/root/usr/bin/g++"
    candidate = os.environ.get("CXX") or (preferred if Path(preferred).exists() else "g++")
    resolved = shutil.which(candidate)
    if not resolved: raise LabError(f"Missing C++ compiler: {candidate}. Set CXX to a compiler executable.")
    return str(Path(resolved).absolute())

def native_c_compiler():
    candidates = [os.environ["CC"]] if os.environ.get("CC") else ["cc", "gcc"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved: return str(Path(resolved).absolute())
    raise LabError("A native C compiler is required for visual reference tests; set CC.")

def invoke(command, log=None, timeout=120, env=None):
    try:
        p = subprocess.run([str(x) for x in command], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, timeout=timeout, env=env)
        output, rc = p.stdout, p.returncode
    except subprocess.TimeoutExpired as e:
        output = e.stdout or b""
        if isinstance(output, bytes): output = output.decode(errors="replace")
        output += f"\nHOST WALL-TIME LIMIT: {timeout}s\n"
        rc = 124
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(output)
    return rc, output

def require(command, log=None, timeout=120, env=None):
    rc, output = invoke(command, log, timeout, env)
    if rc:
        raise LabError(f"Command failed ({rc}). " + (f"See {log}\n" if log else "") + output[-3000:])
    return output

def version(path):
    rc, output = invoke([path, "--version"], timeout=15)
    if rc: output = invoke([path, "--help"], timeout=15)[1]
    return output.splitlines()[0] if output.splitlines() else "unknown"

def source_files(args):
    if not args.source and args.app in VISUAL_EXAMPLES:
        base = ROOT / "examples/visual_suite"
        return args.app, [base / name for name in ("main.c", "image_kernels.c", "render.c")], [
            "-I", str(args._visual["directory"]), "-I", str(base)]
    if not args.source and args.app == "06_camera":
        c = args._camera
        return "06_camera-" + args.camera_mode, [ROOT / "examples/camera/main.c", ROOT / "examples/camera/camera_kernels.c"], [
            "-I", str(c["directory"]), "-I", str(ROOT / "examples/camera"), f"-DCAMERA_OPERATION={c['operation']}"]
    if args.source:
        sources = [Path(p).resolve() for p in args.source]
        name = "application-" + hashlib.sha256("|".join(map(str, sources)).encode()).hexdigest()[:8]
        return name, sources, []
    if args.app == "coremark":
        base = ROOT / "benchmarks/coremark"
        names = ["entry.c", "core_portme.c"] + [f"upstream/core_{s}.c" for s in ("list_join", "matrix", "state", "util")]
        extra = ["-I", str(base), "-I", str(base / "upstream"),
                 f"-DITERATIONS={args.iterations}", f"-DCOREMARK_VALIDATION={int(args.validation)}"]
        return "coremark" + ("-validation" if args.validation else "") + f"-i{args.iterations}", [base / s for s in names], extra
    for folder in ["examples", "tests"]:
        for suffix in [".c", ".S"]:
            p = ROOT / folder / (args.app + suffix)
            if p.is_file(): return args.app, [p], []
    raise LabError(f"Unknown app {args.app!r}. Use --source your_main.c or one of {', '.join(EXAMPLES + ['06_camera'] + VISUAL_EXAMPLES + ['isa_contract', 'coremark'])}.")

def elf_to_hex(elf, out):
    data = elf.read_bytes()
    if data[:7] != b"\x7fELF\x01\x01\x01": raise LabError("Expected ELF32 little-endian image")
    h = struct.unpack_from("<16sHHIIIIIHHHHHH", data)
    if h[2] != 243: raise LabError("ELF is not RISC-V")
    entries = []
    for i in range(h[10]):
        ptype, offset, va, pa, filesz, memsz, flags, align = struct.unpack_from("<IIIIIIII", data, h[5] + i*h[9])
        if ptype != 1 or memsz == 0: continue
        if not RAM_BASE <= pa or pa + memsz > RAM_BASE + RAM_BYTES or filesz > memsz:
            raise LabError("Loadable ELF segment outside the lab's 1 MiB SRAM")
        if offset + filesz > len(data): raise LabError("Truncated ELF segment")
        if filesz:
            entries.append(f"@{pa-RAM_BASE:08x}\n" + "\n".join(f"{v:02x}" for v in data[offset:offset+filesz]))
    out.write_text("\n".join(entries) + "\n")

def build_application(args):
    # Derive and invalidate the destination before source validation: deleting a
    # formerly working source must not leave its previous PASS verdict/viewer.
    if args.source:
        source_key = "|".join(str(Path(p).resolve()) for p in args.source)
        expected_name = "application-" + hashlib.sha256(source_key.encode()).hexdigest()[:8]
    elif args.app == "coremark":
        expected_name = "coremark" + ("-validation" if args.validation else "") + f"-i{args.iterations}"
    elif args.app == "06_camera":
        expected_name = "06_camera-" + args.camera_mode
    else:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.app): raise LabError("Use --source for a source-file path")
        expected_name = args.app
    out = BUILD / (f"{expected_name}-{args.opt}" + memory_suffix(args))
    out.mkdir(parents=True, exist_ok=True)
    if (args.app == "06_camera" or args.app in VISUAL_EXAMPLES) and getattr(args, "image", None):
        try: Path(args.image).resolve().relative_to(out.resolve())
        except ValueError: pass
        else:
            raise LabError("Copy the selected image outside this run's generated output directory before using it as input")
    for stale in ["result.json", "sw.json", "hw.json", "compare.json", "hw.metrics.json",
                  "sw.signature", "hw.signature", "trace.jsonl", "trace.html", "wave.fst", "microarchitecture.svg",
                  "report.html", "performance.json", "hw.csr.txt", "commits.jsonl", "commits.csv", "registration.json",
                  "sw.output.rgb", "hw.output.rgb", "sw.output.png", "hw.output.png"]:
        (out / stale).unlink(missing_ok=True)
    if (BUILD / "results.html").is_file():
        from performance import refresh_index
        refresh_index(BUILD)
    if (BUILD / "catalog.json").is_file(): refresh_gallery()
    if args.app == "06_camera" and not args.source:
        from camera_support import prepare
        args._camera = prepare(args, out)
    if args.app in VISUAL_EXAMPLES and not args.source:
        from visual_support import prepare
        args._visual = prepare(args, out)
    name, sources, extra = source_files(args)
    for path in sources:
        if not path.is_file(): raise LabError(f"Source does not exist: {path}")
    cc = tool("riscv32-unknown-elf-gcc")
    csr = getattr(args, "csr_counters", False) or (args.app == "10_performance" and not args.source)
    isa = "rv32im_zicsr_zicntr" if csr else "rv32im"
    runtime = [ROOT / "runtime/start.S", ROOT / "runtime/runtime.c"]
    if csr: runtime.append(ROOT / "runtime/perf.c")
    flags = [f"-march={isa}", "-mabi=ilp32", f"-{args.opt}", "-g", "-std=gnu11",
             "-ffreestanding", "-fno-builtin", "-fno-tree-loop-distribute-patterns",
             "-fno-pic", "-fno-pie", "-mno-relax", "-msmall-data-limit=0", "-nostdlib",
             "-I", str(ROOT / "runtime"), "-Wl,--no-relax", "-Wl,--build-id=none",
             "-T", str(ROOT / "runtime/link.ld"), "-Wl,-Map," + str(out / "program.map")]
    command = [cc, *flags, *extra, *runtime, *sources, "-o", out / "program.elf"]
    require(command, out / "build.log")
    symbols = {}
    for line in require([tool("riscv32-unknown-elf-nm"), "-n", out / "program.elf"]).splitlines():
        parts = line.split()
        if len(parts) == 3:
            try: symbols[parts[2]] = int(parts[0], 16)
            except ValueError: pass
    for symbol in ["main", "tohost", "begin_signature", "end_signature", "lab_roi_begin_marker", "lab_roi_end_marker"]:
        if symbol not in symbols: raise LabError(f"Missing runtime symbol: {symbol}")
    (out / "program.dis").write_text(require([tool("riscv32-unknown-elf-objdump"), "-d", "-S", "-M", "no-aliases", out / "program.elf"]))
    elf_to_hex(out / "program.elf", out / "program.hex")
    if csr:
        address = symbols.get("lab_perf_record")
        if address is None or address % 16 or not RAM_BASE <= address <= RAM_BASE + RAM_BYTES - 64:
            raise LabError("CSR telemetry record must be 16 aligned words in SRAM")
        if address < symbols["end_signature"] and address + 64 > symbols["begin_signature"]:
            raise LabError("CSR telemetry must be outside the functional signature")
    manifest = {"schema_version": 1, "application": name, "isa": isa, "abi": "ilp32",
                "optimization": args.opt, "compiler": version(cc), "command": list(map(str, command)),
                "sources": {source_label(p): digest(p) for p in sources},
                "runtime": {source_label(p): digest(p) for p in runtime + sorted((ROOT / "runtime").glob("*.h")) + [ROOT / "runtime/link.ld"]},
                "csr_counters_enabled": csr,
                "elf_sha256": digest(out / "program.elf"), "symbols": symbols,
                "rtl_memory": memory_configuration(args)}
    if args.app == "06_camera" and not args.source:
        manifest["camera"] = {k: args._camera[k] for k in ("width", "height", "mode", "operation", "input_sha256", "input_name")}
        manifest["camera"]["input_header_sha256"] = digest(out / "camera_input.h")
    if args.app in VISUAL_EXAMPLES and not args.source:
        manifest["visual"] = {k: v for k, v in args._visual.items() if k != "directory"}
        manifest["visual"]["input_header_sha256"] = digest(out / "visual_input.h")
    save_json(out / "build.json", manifest)
    return out, manifest

def build_hardware(args):
    rtl = Path(args.rtl_dir).resolve() if args.rtl_dir else ROOT / "rtl"
    filelist = rtl / "filelist.f"
    if not filelist.is_file(): raise LabError(f"Missing {filelist}; see RTL replacement contract")
    files = [rtl / line.strip() for line in filelist.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]
    files += [ROOT / "tb/teaching_sram.sv", ROOT / "tb/tb_cpu_lab.sv", ROOT / "tb/sim_main.cpp"]
    verilator = tool("verilator")
    # GNU make honors CXX. Prefer the locally installed modern compiler if the
    # environment has not chosen one; other machines simply use PATH's g++.
    cxx = cxx_compiler()
    dependencies = files + [filelist] + sorted(p for p in rtl.rglob("*") if p.suffix in (".svh", ".vh"))
    identity = {"verilator": version(verilator), "verilator_path": verilator, "cxx": version(cxx), "cxx_path": cxx,
                "files": {str(p): digest(p) for p in dependencies}, "flags": "memory-v1 --assert --trace-fst"}
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out = BUILD / "verilator" / key
    binary = out / "Vtb_cpu_lab"
    if not binary.exists():
        out.mkdir(parents=True, exist_ok=True)
        command = [verilator, "--cc", "--exe", "--build", "-j", str(min(4, os.cpu_count() or 1)), "--assert", "--trace-fst",
                   "--top-module", "tb_cpu_lab", "--Mdir", out, "-MAKEFLAGS", f"CXX={cxx}", *files]
        build_env = os.environ.copy()
        # The outer lab Makefile's APP/OPT selections must not override the
        # separate Makefile generated by Verilator for its C++ simulator.
        for name in ('MAKEFLAGS', 'MFLAGS', 'MAKEOVERRIDES', 'OPT'):
            build_env.pop(name, None)
        build_env.setdefault("CCACHE_DIR", str(BUILD / "ccache"))
        require(command, out / "build.log", timeout=600, env=build_env)
        save_json(out / "build.json", identity)
    return binary, key

def read_signature(path, expected_words=664):
    if not path.exists(): raise LabError("No signature dump: application did not complete")
    try: words = [int(x, 16) for x in path.read_text().split()]
    except ValueError as e: raise LabError("Malformed signature dump") from e
    if len(words) != expected_words or len(words) < 664 or words[0:2] != [0x4350554c, 1]: raise LabError("Invalid runtime signature header or length")
    count, failures, status, mask, length, flags = words[2:8]
    if count > 128 or mask > 0xffff or length > 1024: raise LabError("Corrupted runtime signature bounds")
    if not flags & 0x80000000: raise LabError("Application did not reach lab_finish (incomplete signature)")
    checks = [{"id": words[24+i*3], "actual": words[25+i*3], "expected": words[26+i*3]} for i in range(count)]
    actual_failures = sum(c["actual"] != c["expected"] for c in checks)
    if failures != actual_failures: raise LabError("Target failure count disagrees with host's independent check")
    console = b"".join(struct.pack("<I", w) for w in words[408:664])[:length].decode("utf-8", errors="replace")
    return {"check_count": count, "failure_count": failures, "exit_code": status, "checks": checks,
            "results": {str(i): words[8+i] for i in range(16) if mask & (1 << i)},
            "console": console, "console_truncated": bool(flags & 1)}, words

def run_backend(args, backend, out, manifest, hardware=None):
    dump, raw, log = out / f"{backend}.signature", out / "hw.metrics.json", out / f"{backend}.log"
    for p in [dump, out / f"{backend}.json"]: p.unlink(missing_ok=True)
    metrics, symbols = {}, manifest["symbols"]
    if backend == "sw":
        spike = tool("spike")
        # Some Spike versions return success at --instructions exhaustion.
        # Use a host wall-time watchdog and explicit runtime completion instead.
        command = [spike, "--isa=" + manifest["isa"], "--priv=m", "-m0x80000000:0x100000",
                   f"+signature={dump}", "+signature-granularity=4", out / "program.elf"]
        metrics["simulator"] = version(spike)
    else:
        binary, key = hardware or build_hardware(args)
        raw.unlink(missing_ok=True)
        command = [binary, f"+program={out / 'program.hex'}", f"+tohost={symbols['tohost']:x}",
                   f"+signature_begin={symbols['begin_signature']:x}", f"+signature_end={symbols['end_signature']:x}",
                   f"+dump_file={dump}", f"+result_file={raw}", f"+timeout={args.max_cycles}",
                   f"+roi_begin_addr={symbols['lab_roi_begin_marker']:x}", f"+roi_end_addr={symbols['lab_roi_end_marker']:x}"]
        command += [f"+{key}={value}" for key, value in memory_configuration(args).items()]
        metrics["rtl_build"] = key
        metrics["memory_configuration"] = memory_configuration(args)
        if getattr(args, "commit_log", False): command += [f"+commit_file={out / 'commits.jsonl'}"]
        if manifest.get("csr_counters_enabled"):
            command += [f"+perf_addr={symbols['lab_perf_record']:x}", f"+perf_file={out / 'hw.csr.txt'}"]
        # Trace outputs are invalidated on every hardware run, including untraced runs.
        for p in [out / "trace.jsonl", out / "trace.html", out / "wave.fst"]: p.unlink(missing_ok=True)
        if args.trace:
            command += [f"+trace_file={out / 'trace.jsonl'}", f"+trace_limit={args.trace_limit}"]
            start_symbol = getattr(args, "trace_symbol", None)
            if not start_symbol and "camera" in manifest:
                start_symbol = {"copy": "camera_copy", "grayscale": "camera_grayscale", "sobel": "camera_sobel_pixels", "pipeline": "camera_grayscale"}[manifest["camera"]["mode"]]
            if not start_symbol and "visual" in manifest:
                start_symbol = manifest["visual"]["trace_symbol"]
            if not args.trace_startup:
                start_symbol = start_symbol or "main"
                if start_symbol not in symbols: raise LabError(f"Trace start symbol not present: {start_symbol}")
                command += [f"+trace_start_pc={symbols[start_symbol]:x}"]
        if args.wave: command += [f"+wave={out / 'wave.fst'}"]
    started = time.monotonic()
    rc, _ = invoke(command, log, args.wall_seconds)
    record = {"schema_version": 1, "backend": backend, "status": "fail", "elf_sha256": manifest["elf_sha256"],
              "process_returncode": rc, "host_seconds": round(time.monotonic()-started, 3), "command": list(map(str, command))}
    record.update(metrics)
    if backend == "hw" and raw.exists():
        record["metrics"] = json.loads(raw.read_text())
    if rc == 124: record["error"] = "Host wall-time limit reached"
    words = None
    try:
        signature, words = read_signature(dump, (symbols['end_signature']-symbols['begin_signature'])//4)
        record.update(signature)
        if rc == 0 and signature["exit_code"] == 0 and signature["failure_count"] == 0:
            if backend == "sw" or record.get("metrics", {}).get("status") == "pass": record["status"] = "pass"
    except LabError as e:
        record["error"] = (record["error"] + "; " if record.get("error") else "") + str(e)
    if ("camera" in manifest or "visual" in manifest) and words is not None:
        if "visual" in manifest:
            from visual_support import verify_output
        else:
            from camera_support import verify_output
        check = verify_output(words, manifest, out, backend)
        record["image_check"] = check
        if not check["passed"]:
            record["status"] = "fail"
            record["error"] = "Image output failed the independent host reference"
    if ("camera" in manifest or "visual" in manifest) and backend == "hw":
        m = record.get("metrics", {})
        if not m.get("roi_complete") or m.get("roi_cycles", 0) <= 0:
            record["status"] = "fail"
            record["error"] = "Image-processing run did not complete its measured region"
    if args.app == "coremark" and backend == "hw" and record.get("metrics", {}).get("roi_complete"):
        cycles = record["metrics"]["roi_cycles"]
        record["workload_measurement"] = {"iterations": args.iterations, "roi_cycles_per_iteration": cycles / args.iterations,
                                          "official_coremark_score": False, "boundary": "retired begin-store to retired end-store"}
    if backend == "hw":
        from performance import read_csr, retirement_summary
        try:
            if manifest.get("csr_counters_enabled"):
                record["csr_counters"] = read_csr(out / "hw.csr.txt")
            if getattr(args, "commit_log", False) and (out / "commits.jsonl").is_file():
                record["instruction_log"] = retirement_summary(out / "commits.jsonl", record.get("metrics", {}),
                                                               out / "program.dis", out / "commits.csv")
        except (OSError, ValueError) as error:
            record["status"] = "fail"
            record["telemetry_error"] = str(error)
    save_json(out / f"{backend}.json", record)
    print(f"{backend.upper():2} {record['status'].upper():4} {manifest['application']} ({record.get('check_count', 0)} checks)")
    if record.get("console"): print(record["console"], end="" if record["console"].endswith("\n") else "\n")
    if record.get("console_truncated"): print("[buffered console truncated at 1024 bytes]")
    if record.get("error"): print(record["error"])
    if backend == "hw" and "metrics" in record:
        m = record["metrics"]
        print(f"  cycles={m['cycles']}, retired={m['retired']}, ROI cycles={m['roi_cycles']}")
    if "image_check" in record:
        print(f"  image bytes checked={record['image_check']['bytes_compared']}, mismatches={record['image_check']['mismatched_bytes']}")
    if backend == "hw" and args.trace and (out / "trace.jsonl").exists() and (out / "trace.jsonl").stat().st_size:
        from viewer.render import generate
        generate(out / "trace.jsonl", out / "program.dis", out / "trace.html",
                 metadata={**record.get("metrics", {}), "application": manifest["application"], "elf_sha256": manifest["elf_sha256"],
                           "start_symbol": start_symbol or "main",
                           "status": record["status"], "trace_limit": args.trace_limit})
        print(f"  Cycle viewer: {out / 'trace.html'}")
    return record, words

def run(args, hardware=None):
    out, manifest = build_application(args)
    backends = ["sw", "hw"] if args.backend == "both" else [args.backend]
    records, signatures = {}, {}
    for backend in backends:
        records[backend], signatures[backend] = run_backend(args, backend, out, manifest, hardware)
    ok = all(r["status"] == "pass" for r in records.values())
    summary = {"application": manifest["application"], "elf_sha256": manifest["elf_sha256"],
               "backends": {k: v["status"] for k, v in records.items()}}
    if args.backend == "both":
        equal = signatures["sw"] is not None and signatures["sw"] == signatures["hw"]
        ok &= equal
        summary["signature_match"] = equal
        print(f"COMPARE {'PASS' if ok else 'FAIL'}: complete memory signatures {'match' if equal else 'do not match'}")
    summary["status"] = "pass" if ok else "fail"
    save_json(out / "result.json", summary)
    from performance import generate, print_measurements
    performance = generate(out, manifest, records, summary, getattr(args, "clock_mhz", None))
    print_measurements(performance)
    print(f"  Output and performance: {out / 'report.html'}")
    if (out / "trace.html").is_file() or (BUILD / "catalog.json").is_file(): refresh_gallery()
    print(f"  Results: {out}")
    return ok, out, summary

def register(args, hardware=None):
    """Run a student's program and publish only its verified, recorded trace."""
    from applications import validate_request, publish
    validate_request(args, BUILD)
    case = argparse.Namespace(**vars(args))
    case.backend = "both"
    case.trace = True
    case.commit_log = True
    ok, out, _ = run(case, hardware)
    if not ok:
        print("Registration withheld: fix the failed run, then repeat the register command.")
        return False
    receipt = publish(case, out)
    gallery_path = refresh_gallery()
    print(f"REGISTERED: {receipt['title']} · My applications")
    print(f"  Gallery: {gallery_path}")
    print(f"  Registration receipt: {out / 'registration.json'}")
    return True

def regression(args):
    previous = BUILD / "regression.json"
    if previous.is_file():
        archive = BUILD / "regression-history" / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + ".json")
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(previous, archive)
    previous.unlink(missing_ok=True)
    hardware = build_hardware(args)
    records = []
    def case_args(**overrides):
        values = dict(vars(args), source=None, backend="both", trace=False,
                      memory_profile="fast", **{key: None for key in MEMORY_PROFILES["fast"]})
        values.update(overrides)
        return argparse.Namespace(**values)
    def positive(case):
        ok, out, _ = run(case, hardware)
        records.append(regression_case(out, out.name, "pass", ok))
        save_json(BUILD / "regression.json", {"status": "running", "cases": records})
    for opt in ["O0", "O2"]:
        for app in EXAMPLES + ["isa_contract"]:
            positive(case_args(app=app, opt=opt))
    for validation in [False, True]:
        positive(case_args(app="coremark", opt="O2", validation=validation))
    for app in ["return_nonzero", "check_failure", "hang"]:
        case = case_args(app=app, opt="O2")
        if app == "hang": case.max_cycles = 30000; case.wall_seconds = 2
        ok, out, summary = run(case, hardware)
        # Both backends must fail for the right class of reason, not merely disagree.
        sw = json.loads((out / "sw.json").read_text()); hw = json.loads((out / "hw.json").read_text())
        expected = not ok and sw["status"] == hw["status"] == "fail"
        if app == "hang": expected &= hw.get("metrics", {}).get("reason") == "cycle_budget" and sw["process_returncode"] != 0
        elif app == "return_nonzero": expected &= sw.get("exit_code") == hw.get("exit_code") == 7
        else: expected &= sw.get("failure_count") == hw.get("failure_count") == 1
        records.append(regression_case(out, app, "fail", bool(expected)))
    protocol = None
    if getattr(args, "suite", "full") == "full":
        # Functional behavior must survive changes to BOTH ports' service timing.
        # Different initiation intervals are deliberate even with a blocking CPU:
        # the standalone protocol tests exercise response backpressure separately.
        for profile in ["latency2", "latency3", "stress"]:
            for app in EXAMPLES + ["isa_contract"]:
                positive(case_args(app=app, opt="O2", memory_profile=profile))
        for i_latency, d_latency in [(1, 5), (5, 1)]:
            for app in ["02_memory", "03_control"]:
                positive(case_args(app=app, opt="O2", i_latency=i_latency, d_latency=d_latency))
        for validation in [False, True]:
            positive(case_args(app="coremark", opt="O2", validation=validation, memory_profile="stress"))
        for mode in ["copy", "grayscale", "sobel", "pipeline"]:
            positive(case_args(app="06_camera", opt="O2", memory_profile="stress",
                               camera_mode=mode, width=7, height=5, image=None))
        for app in ["isa_contract", "03_control"]:
            positive(case_args(app=app, opt="O2", memory_profile="stress", stall_seed=2026))
        protocol_path = BUILD / "memory_protocol.json"
        protocol_path.unlink(missing_ok=True)
        protocol_command = [sys.executable, ROOT / "tests/memory_protocol.py", "--output", protocol_path]
        if args.rtl_dir: protocol_command += ["--rtl-dir", args.rtl_dir]
        rc, output = invoke(protocol_command,
                            BUILD / "memory_protocol.log", timeout=600)
        if protocol_path.exists(): protocol = json.loads(protocol_path.read_text())
        else: protocol = {"status": "fail", "error": output[-3000:]}
        if rc: protocol["status"] = "fail"
    passed = all(r["passed"] for r in records) and (protocol is None or protocol.get("status") == "pass")
    report = {"schema_version": 2, "status": "pass" if passed else "fail",
              "suite": getattr(args, "suite", "full"), "rtl_build": hardware[1],
              "verified_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "memory_profiles": MEMORY_PROFILES, "cases": records, "protocol": protocol}
    save_json(BUILD / "regression.json", report)
    print(f"REGRESSION {report['status'].upper()}: {sum(r['passed'] for r in records)}/{len(records)} cases")
    if protocol is not None: print(f"MEMORY PROTOCOL {protocol['status'].upper()}")
    return report["status"] == "pass"

def regression_case(out, name, expected, passed):
    # Embed evidence so later interactive runs cannot rewrite this run's report.
    return {"case": name, "expected": expected, "passed": bool(passed),
            "result": json.loads((out / "result.json").read_text()),
            "sw": json.loads((out / "sw.json").read_text()),
            "hw": json.loads((out / "hw.json").read_text())}

def refresh_gallery():
    """Refresh grouped, portable navigation from completed recorded runs."""
    from viewer.catalog import refresh
    return refresh(BUILD)


def gallery(args):
    for app in EXAMPLES:
        case = argparse.Namespace(**vars(args)); case.app = app; case.source = None
        case.backend = "hw"; case.trace = True; case.opt = "O2"; case.trace_symbol = None
        if not run(case)[0]: return False
    case = argparse.Namespace(**vars(args)); case.app = "02_memory"; case.source = None
    case.backend = "hw"; case.trace = True; case.opt = "O2"; case.trace_symbol = None
    case.memory_profile = "stress"
    for key in MEMORY_PROFILES["fast"]: setattr(case, key, None)
    if not run(case)[0]: return False
    refresh_gallery()
    print("Open the rendered gallery with: make serve")
    return True

def camera_suite(args):
    from camera_support import load_input, frame_record, png_bytes
    from viewer.render import generate_camera_report
    if args.source: raise LabError("Use --input for a camera frame; --source is for a custom application")
    directory = BUILD / "camera"
    directory.mkdir(parents=True, exist_ok=True)
    if args.image:
        try: Path(args.image).resolve().relative_to(directory.resolve())
        except ValueError: pass
        else: raise LabError("Copy the selected image outside build/camera before using it as input; that directory is generated output")
    for name in ("report.html", "report.json", "input.png", "input.ppm", "copy.png", "grayscale.png", "sobel.png", "pipeline.png", "trace.html", "microarchitecture.svg", "comparison.png",
                 "copy-trace.html", "grayscale-trace.html", "sobel-trace.html", "pipeline-trace.html"):
        (directory / name).unlink(missing_ok=True)
    report = {"schema_version": 1, "status": "fail", "backend": "Spike + Verilator RTL", "modes": {}}
    save_json(directory / "report.json", report)
    refresh_gallery()
    width, height, rgb, name = load_input(args.image, args.width, args.height)
    # Freeze one input for all four ELF builds, including a user-supplied image.
    (directory / "input.ppm").write_bytes(f"P6\n{width} {height}\n255\n".encode() + rgb)
    input_png = png_bytes(width, height, rgb)
    (directory / "input.png").write_bytes(input_png)
    report.update({"width": width, "height": height, "input_name": name, "input_sha256": hashlib.sha256(rgb).hexdigest(),
                   "measurement_boundary": "begin marker-store retirement excluded; end marker-store retirement included",
                   "physical_realtime_claim": False})
    frames = [frame_record("input", "Input RGB", input_png, width, height)]
    titles = {"copy": "RGB copy", "grayscale": "Grayscale", "sobel": "Sobel only", "pipeline": "RGB to edges"}
    hardware = build_hardware(args)
    for mode in titles:
        case = argparse.Namespace(**vars(args)); case.app = "06_camera"; case.source = None
        case.backend = "both"; case.camera_mode = mode; case.image = str(directory / "input.ppm")
        case.width = None; case.height = None; case.trace = args.trace
        ok, out, summary = run(case, hardware)
        sw = json.loads((out / "sw.json").read_text()); hw = json.loads((out / "hw.json").read_text())
        report["modes"][mode] = {"result": summary, "sw": sw, "hw": hw,
                                  "build": json.loads((out / "build.json").read_text())}
        save_json(directory / "report.json", report)
        if not ok: return False
        output_png = (out / "hw.output.png").read_bytes()
        (directory / f"{mode}.png").write_bytes(output_png)
        explanation = "Grayscale preparation is outside this measured region." if mode == "sobel" else (
            "Both grayscale conversion and Sobel are inside this measured region." if mode == "pipeline" else None)
        frame = frame_record(mode, titles[mode], output_png, width, height, hw["metrics"]["roi_cycles"], explanation)
        frame["full_cycles"] = hw["metrics"]["cycles"]
        frame["roi_start_cycle"] = hw["metrics"].get("roi_start_cycle")
        frame["roi_end_cycle"] = hw["metrics"].get("roi_end_cycle")
        frames.append(frame)
        if case.trace:
            shutil.copy2(out / "trace.html", directory / (mode + "-trace.html"))
            shutil.copy2(out / "microarchitecture.svg", directory / "microarchitecture.svg")
            frame["trace_href"] = mode + "-trace.html"
            if mode == "sobel": shutil.copy2(out / "trace.html", directory / "trace.html")
    report["status"] = "pass"
    save_json(directory / "report.json", report)
    metadata = {"application": "Camera image processing", "status": "pass", "backend": "Verilator RTL; checked against Spike and a host reference",
                "width": width, "height": height, "pixels_processed": width * height, "input_name": name,
                "gallery_href": "../index.html"}
    if (directory / "trace.html").exists(): metadata["trace_href"] = "trace.html"
    generate_camera_report(metadata, frames, directory / "report.html")
    refresh_gallery()
    print(f"CAMERA PASS: all four operations, {width}x{height}, every RGB output byte checked on both backends")
    print("Open in a browser with make serve, then /camera/report.html")
    return True

def serve(args):
    """Serve generated reports on loopback only, so HTML renders as a web page."""
    refresh_gallery()
    handler = partial(SimpleHTTPRequestHandler, directory=str(BUILD))
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"CPU lab browser: http://127.0.0.1:{args.port}/", flush=True)
        print("HTML links opened in a source editor will show code. Open this URL in a browser.", flush=True)
        print("Remote host: forward this port with SSH, or download the offline reports. Ctrl-C stops the server.", flush=True)
        try: server.serve_forever()
        except KeyboardInterrupt: pass

def visual_suite(args):
    """Run the portable image kernels on both backends with recorded RTL cycles."""
    if args.source: raise LabError("Use --input for an image; --source is for a custom application")
    hardware = build_hardware(args)
    report = {"status": "running", "applications": {}}
    save_json(BUILD / "visual-suite.json", report)
    for app in VISUAL_EXAMPLES:
        case = argparse.Namespace(**vars(args))
        case.app = app; case.backend = "both"; case.source = None; case.trace = True
        ok, out, summary = run(case, hardware)
        report["applications"][app] = {"result": summary,
            "sw": json.loads((out / "sw.json").read_text()),
            "hw": json.loads((out / "hw.json").read_text())}
        if not ok:
            report["status"] = "fail"
            save_json(BUILD / "visual-suite.json", report)
            return False
        save_json(BUILD / "visual-suite.json", report)
    report["status"] = "pass"
    save_json(BUILD / "visual-suite.json", report)
    refresh_gallery()
    print("VISUAL PASS: three integer applications; Spike/RTL signatures and host pixel references match")
    return True

def export_bundle():
    BUILD.mkdir(parents=True, exist_ok=True)
    target = BUILD / "cpu_lab.zip"
    manifest = {}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file(): continue
            if BUILD in path.parents: continue
            rel = path.relative_to(ROOT)
            if rel == Path("bundle_manifest.json"): continue
            if any(part in ("build", "__pycache__", ".git") for part in rel.parts) or path.suffix == ".pyc": continue
            archive.write(path, str(Path("cpu_lab") / rel)); manifest[str(rel)] = digest(path)
        archive.writestr("cpu_lab/bundle_manifest.json", json.dumps(manifest, indent=2) + "\n")
    print(target)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "register", "course", "build", "test", "doctor", "export", "export-views", "camera", "visual", "gallery", "serve"])
    parser.add_argument("--backend", choices=["sw", "hw", "both"], default="both")
    parser.add_argument("--suite", choices=["smoke", "full"], default="full", help="Regression: original application suite, or applications plus memory stress/protocol tests")
    parser.add_argument("--memory-profile", choices=list(MEMORY_PROFILES), default="fast")
    for key in MEMORY_PROFILES["fast"]:
        parser.add_argument("--" + key.replace("_", "-"), type=int, help="Override this RTL memory timing parameter; independent of Spike")
    parser.add_argument("--app", default="01_arithmetic")
    parser.add_argument("--source", action="append", help="Application C or assembly file; repeat for multiple files")
    parser.add_argument("--name", help="Stable student application name for register (lowercase letters, digits, hyphens, underscores)")
    parser.add_argument("--title", help="Human-readable gallery title for register")
    parser.add_argument("--description", help="Short gallery description for register")
    parser.add_argument("--opt", choices=["O0", "O1", "O2", "O3", "Os"], default="O2")
    parser.add_argument("--rtl-dir", default=os.environ.get("LAB_RTL_DIR"), help="Alternative CPU source directory with the same filelist/top/trace contract (default: LAB_RTL_DIR or bundled rtl)")
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--csr-counters", action="store_true", help="Enable optional Zicsr/Zicntr software cycle/instret telemetry, separate from functional results")
    parser.add_argument("--commit-log", action="store_true", help="Record every RTL retirement as JSONL and decoded CSV, independently of the cycle-trace cap")
    parser.add_argument("--clock-mhz", type=float, help="Assumed target clock in MHz, only for estimated execution time")
    parser.add_argument("--trace-startup", action="store_true", help="Include startup instead of beginning at main")
    parser.add_argument("--trace-symbol", help="Begin capture at this ELF function/symbol; does not change ROI timing")
    parser.add_argument("--trace-limit", type=int, default=20000)
    parser.add_argument("--wave", action="store_true")
    parser.add_argument("--max-cycles", type=int, default=20000000)
    parser.add_argument("--wall-seconds", type=int, default=120)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--validation", action="store_true")
    parser.add_argument("--camera-mode", choices=["copy", "grayscale", "sobel", "pipeline"], default="pipeline")
    parser.add_argument("--input", dest="image", help="Input image: P6 PPM, or PNG/JPEG with Pillow installed")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--frame", type=int, default=0, help="Integer ball animation frame to render and trace")
    parser.add_argument("--noise-seed", type=int, default=1, help="Deterministic impulse-noise seed")
    parser.add_argument("--port", type=int, default=8770)
    args = parser.parse_args()
    if args.clock_mhz is not None and (not math.isfinite(args.clock_mhz) or args.clock_mhz <= 0):
        parser.error("--clock-mhz must be finite and positive")
    for name in ["trace_limit", "max_cycles", "wall_seconds", "iterations"]:
        if getattr(args, name) <= 0: parser.error(f"--{name.replace('_', '-')} must be positive")
    if not 1 <= args.port <= 65535: parser.error("--port must be 1..65535")
    try:
        if args.command == "doctor":
            print(f"Build directory: {BUILD}")
            print(f"RTL directory: {Path(args.rtl_dir).resolve() if args.rtl_dir else ROOT / 'rtl'}")
            print(f"Python: {sys.executable}\n  {sys.version.splitlines()[0]}")
            for name in ["make", "riscv32-unknown-elf-gcc", "riscv32-unknown-elf-objdump", "riscv32-unknown-elf-nm", "riscv32-unknown-elf-objcopy", "spike", "verilator"]:
                p = tool(name); print(f"{name}: {p}\n  {version(p)}")
            for name, p in [("C++ compiler", cxx_compiler()), ("Native C compiler", native_c_compiler())]:
                print(f"{name}: {p}\n  {version(p)}")
        elif args.command == "export": export_bundle()
        elif args.command == "register": return 0 if register(args) else 1
        elif args.command == "course":
            from course import generate
            print(generate(ROOT, BUILD)['html'])
        elif args.command == "export-views":
            from viewer.catalog import export_reports
            print(export_reports(BUILD))
        elif args.command == "camera": return 0 if camera_suite(args) else 1
        elif args.command == "visual": return 0 if visual_suite(args) else 1
        elif args.command == "gallery": return 0 if gallery(args) else 1
        elif args.command == "serve": serve(args)
        elif args.command == "build": print(build_application(args)[0])
        elif args.command == "test": return 0 if regression(args) else 1
        else: return 0 if run(args)[0] else 1
        return 0
    except (LabError, OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr); return 1

if __name__ == "__main__":
    sys.exit(main())
