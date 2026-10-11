"""Camera arithmetic, real Spike/RTL execution, and failed-run artifact checks.

Run from the package root: python3 tests/test_camera_lab.py -v
Requires the same compiler, Spike and Verilator tools as `make compare`.
Application outputs are isolated in a temporary directory; the existing RTL
build cache is reused. Set CPU_LAB_TEST_REPORT to retain a JSON evidence report.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import camera_support as camera
import lab


def arguments(**overrides):
    values = dict(command="run", app="06_camera", source=None, opt="O2",
                  backend="both", rtl_dir=os.environ.get("LAB_RTL_DIR"), trace=False, trace_startup=False,
                  trace_symbol=None, trace_limit=20000, wave=False,
                  max_cycles=20000000, wall_seconds=120, iterations=1,
                  validation=False, image=None, width=None, height=None,
                  camera_mode="pipeline", port=8770)
    values.update(overrides)
    return argparse.Namespace(**values)


def ppm(path, width, height, rgb):
    path.write_bytes(f"P6\n{width} {height}\n255\n".encode() + rgb)


class ReferenceTests(unittest.TestCase):
    def test_primary_colors_and_white(self):
        rgb = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255]) * 3
        actual = camera.reference_images(rgb, 4, 3)["grayscale"]
        self.assertEqual(actual, bytes([77] * 3 + [149] * 3 + [29] * 3 + [255] * 3) * 3)

    def test_linear_ramp_has_known_gradient_and_black_boundary(self):
        rgb = bytes(v for y in range(5) for x in range(7) for v in (10*x + 3*y,) * 3)
        actual = camera.reference_images(rgb, 7, 5)["sobel"]
        # Gx=8*10=80; Gy=8*3=24; L1 magnitude=104 at interior pixels.
        expected = bytes(v for y in range(5) for x in range(7)
                         for v in ((104 if 0 < x < 6 and 0 < y < 4 else 0),) * 3)
        self.assertEqual(actual, expected)

    def test_minimum_frame_saturates_without_wrapping(self):
        rgb = bytes(v for y in range(3) for x in range(3)
                    for v in ((0 if x == 0 else 255),) * 3)
        expected = bytearray(27)
        expected[12:15] = bytes([255] * 3)
        self.assertEqual(camera.reference_images(rgb, 3, 3)["sobel"], expected)

    def test_ppm_does_not_discard_binary_whitespace(self):
        with tempfile.TemporaryDirectory(prefix="cpu-camera-ppm-") as folder:
            source = Path(folder) / "input.ppm"
            rgb = bytes([10, 32, 13] + list(range(24)))
            source.write_bytes(b"P6\n# comment\n3 3\n255\n" + rgb)
            self.assertEqual(camera.read_ppm(source), (3, 3, rgb))

    def test_host_rejects_a_forged_output_pixel(self):
        with tempfile.TemporaryDirectory(prefix="cpu-camera-forged-") as folder:
            directory = Path(folder)
            source = bytes(range(27))
            (directory / "input.rgb").write_bytes(source)
            manifest = {"camera": {"width": 3, "height": 3, "mode": "copy",
                                    "input_sha256": hashlib.sha256(source).hexdigest()},
                        "symbols": {"camera_output_storage": 0x80001000,
                                    "begin_signature": 0x80001000}}
            raw = bytearray(16) + bytearray(source) + bytearray(1)
            words = list(struct.unpack("<11I", raw))
            self.assertTrue(camera.verify_output(words, manifest, directory, "good")["passed"])
            raw[16 + 11] ^= 1
            forged = list(struct.unpack("<11I", raw))
            verdict = camera.verify_output(forged, manifest, directory, "forged")
            self.assertFalse(verdict["passed"])
            self.assertEqual(verdict["mismatched_bytes"], 1)
            # Retain actual failed pixels for diagnosis; do not replace with oracle pixels.
            self.assertEqual((directory / "forged.output.rgb").read_bytes(), raw[16:43])
            (directory / "input.rgb").write_bytes(bytes(27))
            with self.assertRaisesRegex(ValueError, "Input changed"):
                camera.verify_output(words, manifest, directory, "changed-input")


class FirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Select/build the normal RTL cache before redirecting generated apps.
        cls.hardware = lab.build_hardware(arguments())
        cls.original_build = lab.BUILD
        cls.directory = tempfile.TemporaryDirectory(prefix="cpu-camera-firmware-")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.addClassCleanup(setattr, lab, "BUILD", cls.original_build)
        cls.root = Path(cls.directory.name)
        lab.BUILD = cls.root / "build"
        cls.evidence = []

    @classmethod
    def tearDownClass(cls):
        if os.environ.get("CPU_LAB_TEST_REPORT"):
            report = Path(os.environ["CPU_LAB_TEST_REPORT"])
            report.parent.mkdir(parents=True, exist_ok=True)
        else:
            fd, filename = tempfile.mkstemp(prefix="cpu-lab-camera-tests-", suffix=".json")
            os.close(fd)
            report = Path(filename)
        report.write_text(json.dumps({"schema_version": 1,
                                      "rtl_build": cls.hardware[1],
                                      "cases": cls.evidence}, indent=2) + "\n")
        print(f"Camera test evidence: {report}", flush=True)

    def execute(self, name, mode, width, height, rgb):
        source = self.root / (name + ".ppm")
        ppm(source, width, height, rgb)
        ok, out, summary = lab.run(arguments(image=str(source), camera_mode=mode), self.hardware)
        self.assertTrue(ok, summary)
        self.assertTrue(summary["signature_match"])
        expected = camera.reference_images(rgb, width, height)[
            {"copy": "passthrough", "grayscale": "grayscale", "sobel": "sobel", "pipeline": "sobel"}[mode]]
        record = {"case": name, "mode": mode, "width": width, "height": height,
                  "status": "pass", "backends": {}}
        for backend in ("sw", "hw"):
            result = json.loads((out / f"{backend}.json").read_text())
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["check_count"], 7)
            self.assertEqual(result["failure_count"], 0)
            self.assertTrue(result["image_check"]["passed"])
            self.assertEqual(result["image_check"]["bytes_compared"], width * height * 3)
            self.assertEqual(result["image_check"]["mismatched_bytes"], 0)
            self.assertEqual((out / f"{backend}.output.rgb").read_bytes(), expected)
            record["backends"][backend] = {"checks": result["check_count"],
                                            "image_check": result["image_check"]}
            if backend == "hw":
                metrics = result["metrics"]
                self.assertEqual(metrics["roi_complete"], 1)
                self.assertGreater(metrics["roi_cycles"], 0)
                self.assertGreater(metrics["roi_retired"], 0)
                record["backends"][backend]["metrics"] = metrics
        self.evidence.append(record)

    def test_real_firmware_modes_shapes_and_known_images(self):
        rng = random.Random(20261008)
        odd = bytes(rng.randrange(256) for _ in range(7 * 5 * 3))
        for mode in ("copy", "grayscale", "sobel", "pipeline"):
            with self.subTest(mode=mode, width=7, height=5):
                self.execute("odd-random-" + mode, mode, 7, 5, odd)
        step = bytes(v for y in range(3) for x in range(3)
                     for v in ((0 if x == 0 else 255),) * 3)
        for mode in ("sobel", "pipeline"):
            with self.subTest(mode=mode, width=3, height=3):
                self.execute("minimum-step-" + mode, mode, 3, 3, step)
        for width, height in ((3, 11), (11, 3)):
            rgb = bytes(rng.randrange(256) for _ in range(width * height * 3))
            with self.subTest(width=width, height=height):
                self.execute(f"narrow-{width}-{height}", "pipeline", width, height, rgb)
        ramp = bytes(v for y in range(5) for x in range(7) for v in (10*x + 3*y,) * 3)
        self.execute("known-ramp", "pipeline", 7, 5, ramp)
        self.execute("constant", "sobel", 7, 5, bytes([177, 99, 28]) * 35)

    def test_timeout_invalidates_successful_camera_report(self):
        args = arguments(width=3, height=3, trace=True, trace_limit=2000)
        # camera_suite obtains its own simulator handle; use the validated cache
        # instead of asking it to rebuild under the temporary output directory.
        with patch.object(lab, "build_hardware", return_value=self.hardware):
            self.assertTrue(lab.camera_suite(args))
            directory = lab.BUILD / "camera"
            self.assertTrue((directory / "report.html").is_file())
            self.assertEqual(json.loads((directory / "report.json").read_text())["status"], "pass")
            for mode in ("copy", "grayscale", "sobel", "pipeline"):
                self.assertTrue((directory / (mode + "-trace.html")).is_file(), mode)
            args.max_cycles = 1
            self.assertFalse(lab.camera_suite(args))
        self.assertEqual(json.loads((directory / "report.json").read_text())["status"], "fail")
        for name in ("report.html", "copy.png", "grayscale.png", "sobel.png", "pipeline.png", "trace.html",
                     "copy-trace.html", "grayscale-trace.html", "sobel-trace.html", "pipeline-trace.html"):
            self.assertFalse((directory / name).exists(), name)
        self.assertNotIn("camera/report.html", (lab.BUILD / "index.html").read_text())
        failed = json.loads((lab.BUILD / "06_camera-copy-O2/hw.json").read_text())
        self.assertEqual(failed["status"], "fail")
        self.assertEqual(failed["metrics"]["reason"], "cycle_budget")
        self.evidence.append({"case": "timeout-after-success", "status": "expected failure",
                              "reason": failed["metrics"]["reason"], "stale_report_removed": True})

    def test_tracing_preserves_kernel_timing(self):
        args = arguments(width=3, height=3, camera_mode="pipeline")
        ok, out, _ = lab.run(args, self.hardware)
        self.assertTrue(ok)
        before = json.loads((out / "hw.json").read_text())["metrics"]
        signature = (out / "hw.signature").read_bytes()
        args.trace = True
        args.trace_limit = 500
        ok, out, _ = lab.run(args, self.hardware)
        self.assertTrue(ok)
        after = json.loads((out / "hw.json").read_text())["metrics"]
        for key in ("cycles", "retired", "roi_cycles", "roi_retired", "roi_start_cycle", "roi_end_cycle"):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual(signature, (out / "hw.signature").read_bytes())
        self.assertEqual(after["trace_cycles"], 500)
        self.assertEqual(after["trace_truncated"], 1)
        self.assertTrue((out / "trace.html").is_file())
        self.evidence.append({"case": "traced-versus-untraced", "status": "pass",
                              "timing_unchanged": True, "bounded_capture": 500})


if __name__ == "__main__":
    unittest.main()
