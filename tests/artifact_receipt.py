# =============================================================================
# HY-RV | artifact_receipt
# Description: Preserve source-bound software and simulation evidence from temporary tests.
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See applicable manifests and verification records for provenance.
# Preserve existing license, copyright, and original author notices.
# =============================================================================
"""Small receipts survive cleanup without storing large traces in the repository."""
import hashlib
import json


def capture(directory):
    result = {"json": {}, "files_sha256": {}}
    for name in ("build.json", "result.json", "hw.json", "sw.json", "performance.json"):
        path = directory / name
        if path.is_file():
            result["json"][name] = json.loads(path.read_text())
    for name in ("program.elf", "program.hex", "program.dis", "build.json", "result.json",
                 "hw.json", "sw.json", "performance.json", "hw.signature", "sw.signature",
                 "hw.output.rgb", "sw.output.rgb", "input.rgb", "input.ppm", "hw.csr.txt",
                 "commits.jsonl", "commits.csv", "trace.jsonl", "trace.html", "report.html"):
        path = directory / name
        if path.is_file():
            result["files_sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result
