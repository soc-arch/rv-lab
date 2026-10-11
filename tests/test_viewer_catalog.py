"""Runner verdict and saved-report navigation regression tests.

These tests use temporary transport fixtures; they do not manufacture or publish
CPU measurements. No compiler, simulator, browser, or existing build is required.
Run: python3 tests/test_viewer_catalog.py -v
"""
import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lab
from viewer import catalog


def read_payload(page):
    opening = '<script id="trace-data" type="application/json">'
    return json.loads(page.read_text().split(opening, 1)[1].split('</script>', 1)[0])


class HostValidationVerdictTests(unittest.TestCase):
    def test_host_rejection_overrides_successful_rtl_termination(self):
        # The simulated process boundary reports normal termination. The real
        # runner still must reject missing ROI completion or failed host pixels.
        for roi_complete, pixels_match, expected in (
                (False, True, 'fail'), (True, False, 'fail'), (True, True, 'pass')):
            with self.subTest(roi_complete=roi_complete, pixels_match=pixels_match):
                with tempfile.TemporaryDirectory(prefix='cpu-viewer-verdict-') as tmp:
                    out = Path(tmp)
                    options = argparse.Namespace(
                        app='07_denoise', trace=True, trace_startup=False,
                        trace_symbol='main', trace_limit=4, wave=False,
                        max_cycles=1000, wall_seconds=1, memory_profile='fast')
                    symbols = dict(main=0x80000080, tohost=0x80001000,
                                   begin_signature=0x80002000,
                                   end_signature=0x80002000 + 664 * 4,
                                   lab_roi_begin_marker=0x80003000,
                                   lab_roi_end_marker=0x80003004)
                    manifest = dict(application=options.app, symbols=symbols,
                                    elf_sha256='fixture-only',
                                    visual={'trace_symbol': 'main'})

                    def completed_process(command, log, timeout):
                        # Valid completed runtime signature, with no failed
                        # target checks. It is consumed by real read_signature.
                        words = [0] * 664
                        words[:2] = [0x4350554c, 1]
                        words[7] = 0x80000000
                        (out / 'hw.signature').write_text(
                            ''.join('%08x\n' % word for word in words))
                        (out / 'hw.metrics.json').write_text(json.dumps(dict(
                            status='pass', cycles=100, retired=40,
                            roi_complete=int(roi_complete),
                            roi_cycles=20 if roi_complete else 0)))
                        # Only the existence of a capture is needed here. The
                        # renderer is mocked, so this is never a displayed trace.
                        (out / 'trace.jsonl').write_text('{}\n')
                        return 0, ''

                    image_check = dict(passed=pixels_match, bytes_compared=27,
                                       mismatched_bytes=0 if pixels_match else 1)
                    with mock.patch.object(lab, 'invoke', side_effect=completed_process), \
                            mock.patch('visual_support.verify_output', return_value=image_check), \
                            mock.patch('viewer.render.generate') as generate, \
                            contextlib.redirect_stdout(io.StringIO()):
                        record, _ = lab.run_backend(
                            options, 'hw', out, manifest,
                            hardware=(Path('/fixture/simulator'), 'fixture-build'))
                    self.assertEqual(record['metrics']['status'], 'pass')
                    self.assertEqual(record['status'], expected)
                    self.assertEqual(json.loads((out / 'hw.json').read_text())['status'], expected)
                    self.assertEqual(generate.call_args.kwargs['metadata']['status'], expected)
                    if not roi_complete:
                        self.assertIn('measured region', record['error'])
                    elif not pixels_match:
                        self.assertIn('independent host reference', record['error'])


class SavedCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cpu-catalog-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.build = Path(self.temp.name)

    def report(self, name, elf='fixture-elf'):
        directory = self.build / name
        directory.mkdir(parents=True, exist_ok=True)
        payload = {'metadata': {'status': 'pass', 'elf_sha256': elf},
                   'trace': [], 'assembly': {}}
        (directory / 'trace.html').write_text(
            '<script id="trace-data" type="application/json">' +
            json.dumps(payload, separators=(',', ':')) + '</script>')
        (directory / 'hw.json').write_text(json.dumps({
            'status': 'pass', 'elf_sha256': elf,
            'metrics': {'status': 'pass', 'cycles': 100, 'retired': 40}}))
        (directory / 'build.json').write_text(json.dumps({'elf_sha256': elf}))
        return directory

    def test_primary_and_alias_navigation_resolve_after_refresh(self):
        first = self.report('01_arithmetic-O2')
        second = self.report('02_memory-O2-mem-stress')
        alias = self.build / 'showcase/01_arithmetic/trace.html'
        alias.parent.mkdir(parents=True)
        alias.write_text((first / 'trace.html').read_text())
        catalog.refresh(self.build)
        entries = json.loads((self.build / 'catalog.json').read_text())['examples']
        self.assertEqual(len(entries), 2)
        for page in (first / 'trace.html', second / 'trace.html', alias):
            payload = read_payload(page)
            self.assertEqual(payload['trace'], [])
            navigation = payload['metadata']['navigation']
            self.assertTrue((page.parent / navigation['home_href']).is_file())
            links = [e['href'] for g in navigation['groups'] for e in g['examples']]
            self.assertEqual(len(links), 2)
            for href in links:
                self.assertTrue((page.parent / href).is_file(), (page, href))

    def test_failures_and_wrong_elf_are_not_completed_examples(self):
        failed = self.report('01_arithmetic-O2')
        record = json.loads((failed / 'hw.json').read_text())
        record['status'] = 'fail'
        (failed / 'hw.json').write_text(json.dumps(record))
        wrong_elf = self.report('02_memory-O2')
        (wrong_elf / 'build.json').write_text(json.dumps({'elf_sha256': 'different'}))
        catalog.refresh(self.build)
        self.assertEqual(json.loads((self.build / 'catalog.json').read_text())['examples'], [])

    def test_invalidated_alias_is_removed_and_restored_with_new_report(self):
        original = self.report('04_muldiv-O2')
        alias = self.build / 'muldiv/trace.html'
        alias.parent.mkdir(parents=True)
        alias.write_text((original / 'trace.html').read_text())
        catalog.refresh(self.build)
        (original / 'trace.html').unlink()
        (original / 'hw.json').unlink()
        catalog.refresh(self.build)
        self.assertFalse(alias.exists(), 'Invalidated run must not keep a PASS alias')
        self.assertEqual(json.loads((self.build / 'catalog.json').read_text())['examples'], [])
        self.report('04_muldiv-O2', elf='new-fixture-elf')
        catalog.refresh(self.build)
        self.assertTrue(alias.exists(), 'Successful rerun must restore previously shared URLs')
        payload = read_payload(alias)
        self.assertEqual(payload['metadata']['elf_sha256'], 'new-fixture-elf')
        self.assertEqual(payload['metadata']['navigation']['current_id'], '04_muldiv-O2')

    def test_failed_source_validation_refreshes_existing_gallery(self):
        original = self.report('01_arithmetic-O2')
        alias = self.build / 'showcase/01_arithmetic/trace.html'
        alias.parent.mkdir(parents=True)
        alias.write_text((original / 'trace.html').read_text())
        catalog.refresh(self.build)
        options = argparse.Namespace(app='01_arithmetic', source=None, opt='O2',
                                     memory_profile='fast', image=None)
        missing = self.build / 'deleted_application.c'
        with mock.patch.object(lab, 'BUILD', self.build), \
                mock.patch.object(lab, 'source_files', return_value=('01_arithmetic', [missing], [])):
            with self.assertRaisesRegex(lab.LabError, 'Source does not exist'):
                lab.build_application(options)
        self.assertFalse((original / 'trace.html').exists())
        self.assertFalse(alias.exists())
        self.assertEqual(json.loads((self.build / 'catalog.json').read_text())['examples'], [])


if __name__ == '__main__':
    unittest.main()
