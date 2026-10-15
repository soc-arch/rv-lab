# =============================================================================
# HY-RV | test_student_workflow
# Description: Verify the public CPU laboratory contract and preserve source-bound evidence.
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See applicable manifests and verification records for provenance.
# Preserve existing license, copyright, and original author notices.
# =============================================================================

"""Real student programs: same ELF, CSR/TB agreement, complete instruction logs."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lab
from artifact_receipt import capture
from test_camera_lab import arguments


class StudentWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hardware = lab.build_hardware(arguments())
        cls.original_build = lab.BUILD
        cls.temp = tempfile.TemporaryDirectory(prefix='cpu-student-workflow-')
        cls.root = Path(cls.temp.name)
        lab.BUILD = cls.root / 'build'
        cls.records = []

    @classmethod
    def tearDownClass(cls):
        lab.BUILD = cls.original_build
        path = os.environ.get('CPU_LAB_PERF_TEST_REPORT')
        if path: lab.save_json(Path(path), dict(schema_version=1, rtl_build=cls.hardware[1], cases=cls.records))
        cls.temp.cleanup()

    def run_case(self, **overrides):
        args = arguments(**dict(dict(app='10_performance', trace=True, trace_limit=8,
                                     commit_log=True, clock_mhz=100, csr_counters=False), **overrides))
        ok, out, summary = lab.run(args, self.hardware)
        data = json.loads((out / 'performance.json').read_text())
        self.records.append(dict(data, evidence=capture(out)))
        return ok, out, summary, data

    def test_csr_values_match_each_public_retirement_o0_o2(self):
        measurements = {}
        for optimization in ('O0', 'O2'):
            ok, out, summary, data = self.run_case(opt=optimization)
            self.assertTrue(ok)
            self.assertTrue(summary['signature_match'])
            self.assertEqual(data['backends']['hw']['console'], 'sum(1..32)=528\n')
            self.assertEqual(data['csr_counters']['status'], 'complete')
            self.assertTrue(data['instruction_log']['count_matches_testbench'])
            self.assertEqual(data['instruction_log']['roi_retired'], data['measurements']['roi']['retired'])
            self.assertGreater(data['measurements']['csr']['cycles'], data['measurements']['roi']['cycles'])
            manifest = json.loads((out / 'build.json').read_text())
            symbols = manifest['symbols']; address = symbols['lab_perf_record']
            self.assertFalse(address < symbols['end_signature'] and address + 64 > symbols['begin_signature'])
            reads = 0
            with (out / 'commits.jsonl').open() as stream:
                commit_lines = list(stream)
            for ordinal, line in enumerate(commit_lines, 1):
                row = json.loads(line); insn = row['insn']; csr = insn >> 20
                if insn & 0x7f != 0x73 or csr not in (0xb00, 0xb80, 0xb02, 0xb82): continue
                # These trap-free programs never reset or write the counters.
                expected = row['cycle'] - 1 if csr in (0xb00, 0xb80) else ordinal - 1
                if csr in (0xb80, 0xb82): expected >>= 32
                self.assertEqual(row['rd_data'], expected & 0xffffffff)
                reads += 1
            self.assertGreaterEqual(reads, 12)
            measurements[optimization] = data['measurements']['roi']
        self.assertLess(measurements['O2']['cycles'], measurements['O0']['cycles'])

    def test_custom_main_without_csr_and_failed_run(self):
        source = self.root / 'my_main.c'
        source.write_text('#include "lab.h"\n#include <stdio.h>\nstatic volatile unsigned a[]={1,2,3,4};\n'
                          'int main(void){unsigned sum=0;lab_roi_begin();for(unsigned i=0;i<4;i++)sum+=a[i];'
                          'lab_roi_end();lab_check(1,sum,10);printf("sum=%u\\n",sum);return 0;}\n')
        ok, out, _, data = self.run_case(source=[str(source)], app='custom', clock_mhz=None)
        self.assertTrue(ok)
        self.assertEqual(data['backends']['hw']['console'], 'sum=10\n')
        self.assertEqual(data['csr_counters'], {})
        self.assertIsNone(data['measurements']['roi']['estimated_seconds'])
        self.assertGreater(data['instruction_log']['retired'], 8)
        self.assertEqual(data['backends']['hw']['metrics']['trace_truncated'], 1)
        self.assertTrue((out / 'report.html').is_file())
        source.write_text(source.read_text().replace('sum,10', 'sum,11'))
        ok, out, _, data = self.run_case(source=[str(source)], app='custom')
        self.assertFalse(ok)
        self.assertEqual(data['status'], 'fail')
        self.assertIn('FAIL', (out / 'report.html').read_text())
        self.assertTrue(data['functional_signature_match'])  # Same wrong answer still fails.


if __name__ == '__main__': unittest.main()
