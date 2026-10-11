"""Output isolation and replacement selection, without running any simulator."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import lab
import memory_protocol
from test_camera_lab import arguments as camera_arguments
from test_visual_lab import args as visual_arguments


class EnvironmentTests(unittest.TestCase):
    def test_candidate_failure_does_not_invalidate_baseline(self):
        with tempfile.TemporaryDirectory(prefix="cpu-output-isolation-") as tmp:
            root = Path(tmp)
            missing = root / "missing.c"
            app = "application-" + hashlib.sha256(str(missing).encode()).hexdigest()[:8]
            baseline = root / "build" / (app + "-O2")
            candidate = root / "build/candidate" / (app + "-O2")
            for directory in (baseline, candidate):
                directory.mkdir(parents=True)
                (directory / "result.json").write_text('{"status":"pass"}\n')
                (directory / "trace.html").write_text("previous report")
            options = argparse.Namespace(source=[str(missing)], app="unused", opt="O2",
                                         memory_profile="fast", image=None)
            with mock.patch.object(lab, "ROOT", root), \
                    mock.patch.dict(os.environ, {"LAB_BUILD_DIR": "build/candidate"}):
                with mock.patch.object(lab, "BUILD", lab.build_directory()):
                    with self.assertRaisesRegex(lab.LabError, "Source does not exist"):
                        lab.build_application(options)
            self.assertTrue((baseline / "result.json").is_file())
            self.assertEqual((baseline / "trace.html").read_text(), "previous report")
            self.assertFalse((candidate / "result.json").exists())
            self.assertFalse((candidate / "trace.html").exists())

    def test_environment_core_selection_and_explicit_override(self):
        with tempfile.TemporaryDirectory(prefix="cpu-core-selection-") as tmp:
            candidate = str(Path(tmp) / "candidate")
            explicit = str(Path(tmp) / "explicit")
            with mock.patch.dict(os.environ, {"LAB_RTL_DIR": candidate}):
                self.assertEqual(camera_arguments().rtl_dir, candidate)
                self.assertEqual(visual_arguments().rtl_dir, candidate)
                self.assertEqual(camera_arguments(rtl_dir=explicit).rtl_dir, explicit)
                self.assertEqual(visual_arguments(rtl_dir=explicit).rtl_dir, explicit)
                for extra, expected in (([], candidate), (["--rtl-dir", explicit], explicit)):
                    with mock.patch.object(sys, "argv", ["lab.py", "build", *extra]), \
                            mock.patch.object(lab, "build_application", return_value=(Path(tmp), {})) as build, \
                            contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(lab.main(), 0)
                    self.assertEqual(build.call_args.args[0].rtl_dir, expected)

    def test_memory_protocol_uses_selected_output_and_core(self):
        with tempfile.TemporaryDirectory(prefix="cpu-memory-selection-") as tmp:
            directory = Path(tmp) / "candidate-output"
            candidate = Path(tmp) / "candidate-core"
            with mock.patch.object(lab, "BUILD", directory), \
                    mock.patch.dict(os.environ, {"LAB_RTL_DIR": str(candidate)}), \
                    mock.patch.object(sys, "argv", ["memory_protocol.py"]), \
                    mock.patch.object(memory_protocol, "build_standalone", side_effect=RuntimeError("fixture stop")) as build, \
                    contextlib.redirect_stdout(io.StringIO()):
                memory_protocol.main()
            self.assertEqual(build.call_args.args, (candidate, directory / "memory_protocol_cases"))
            report = json.loads((directory / "memory_protocol.json").read_text())
            self.assertEqual(report["setup_error"], "fixture stop")

    def test_export_excludes_selected_output_inside_source_tree(self):
        with tempfile.TemporaryDirectory(prefix="cpu-isolated-export-") as tmp:
            root = Path(tmp)
            (root / "application.c").write_text("int main(void) { return 0; }\n")
            output = root / "candidate-output"
            output.mkdir()
            (output / "private-generated-result.json").write_text("{}")
            with mock.patch.object(lab, "ROOT", root), mock.patch.object(lab, "BUILD", output), \
                    contextlib.redirect_stdout(io.StringIO()):
                lab.export_bundle()
            with zipfile.ZipFile(output / "cpu_lab.zip") as archive:
                self.assertEqual(set(archive.namelist()), {"cpu_lab/application.c", "cpu_lab/bundle_manifest.json"})


if __name__ == "__main__":
    unittest.main()
