# =============================================================================
# HY-RV | test_registration
# Description: Verify the public CPU laboratory contract and preserve source-bound evidence.
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See applicable manifests and verification records for provenance.
# Preserve existing license, copyright, and original author notices.
# =============================================================================

"""Exercise publication and invalidation using real compiled student programs."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import applications
import lab
from artifact_receipt import capture
from test_camera_lab import arguments
from viewer import catalog


class RegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hardware = lab.build_hardware(arguments())
        cls.old_build = lab.BUILD
        cls.temp = tempfile.TemporaryDirectory(prefix='cpu-registration-')
        cls.root = Path(cls.temp.name)
        lab.BUILD = cls.root / 'build'
        cls.records = []

    @classmethod
    def tearDownClass(cls):
        lab.BUILD = cls.old_build
        report = os.environ.get('CPU_LAB_REGISTRATION_TEST_REPORT')
        if report:
            lab.save_json(Path(report), dict(rtl_build=cls.hardware[1], cases=cls.records))
        cls.temp.cleanup()

    def test_registration_lifecycle(self):
        source = self.root / 'main.c'
        source.write_text('#include "lab.h"\n#include <stdio.h>\n'
                          'static volatile unsigned input[]={1,2,3,4};\n'
                          'int main(void){unsigned sum=0;lab_roi_begin();'
                          'for(unsigned i=0;i<4;i++)sum+=input[i];lab_roi_end();'
                          'lab_check(1,sum,10);printf("sum=%u\\n",sum);return 0;}\n')
        args = arguments(app='custom', source=[str(source)], name='my-sum',
                         title='My <sum> & "demo"', memory_profile='fast', trace_limit=64)

        def entries():
            return json.loads((lab.BUILD / 'catalog.json').read_text())['examples']

        def register(opt='O2'):
            args.opt = opt
            self.assertTrue(lab.register(args, self.hardware))
            folder = lab.BUILD / next(e['id'] for e in entries() if e['id'].endswith('-' + opt))
            receipt = applications.completed(folder)
            self.assertIsNotNone(receipt)
            summary = json.loads((folder / 'result.json').read_text())
            self.assertTrue(summary['signature_match'])
            self.records.append(dict(optimization=opt, evidence=capture(folder), **summary))
            return folder, receipt

        out, before = register()
        self.assertEqual(entries()[0]['group_id'], 'custom')
        self.assertEqual(entries()[0]['title'], args.title)
        self.assertIn('My &lt;sum&gt; &amp; &quot;demo&quot;', (lab.BUILD / 'index.html').read_text())
        self.assertTrue((out / 'commits.csv').is_file())
        # A second optimization is a separate, simultaneously available run.
        register('O0')
        self.assertEqual(len(entries()), 2)
        source.write_text(source.read_text().replace('{1,2,3,4}', '{2,3,4,5}').replace('sum,10', 'sum,14'))
        out, after = register()
        self.assertNotEqual(before['elf_sha256'], after['elf_sha256'])
        self.assertEqual(len(entries()), 2)

        # Names cannot silently reassign somebody else's application.
        other = self.root / 'other.c'
        other.write_text(source.read_text())
        args.source = [str(other)]
        with self.assertRaisesRegex(ValueError, 'already identifies other sources'):
            lab.register(args, self.hardware)
        args.source = [str(source)]

        exported = catalog.export_reports(lab.BUILD)
        with zipfile.ZipFile(exported) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['examples'], 2)
            self.assertIn(out.name + '/registration.json', archive.namelist())
            self.assertIn('course/index.html', archive.namelist())
            for name, expected in manifest['sha256'].items():
                import hashlib
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), expected)

        # Changed evidence cannot keep its old registered PASS entry.
        original = (out / 'hw.json').read_text()
        (out / 'hw.json').write_text(original + '\n')
        catalog.refresh(lab.BUILD)
        self.assertEqual(len(entries()), 1)
        (out / 'hw.json').write_text(original)
        catalog.refresh(lab.BUILD)
        self.assertEqual(len(entries()), 2)

        # The displayed sample stream must also belong to the registered run.
        viewer = (out / 'trace.html').read_text()
        (out / 'trace.html').write_text(re.sub(r'"cycle":(\d+)',
            lambda match: '"cycle":' + str(int(match.group(1)) + 1), viewer, count=1))
        catalog.refresh(lab.BUILD)
        self.assertEqual(len(entries()), 1)
        (out / 'trace.html').write_text(viewer)
        catalog.refresh(lab.BUILD)
        self.assertEqual(len(entries()), 2)

        # A plain hardware-only rerun requires explicit re-registration.
        args.backend = 'hw'; args.trace = True
        self.assertTrue(lab.run(args, self.hardware)[0])
        self.assertFalse((out / 'registration.json').exists())
        self.assertEqual(len(entries()), 1)
        register()
        source.write_text(source.read_text().replace('sum,14', 'sum,15'))
        self.assertFalse(lab.register(args, self.hardware))
        self.assertFalse((out / 'registration.json').exists())
        self.assertEqual(len(entries()), 1)
        self.assertEqual(json.loads((out / 'result.json').read_text())['status'], 'fail')
        source.write_text(source.read_text().replace('sum,15', 'sum,14'))
        register()
        source.unlink()
        with self.assertRaisesRegex(lab.LabError, 'Source does not exist'):
            lab.register(args, self.hardware)
        self.assertEqual(len(entries()), 1)
        self.assertFalse((out / 'registration.json').exists())

    def test_registration_requires_source_and_safe_name(self):
        for source, name in ((None, 'app'), (['main.c'], '../app'), (['main.c'], None)):
            with self.subTest(source=source, name=name), self.assertRaises(ValueError):
                applications.validate_request(arguments(source=source, name=name), lab.BUILD)


if __name__ == '__main__': unittest.main()
