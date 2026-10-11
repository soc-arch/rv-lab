#!/usr/bin/env python3
"""Create a standalone HTML report from an actual RTL cycle trace.

No browser, web server, network access, or third-party Python package is needed
to generate or open the result. Import ``generate`` from the lab runner or run
this file with --trace, --disassembly, and --output.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    from .reports import generate_camera_report, generate_gallery, normalize_navigation, normalize_image_result
except ImportError:  # Direct invocation: python3 viewer/render.py
    from reports import generate_camera_report, generate_gallery, normalize_navigation, normalize_image_result


HERE = Path(__file__).resolve().parent
LIMIT = 20_000
MAX_LIMIT = 100_000


def _number(value):
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return int(value, 16)
    return int(value)


def _disassembly(path):
    """Preserve source lines and labels while indexing actual instruction PCs."""
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    entries, symbols = {}, {}
    instruction = re.compile(r"^\s*([0-9a-fA-F]+):\s+((?:(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{4}|[0-9a-fA-F]{2})\s+)+)(\S.*)$")
    label = re.compile(r"^\s*([0-9a-fA-F]+)\s+<([^>]+)>:\s*$")
    for index, line in enumerate(lines):
        if found := label.match(line):
            symbols[found.group(2)] = int(found.group(1), 16)
        if found := instruction.match(line):
            # Both a 32-bit word and byte-separated object dumps are accepted.
            text = found.group(3).strip()
            entries[str(int(found.group(1), 16))] = {
                "text": text,
                "line": index,
                "encoding": "".join(found.group(2).split()),
            }
    return {"lines": lines, "instructions": entries, "symbols": symbols}


def generate(trace_path, disassembly_path, output_path, metadata=None):
    """Render RTL JSONL and objdump -d -S as a self-contained HTML report.

    ``metadata`` may contain title, application, profile, trace_limit,
    start_symbol (default ``main``), start_pc, description, and navigation
    (see reports.normalize_navigation for the embedded example catalog). Values are
    embedded as data, never interpreted as HTML. trace_limit defaults to
    20,000 and can be raised to 100,000. The return value gives artifact paths,
    recorded cycles and retirements, and whether the input was truncated.

    Sample schema and edge convention are documented in README.md. All event
    highlights come from the supplied trace. No timing is invented here.
    """
    trace_path = Path(trace_path)
    disassembly_path = Path(disassembly_path)
    output_path = Path(output_path)
    meta = dict(metadata or {})
    if meta.get("navigation"):
        meta["navigation"] = normalize_navigation(meta["navigation"])
    if meta.get("image_result"):
        meta["image_result"] = normalize_image_result(meta["image_result"])
    limit = min(MAX_LIMIT, max(1, int(meta.get("trace_limit", LIMIT))))
    trace, truncated = [], False
    previous_cycle = None
    with trace_path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            if len(trace) >= limit:
                truncated = True
                break
            try:
                sample = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{trace_path}:{line_number}: invalid JSON: {error}") from error
            for field in ("cycle", "fetch", "execute", "stages", "units", "regs", "memory", "commit", "redirect"):
                if field not in sample:
                    raise ValueError(f"{trace_path}:{line_number}: missing {field}")
            cycle = _number(sample["cycle"])
            if previous_cycle is not None and cycle <= previous_cycle:
                raise ValueError(f"{trace_path}:{line_number}: cycles must be strictly increasing")
            sample["cycle"] = cycle
            previous_cycle = cycle
            trace.append(sample)
    if not trace:
        raise ValueError(f"{trace_path}: no cycle samples; rerun RTL with tracing enabled")

    assembly = _disassembly(disassembly_path)
    capture_truncated = meta.get("trace_truncated") in (True, 1, "1", "true")
    meta.update({"trace_filename": trace_path.name,
                 "disassembly_filename": disassembly_path.name,
                 "truncated": truncated or capture_truncated,
                 "viewer_truncated": truncated,
                 "capture_truncated": capture_truncated, "trace_limit": limit,
                 "sample_convention": "pre-rising-edge"})
    data = {"metadata": meta, "trace": trace, "assembly": assembly}
    # A source string containing </script> must never terminate the data block.
    payload = json.dumps(data, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    diagram = (HERE / "microarchitecture.svg").read_text(encoding="utf-8")
    html = (HERE / "template.html").read_text(encoding="utf-8")
    html = html.replace("<!-- MICROARCHITECTURE -->", diagram)
    html = html.replace("<!-- TRACE_DATA -->", payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    svg_output = output_path.with_name("microarchitecture.svg")
    svg_output.write_text(diagram, encoding="utf-8")
    return {"html": str(output_path), "microarchitecture_svg": str(svg_output),
            "cycles": len(trace), "first_cycle": trace[0]["cycle"],
            "last_cycle": trace[-1]["cycle"],
            "retirements": sum(bool(s["commit"].get("valid")) for s in trace),
            "truncated": truncated or capture_truncated,
            "viewer_truncated": truncated, "capture_truncated": capture_truncated}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", required=True, type=Path)
    parser.add_argument("--disassembly", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title", default="Instruction to hardware")
    args = parser.parse_args()
    print(json.dumps(generate(args.trace, args.disassembly, args.output,
                              {"title": args.title}), indent=2))


if __name__ == "__main__":
    main()
