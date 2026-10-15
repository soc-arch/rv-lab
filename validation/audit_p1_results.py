#!/usr/bin/env python3
# =============================================================================
# HY-RV | audit_p1_results
# Description: Audit compiled presets and publish compact, reproducible laboratory receipts.
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See applicable manifests and verification records for provenance.
# Preserve existing license, copyright, and original author notices.
# =============================================================================
"""Keep real measurements distinct from historical teaching CPU examples."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core_config
import verify
from validation.run_p1_validation import source_identity, display_path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", type=Path, default=ROOT / "build/validation-p1")
    args = parser.parse_args()
    base = args.build_root.resolve()
    run = read(base / "all-receipt.json")
    assert run["status"] == "pass" and not run["source_drift"]
    assert source_identity() == read(base / "all-source-after.json"), "Executable sources changed after the functional run"
    pin = read(ROOT / "provenance/p1-static-core.json")
    assert core_config.rtl_identity(ROOT / "rtl") == pin["rtl_files_sha256"]
    assert core_config.source_hash(ROOT / "rtl") == pin["source_hash"]
    summary = {"schema_version": 2, "status": "pass", "scope": "Functional and student workflow verification; synthesis/Formality evidence is separate.",
               "verified_at_utc": datetime.now(timezone.utc).isoformat(), "source_hash": pin["source_hash"],
               "default_preset": "ant_j0", "memory_adapter": "ii1", "source_drift": False,
               "presets": {}, "lessons": {}, "unit_groups": run["unit"], "tools": verify.tool_provenance()}
    summary["runtime_source_snapshot"] = {"files": len(read(base / "all-source-after.json")),
                                           "sha256": digest(base / "all-source-after.json")}
    summary["reproduce"] = {"build_root": display_path(base),
        "commands": [f"python3 validation/run_p1_validation.py --phase all --build-root {display_path(base)} --workers 2",
                     f"python3 validation/audit_p1_results.py --build-root {display_path(base)}"]}
    log_audit = {}
    for preset in core_config.PRESETS:
        source = read(base / preset / "evidence/summary.json")
        assert source["status"] == "pass"
        config = core_config.resolve(preset, "ii1")
        assert source["configuration"] == config
        assert source["configuration_sha256"] == pin["presets"][preset]["preset_config_sha256"]
        regression = read(base / preset / "evidence/full/regression.json")
        negative = [item["case"] for item in regression["cases"] if item["expected"] == "fail"]
        assert len(negative) == 3
        for case in regression["cases"]:
            assert case["passed"]
            assert case["hw"]["elf_sha256"] == case["sw"]["elf_sha256"] == case["result"]["elf_sha256"]
            assert case["hw"]["configuration_sha256"] == source["configuration_sha256"]
            assert case["hw"]["rtl_source_hash"] == summary["source_hash"]
            if case["expected"] == "pass":
                assert case["result"]["signature_match"] and case["result"]["status"] == "pass"
        expected = config["parameters"]
        observed = []
        pattern = r"\[HY-RV-CONFIG\] BP_PROFILE=(\d+) COND_POLICY=(\d+) EARLY_JAL_EN=(\d+) INSN_QUEUE_DEPTH=(\d+)"
        for path in sorted((base / preset).glob("*/hw.log")):
            match = re.search(pattern, path.read_text())
            assert match, f"Missing actual executable configuration: {path}"
            values = dict(zip(("BP_PROFILE", "COND_POLICY", "EARLY_JAL_EN", "INSN_QUEUE_DEPTH"), map(int, match.groups())))
            assert values == expected, (path, values, expected)
            observed.append({"log": str(path.relative_to(base)), "sha256": digest(path), "observed_parameters": values})
        assert len(observed) >= 47
        log_audit[preset] = observed
        summary["presets"][preset] = {"status": "pass", "model_id": config["model_id"],
            "configuration_sha256": source["configuration_sha256"], "effective_parameters": config["effective_parameters"],
            "counts": dict(source["counts"], functional_positive=44, functional_expected_negative=3),
            "expected_negative_cases": negative, "performance_unit_tests": 3, "student_workflow_tests": 2,
            "registration_tests": 2, "actual_executable_configuration_logs": len(observed),
            "hardware_builds": source["hardware_builds"],
            "gates": [{key: value for key, value in gate.items() if key not in ("command", "log")} for gate in source["gates"]]}
    lessons = read(base / "ant_j0/lessons/summary.json")
    assert lessons["status"] == "pass" and lessons["lessons"] == 8
    summary["lessons"] = {"status": "pass", "preset": "ant_j0", "lesson_count": 8,
                          "commands": len(lessons["records"]), "export_integrity": lessons["export_integrity"],
                          "export_sha256": lessons["export_sha256"]}
    save(base / "actual-configuration-audit.json", log_audit)
    browser_report = base / "browser-muldiv/browser-check.json"
    extra_evidence = []
    if browser_report.is_file():
        browser = read(browser_report)
        assert browser["externalRequests"] == 0 and not browser["errors"]
        summary["browser"] = {"status": "pass", **browser, "receipt_sha256": digest(browser_report),
                              "report_sha256_at_audit": digest(Path(browser["report"]))}
        extra_evidence += [browser_report]
        trace = base / "ant_j0/04_muldiv-O2/trace.jsonl"
        overlap, consecutive, longest = [], [], []
        for line in trace.read_text().splitlines():
            row = json.loads(line)
            fetch, commit, port = row["fetch"], row["commit"], row["ports"]["instruction"]
            if (commit["valid"] and fetch["accepted"] and port["req_accepted"]
                    and fetch["pc"] == commit["pc"] + 4 and port["req_addr"] == fetch["pc"] + 4):
                edge = {"cycle": row["cycle"], "commit_pc": commit["pc"],
                        "ir_accept_pc": fetch["pc"], "fetch_request_pc": port["req_addr"]}
                overlap.append(edge)
                consecutive.append(edge)
                if len(consecutive) > len(longest):
                    longest = consecutive[:]
            else:
                consecutive = []
        assert overlap, "The measured P1 trace must show same-edge commit/admission/next request"
        summary["measured_overlap"] = {"status": "pass", "preset": "ant_j0", "example_kind": "measured_rtl_trace",
            "trace_sha256": digest(trace), "qualifying_edges": len(overlap),
            "maximum_consecutive_qualifying_edges": len(longest), "examples": longest[:3]}
        measured = base / "measured-overlap.json"
        save(measured, summary["measured_overlap"])
        extra_evidence.append(measured)
    profiles_report = base / "browser-profiles/receipt.json"
    if profiles_report.is_file():
        profiles = read(profiles_report)
        assert profiles["status"] == "pass" and len(profiles["checks"]) == 6
        summary["viewer_configuration_checks"] = profiles
        extra_evidence.append(profiles_report)
        for path in (base / "profiles-receipt.json", base / "profiles-source-before.json", base / "profiles-source-after.json"):
            if path.is_file():
                extra_evidence.append(path)
        extra_evidence += [p for p in (base / "profile-views").rglob("*") if p.is_file() and p.suffix in (".json", ".log")]
    cases = []
    for record in lessons["records"]:
        directory = base / "ant_j0/lessons" / record["lesson"]
        for application in read(directory / "applications.json"):
            data = application["json"]
            hw, sw = data.get("hw.json", {}), data.get("sw.json", {})
            measurement = data.get("performance.json", {})
            result = data.get("result.json", {})
            cases.append({"case": record["lesson"], "application_directory": application["directory"],
                "expected_outcome_verified": record["status"] == "pass", "expected_command_exit": record["expected_exit_code"],
                "status": result.get("status"), "signature_match": result.get("signature_match"),
                "elf_sha256": data["build.json"]["elf_sha256"], "core_configuration_sha256": hw.get("configuration_sha256"),
                "check_count": hw.get("check_count"), "failure_count": hw.get("failure_count"),
                "checks": hw.get("checks"), "console": hw.get("console"), "metrics": hw.get("metrics"),
                "memory_configuration": hw.get("memory_configuration"), "measurements": measurement.get("measurements"),
                "csr_counters": measurement.get("csr_counters"), "instruction_log": measurement.get("instruction_log"),
                "files_sha256": application["files_sha256"]})
    reference = {"schema_version": 2, "status": "pass", "description": "Actual current P1 ant_j0 RTL measurements from rerunning all eight lessons.",
                 "source_hash": summary["source_hash"], "preset": "ant_j0", "memory_adapter": "ii1",
                 "configuration_sha256": summary["presets"]["ant_j0"]["configuration_sha256"],
                 "historical_reference": "historical/teaching-reference-results.json", "cases": cases,
                 "workflow_commands": lessons["records"], "export": summary["lessons"]}
    save(ROOT / "docs/reference-results.json", reference)
    archive = ROOT / "validation/functional-p1-receipts.zip"
    files = [base / "all-receipt.json", base / "all-source-before.json", base / "all-source-after.json",
             base / "actual-configuration-audit.json"] + extra_evidence
    for preset in core_config.PRESETS:
        files += [p for p in (base / preset / "evidence").rglob("*") if p.is_file() and p.suffix in (".json", ".log")]
    files += [p for p in (base / "ant_j0/lessons").rglob("*") if p.is_file() and p.suffix in (".json", ".log")]
    files += [p for p in (base / "unit").rglob("*") if p.is_file() and p.suffix in (".json", ".log")]
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(set(files)):
            bundle.write(path, str(path.relative_to(base)))
        bundle.writestr("manifest.json", json.dumps({"files_sha256": {str(path.relative_to(base)): digest(path) for path in sorted(set(files))}}, indent=2))
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
    summary["receipts"] = {"path": "validation/functional-p1-receipts.zip", "sha256": digest(archive),
                           "bytes": archive.stat().st_size, "files": len(set(files)),
                           "reference_results_sha256": digest(ROOT / "docs/reference-results.json")}
    save(ROOT / "validation/functional-p1.json", summary)
    save(ROOT / "docs/current-validation.json", summary)
    print(json.dumps({"status": "pass", "presets": {key: value["counts"] for key, value in summary["presets"].items()},
                      "lessons": summary["lessons"], "archive_bytes": archive.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
