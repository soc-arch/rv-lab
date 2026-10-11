"""Student result pages and measured performance, independent of CPU internals."""
from collections import Counter
import csv
import hashlib
import html
import json
import math
from pathlib import Path
from urllib.parse import quote


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def read_csr(path):
    """Decode the optional LPM1 sideband; never mask functional signature words."""
    if not path.exists():
        return {"status": "not_recorded", "reason": "No hardware telemetry dump"}
    words = [int(word, 16) for word in path.read_text().split()]
    if len(words) != 16 or any(not 0 <= word <= 0xffffffff for word in words):
        raise ValueError("Invalid CSR telemetry length or word")
    if not any(words):
        return {"status": "not_recorded", "reason": "lab_perf_begin was not called"}
    if words[:3] != [0x4c504d31, 1, 16] or words[3] not in (1, 3):
        raise ValueError("Invalid CSR telemetry header or flags")
    value = lambda index: words[index] | (words[index + 1] << 32)
    record = {"status": "complete" if words[3] == 3 else "incomplete", "schema_version": 1,
              "source": "software reads of mcycle/minstret", "atomic_counter_pair": False,
              "begin_cycle": value(4), "begin_instret": value(6)}
    if words[3] == 3:
        record.update(end_cycle=value(8), end_instret=value(10), cycles=value(12), retired=value(14))
        for name in ("cycle", "instret"):
            delta = (record["end_" + name] - record["begin_" + name]) & ((1 << 64) - 1)
            if delta != record["cycles" if name == "cycle" else "retired"]:
                raise ValueError("CSR telemetry delta disagrees with its endpoints")
    return record


def instruction_class(insn):
    opcode = insn & 127
    if opcode == 0x33 and (insn >> 25) == 1:
        return "divide/remainder" if ((insn >> 12) & 7) >= 4 else "multiply"
    return {0x03: "load", 0x23: "store", 0x63: "branch", 0x6f: "jump", 0x67: "jump",
            0x73: "system/CSR", 0x0f: "fence"}.get(opcode, "integer/other")


def retirement_summary(commit_path, metrics, disassembly_path, output_csv_path):
    """Stream real retirements, cross-check TB totals, and retain decoded history."""
    from viewer.render import _disassembly
    assembly = _disassembly(disassembly_path)["instructions"]
    count = roi_count = previous = 0
    hotspots, roi_hotspots, classes = Counter(), Counter(), Counter()
    roi_valid = bool(metrics.get("roi_complete"))
    start, end = metrics.get("roi_start_cycle", 0), metrics.get("roi_end_cycle", 0)
    with commit_path.open() as source, output_csv_path.open("w", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(["retirement", "cycle", "pc", "instruction", "assembly", "rd", "rd_write", "rd_data", "in_roi"])
        for line in source:
            if not line.strip(): continue
            record = json.loads(line)
            cycle, pc, insn = (record[key] for key in ("cycle", "pc", "insn"))
            if not all(isinstance(x, int) for x in (cycle, pc, insn)) or cycle <= previous:
                raise ValueError("Retirement cycles must increase strictly for this single-retire core")
            if not 0 <= pc <= 0xffffffff or not 0 <= insn <= 0xffffffff:
                raise ValueError("Retirement PC/encoding outside RV32 bounds")
            previous = cycle
            count += 1
            inside = roi_valid and start < cycle <= end
            roi_count += int(inside)
            hotspots[pc] += 1
            if inside: roi_hotspots[pc] += 1
            classes[instruction_class(insn)] += 1
            decoded = assembly.get(str(pc), {})
            text = decoded.get("text", "") if decoded.get("encoding", "").lower() == f"{insn:08x}" else ""
            writer.writerow([count, cycle, f"0x{pc:08x}", f"0x{insn:08x}", text or "encoding not in ELF disassembly",
                             record["rd"], record["rd_we"], f"0x{record['rd_data']:08x}", int(inside)])
    if count != metrics.get("retired") or (roi_valid and roi_count != metrics.get("roi_retired")):
        raise ValueError("Retirement log counts disagree with full-run/ROI testbench counters")
    if previous > metrics.get("cycles", -1):
        raise ValueError("Retirement extends beyond the measured run")
    def top(counter):
        return [{"pc": f"0x{pc:08x}", "retired": n, "assembly": assembly.get(str(pc), {}).get("text", "")}
                for pc, n in counter.most_common(20)]
    return {"status": "complete", "source": "actual RTL retirement events", "retired": count,
            "roi_retired": roi_count if roi_valid else None,
            "count_matches_testbench": True, "instruction_classes": dict(classes),
            "hotspots": top(hotspots), "roi_hotspots": top(roi_hotspots),
            "jsonl": commit_path.name, "csv": output_csv_path.name,
            "jsonl_sha256": file_digest(commit_path)}


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def measurement(cycles, retired, frequency):
    return {"cycles": cycles, "retired": retired,
            "cpi": cycles / retired if retired else None,
            "estimated_seconds": cycles / (frequency * 1e6) if frequency else None}


STYLE = """body{font:16px system-ui,sans-serif;color:#183b4a;background:#f1f6f8;margin:0}
main{max-width:1100px;margin:auto;padding:32px 20px}h1{font-size:32px}h2{font-size:22px}
section{background:white;border:1px solid #d5e2e8;border-radius:12px;padding:20px;margin:20px 0}
a{color:#056b91}table{border-collapse:collapse;width:100%}td,th{padding:10px;text-align:left;border-bottom:1px solid #dde7eb}
.scroll{overflow-x:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#102c3a;color:#e4f3fa;padding:16px;border-radius:6px}
.pass{color:#14744c}.fail{color:#b22e36}.note{color:#516975;font-size:14px}code{overflow-wrap:anywhere}
.links{display:flex;flex-wrap:wrap;gap:18px}footer{font-size:13px;color:#526e79}li{margin:8px 0}
@media(max-width:500px){main{padding:16px 10px}section{padding:12px}h1{font-size:26px}}"""


def esc(value):
    return html.escape(str(value), quote=True)


def table(headers, rows):
    return '<div class="scroll"><table><thead><tr>' + ''.join('<th>' + esc(x) + '</th>' for x in headers) + \
        '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + esc(x) + '</td>' for x in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def display(value, digits=3):
    return "Not recorded" if value is None else (f"{value:,.{digits}f}" if isinstance(value, float) else f"{value:,}")


def page(title, body):
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' + \
        '<title>' + esc(title) + '</title><style>' + STYLE + '</style><main>' + body + '</main></html>'


def generate(out, manifest, records, summary, clock_mhz=None):
    if clock_mhz is not None and (not math.isfinite(clock_mhz) or clock_mhz <= 0):
        raise ValueError("Assumed clock must be finite and positive")
    hw = records.get("hw", {})
    metrics = hw.get("metrics", {})
    measurements = {}
    if "cycles" in metrics and "retired" in metrics:
        measurements["full_run"] = measurement(metrics["cycles"], metrics["retired"], clock_mhz)
    if metrics.get("roi_complete"):
        measurements["roi"] = {**measurement(metrics["roi_cycles"], metrics["roi_retired"], clock_mhz),
                               "start_cycle_excluded": metrics["roi_start_cycle"], "end_cycle_included": metrics["roi_end_cycle"]}
    csr = hw.get("csr_counters", {})
    if csr.get("status") == "complete": measurements["csr"] = measurement(csr["cycles"], csr["retired"], clock_mhz)
    report = {"schema_version": 1, "status": summary["status"], "application": manifest["application"],
              "optimization": manifest["optimization"], "isa": manifest["isa"], "elf_sha256": manifest["elf_sha256"],
              "rtl_build": hw.get("rtl_build"), "memory_configuration": manifest.get("rtl_memory"),
              "assumed_clock_mhz": clock_mhz, "measurements": measurements,
              "functional_signature_match": summary.get("signature_match"), "csr_counters": csr,
              "instruction_log": hw.get("instruction_log", {"status": "not_recorded"}),
              "run_complete": metrics.get("reason") == "tohost", "backends": records,
              "measurement_notes": ["RTL full run includes startup and checks; a failed run is an observed prefix.",
                  "ROI excludes begin-marker retirement and includes end-marker retirement; wrapper overhead is included.",
                  "CSR cycle and instret snapshots are sequential, not an atomic pair; their interval includes read/record overhead.",
                  "Estimated execution time assumes the supplied clock; it is not measured wall time or timing closure.",
                  "Spike is a functional reference. CPI = RTL cycles / retired instructions; lower CPI alone does not imply lower latency."]}
    if (out / "hw.signature").is_file(): report["functional_signature_sha256"] = file_digest(out / "hw.signature")
    save(out / "performance.json", report)
    title = manifest["application"] + " · " + manifest["optimization"]
    links = [('program.dis', 'Source & disassembly'), ('trace.html', 'Cycle viewer'), ('commits.csv', 'Retired instructions (CSV)'),
             ('commits.jsonl', 'Retired instructions (JSONL)'), ('performance.json', 'Measurement JSON')]
    body = '<nav class="links"><a href="../results.html">All program results</a><a href="../index.html">Example gallery</a></nav>'
    body += '<h1>' + esc(title) + '</h1><p class="' + esc(summary["status"]) + '"><strong>' + esc(summary['status'].upper()) + '</strong> · ' + esc(manifest["isa"]) + '</p>'
    body += '<section><h2>Program output</h2>'
    for backend, record in records.items():
        body += '<h3>' + ('Spike — functional reference' if backend == 'sw' else 'RTL') + ' · ' + esc(record['status'].upper()) + '</h3>'
        body += '<pre>' + esc(record.get('console') or '(No buffered console output)') + '</pre>'
        if record.get('console_truncated'): body += '<p class="fail">Console truncated at 1024 bytes.</p>'
        for key in ('error', 'telemetry_error'):
            if record.get(key): body += '<p class="fail">' + esc(record[key]) + '</p>'
        if backend == 'hw' and record.get('status') != 'pass':
            stopped = record.get('metrics', {})
            body += '<p class="fail">Termination: ' + esc(stopped.get('reason', 'No hardware completion record')) + '</p>'
            if stopped.get('reason') == 'trap':
                body += table(['Trap cause', 'Faulting PC', 'Fault value'],
                              [(stopped.get('trap_cause'), f"0x{stopped.get('trap_pc', 0):08x}", f"0x{stopped.get('trap_value', 0):08x}")])
        body += table(['Check', 'Actual', 'Expected', 'Result'],
                      [(c['id'], f"{c['actual']} / 0x{c['actual']:08x}", f"{c['expected']} / 0x{c['expected']:08x}",
                        'PASS' if c['actual'] == c['expected'] else 'FAIL') for c in record.get('checks', [])])
        if record.get('results'): body += table(['Result slot', 'Value'], record['results'].items())
    body += '<p class="note">Console output is SRAM data read after execution. Keep printf and validation outside the measured region.</p></section>'
    body += '<section><h2>Performance measurements</h2>'
    body += '<p>' + (f'Assumed target frequency: {clock_mhz:g} MHz. Execution time below is an estimate.' if clock_mhz else 'No target frequency supplied. Execution time is not recorded; use CLOCK_MHZ only with an explicit frequency assumption.') + '</p>'
    titles = {'full_run': 'Full RTL run' if report['run_complete'] else 'Observed RTL prefix (incomplete)',
              'roi': 'RTL marker ROI', 'csr': 'Software CSR interval (sequential reads)'}
    body += table(['Boundary', 'Cycles', 'Retired instructions', 'CPI', 'Estimated time (µs)'],
                  [(titles[k], display(v['cycles']), display(v['retired']), display(v['cpi']),
                    display(None if v['estimated_seconds'] is None else v['estimated_seconds'] * 1e6)) for k, v in measurements.items()])
    if 'roi' not in measurements: body += '<p class="note">ROI not recorded or incomplete. Bracket one region with lab_roi_begin() and lab_roi_end().</p>'
    if csr: body += '<p class="note">CSR record: ' + esc(csr.get('status')) + '.</p>'
    body += '<ul class="note">' + ''.join('<li>' + esc(n) + '</li>' for n in report['measurement_notes']) + '</ul></section>'
    log = report['instruction_log']
    body += '<section><h2>Executed instructions</h2>'
    if log.get('status') == 'complete':
        body += '<p>' + display(log['retired']) + ' actual retirements recorded; totals match the testbench. The cycle-trace cap does not limit this log.</p>'
        body += table(['Instruction class', 'Retirements'], log['instruction_classes'].items())
        body += '<h3>Most frequent PCs' + (' within ROI' if log['roi_retired'] is not None else '') + '</h3>'
        body += table(['PC', 'Instruction', 'Retirements'], [(r['pc'], r['assembly'], r['retired']) for r in log['roi_hotspots'] or log['hotspots']])
    else: body += '<p>Run with COMMITS=1 for a complete executed-instruction log. Disassembly lists code; it does not count loop iterations.</p>'
    body += '<nav class="links">' + ''.join('<a href="' + name + '">' + title + '</a>' for name, title in links if (out / name).is_file()) + '</nav></section>'
    body += '<footer>ELF SHA256 <code>' + esc(manifest['elf_sha256']) + '</code><br>RTL build <code>' + esc(hw.get('rtl_build', 'Not run')) + '</code></footer>'
    (out / 'report.html').write_text(page(title, body))
    refresh_index(out.parent)
    return report


def refresh_index(build):
    rows = []
    for path in sorted(build.glob('*/performance.json')):
        if not path.with_name('report.html').is_file(): continue
        data = json.loads(path.read_text())
        roi = data['measurements'].get('roi', {})
        href = quote(path.parent.name) + '/report.html'
        rows.append('<tr><td><a href="' + href + '">' + esc(data['application']) + '</a></td>' +
                    ''.join('<td>' + esc(x) + '</td>' for x in [data['optimization'], data['status'].upper(), display(roi.get('cycles')),
                            display(roi.get('retired')), display(roi.get('cpi')), display(data.get('assumed_clock_mhz'))]) + '</tr>')
    body = '<nav><a href="index.html">Cycle example gallery</a></nav><h1>Program output & performance</h1>'
    body += '<p>Open a run to see its console, checks and measured boundaries. Compare cycles and instruction count together; CPI alone can be misleading.</p>'
    body += '<section><div class="scroll"><table><thead><tr>' + ''.join('<th>' + text + '</th>' for text in ['Application', 'Build', 'Result', 'ROI cycles', 'ROI retired', 'ROI CPI', 'Assumed MHz']) + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></section>'
    body += '<p class="note">Runs must use comparable inputs, functionality, instrumentation and memory settings. Opening a stored report does not rerun or revalidate it.</p>'
    (build / 'results.html').write_text(page('Program results', body))


def print_measurements(report):
    for name, values in report['measurements'].items():
        extra = '' if values['estimated_seconds'] is None else f", estimated={values['estimated_seconds'] * 1e6:.3f} us @ {report['assumed_clock_mhz']:g} MHz"
        print(f"  {name}: cycles={values['cycles']}, retired={values['retired']}, CPI={display(values['cpi'])}{extra}")
