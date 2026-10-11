"""Reject misleading telemetry and keep untrusted program text inert in reports."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import performance


class PerformanceTests(unittest.TestCase):
    def test_csr_rollover_incomplete_and_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'csr.txt'
            # A real-format record crossing the low 32-bit boundary.
            words = [0x4c504d31, 1, 16, 3, 0xfffffffe, 2, 10, 0, 3, 3, 14, 0, 5, 0, 4, 0]
            path.write_text('\n'.join(f'{w:08x}' for w in words))
            record = performance.read_csr(path)
            self.assertEqual((record['cycles'], record['retired']), (5, 4))
            words[12] = 6
            path.write_text('\n'.join(f'{w:08x}' for w in words))
            with self.assertRaisesRegex(ValueError, 'delta'): performance.read_csr(path)
            words[3] = 1
            path.write_text('\n'.join(f'{w:08x}' for w in words))
            self.assertEqual(performance.read_csr(path)['status'], 'incomplete')
            path.write_text('00000000\n' * 16)
            self.assertEqual(performance.read_csr(path)['status'], 'not_recorded')

    def test_retirement_boundaries_and_incomplete_logs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            assembly = root / 'program.dis'
            assembly.write_text('80000000: 00000013 addi zero,zero,0\n80000004: 00102023 sw ra,0(zero)\n')
            records = [dict(cycle=c, pc=0x80000000 if c != 12 else 0x80000004,
                            insn=0x13 if c != 12 else 0x00102023, rd=0, rd_we=0, rd_data=0) for c in (10, 12, 17)]
            log = root / 'commits.jsonl'
            log.write_text(''.join(json.dumps(r) + '\n' for r in records))
            metrics = dict(cycles=17, retired=3, roi_complete=1, roi_start_cycle=10, roi_end_cycle=12, roi_retired=1)
            result = performance.retirement_summary(log, metrics, assembly, root / 'commits.csv')
            self.assertEqual(result['roi_retired'], 1)
            self.assertEqual(result['instruction_classes']['store'], 1)
            with (root / 'commits.csv').open() as f: rows = list(csv.DictReader(f))
            self.assertEqual([r['in_roi'] for r in rows], ['0', '1', '0'])
            log.write_text(json.dumps(records[0]) + '\n')
            with self.assertRaisesRegex(ValueError, 'disagree'):
                performance.retirement_summary(log, metrics, assembly, root / 'commits.csv')

    def test_failure_html_escaping_and_frequency_semantics(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'custom-O2'; out.mkdir()
            manifest = dict(application='custom', optimization='O2', isa='rv32im', elf_sha256='abc')
            records = {'hw': dict(status='fail', console='</script><script>alert(1)</script>',
                                 checks=[dict(id=7, actual=9, expected=8)], metrics=dict(cycles=20, retired=5, reason='cycle_budget'))}
            result = performance.generate(out, manifest, records, dict(status='fail'))
            self.assertIsNone(result['measurements']['full_run']['estimated_seconds'])
            self.assertEqual(result['measurements']['full_run']['cpi'], 4)
            self.assertNotIn('<script>', (out / 'report.html').read_text())
            self.assertIn('cycle_budget', (out / 'report.html').read_text())
            self.assertIn('incomplete', (out / 'report.html').read_text())
            self.assertNotIn('roi', result['measurements'])
            result = performance.generate(out, manifest, records, dict(status='fail'), 100)
            self.assertEqual(result['measurements']['full_run']['estimated_seconds'], 20 / 1e8)
            for frequency in (float('nan'), 0, -1, float('inf')):
                with self.assertRaises(ValueError): performance.generate(out, manifest, records, dict(status='fail'), frequency)


if __name__ == '__main__': unittest.main()
