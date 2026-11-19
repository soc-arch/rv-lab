# =============================================================================
# HY-RV | test_extensions
# Description: Tool-free checks for the Lab 09/10 extension package and its isolation from Labs 01-08.
#
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
#
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See the applicable manifests and verification records for
# file-specific provenance, revision history, and validation evidence.
# Preserve existing license, copyright, and original author notices.
# =============================================================================
"""No RISC-V tools or simulators needed; safe for continuous integration."""
import argparse
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core_config  # noqa: E402
import extensions  # noqa: E402

ENCODINGS = {  # name: (MATCH, MASK) from ext/README.md
    "xdot4": (0x0200000B, 0xFE00707F),
    "xacc.clr": (0x0000002B, 0xFFFFFFFF),
    "xacc.dot4": (0x0200002B, 0xFE007FFF),
    "xacc.rd": (0x0400002B, 0xFFFFF07F),
}


def hex_words(text):
    return {int(x.replace("_", ""), 16) for x in re.findall(r"0x([0-9A-Fa-f_]{8,9})\b", text)} | \
           {int(x.replace("_", ""), 16) for x in re.findall(r"32'h([0-9A-Fa-f_]{8,9})\b", text)}


class BaseLabsUnchanged(unittest.TestCase):
    def test_bundled_rtl_has_no_extension(self):
        self.assertFalse((ROOT / "rtl" / core_config.EXTENSION_FILE).exists())
        for preset in core_config.PRESETS:
            config = core_config.resolve(preset, "ii1")
            self.assertNotIn("extension", config)
            self.assertFalse(any("XACC" in flag for flag in config["compile_flags"]))

    def test_latency_rejected_for_bundled_cpu(self):
        with self.assertRaises(ValueError):
            core_config.resolve("ant_j0", "ii1", None, 4)

    def test_no_name_suffix_without_extension(self):
        args = argparse.Namespace(ext=None, rtl_dir=None, xacc_latency=None)
        self.assertEqual(extensions.name_suffix(args), "")
        args.rtl_dir = str(ROOT / "rtl")
        self.assertEqual(extensions.name_suffix(args), "")


class ExtensionPackage(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="rv-lab-ext-"))
        for name in ("rtl", "ext"):
            shutil.copytree(ROOT / name, self.temp / name)
        self.saved_root = extensions.ROOT
        extensions.ROOT = self.temp

    def tearDown(self):
        extensions.ROOT = self.saved_root
        shutil.rmtree(self.temp)

    def init(self, lab):
        extensions.init(argparse.Namespace(lab=lab, force=False), RuntimeError)
        return self.temp / "student" / f"lab{lab}" / "rtl"

    def test_init_creates_complete_copy_with_expected_todos(self):
        for lab, extension, todos in (("09", "xdot4", 3), ("10", "xacc", 4)):
            rtl = self.init(lab)
            for line in (rtl / "filelist.f").read_text().splitlines():
                if line.strip() and not line.startswith("#"):
                    self.assertTrue((rtl / line.strip()).is_file(), f"lab {lab}: {line}")
            found = set()
            for path in rtl.rglob("*.sv"):
                found |= set(re.findall(rf"TODO\(lab{lab}-(\d)\)", path.read_text()))
            self.assertEqual(found, {str(i) for i in range(1, todos + 1)}, lab)
            manifest, _ = core_config.extension_manifest(rtl)
            self.assertEqual(manifest["extension"], extension)
            config = core_config.resolve("ant_j0", "ii1", rtl)
            self.assertEqual(config["extension"]["name"], extension)

    def test_init_refuses_to_overwrite_work(self):
        rtl = self.init("09")
        (rtl / "mine.txt").write_text("student work")
        with self.assertRaises(RuntimeError):
            self.init("09")
        extensions.init(argparse.Namespace(lab="09", force=True), RuntimeError)
        backups = list(rtl.parent.glob("rtl.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "mine.txt").read_text(), "student work")

    def test_latency_only_for_lab10(self):
        lab09, lab10 = self.init("09"), self.init("10")
        with self.assertRaises(ValueError):
            core_config.resolve("ant_j0", "ii1", lab09, 2)
        config = core_config.resolve("ant_j0", "ii1", lab10, 4)
        self.assertIn("+define+HY_RV_XACC_LATENCY=4", config["compile_flags"])
        self.assertEqual(core_config.resolve("ant_j0", "ii1", lab10)["extension"]["xacc_latency"], 1)
        with self.assertRaises(ValueError):
            core_config.resolve("ant_j0", "ii1", lab10, 0)


class EncodingsAgree(unittest.TestCase):
    def test_contract_spike_model_and_rtl_agree(self):
        readme = hex_words((ROOT / "ext/README.md").read_text())
        spike = (ROOT / "ext/spike/hyrv_ext.cc").read_text()
        coproc = hex_words((ROOT / "ext/lab10/overlay/coproc/xacc_coproc.sv").read_text())
        for name, (match, mask) in ENCODINGS.items():
            self.assertIn(match, readme, name)
            self.assertIn(mask, readme, name)
            self.assertRegex(spike, rf"describe\(0x{match:08X}, 0x{mask:08X},", name)
            if name.startswith("xacc"):
                self.assertIn(match, coproc, name)
                self.assertIn(mask, coproc, name)

    def test_headers_emit_the_documented_fields(self):
        xdot4 = (ROOT / "ext/include/xdot4.h").read_text()
        xacc = (ROOT / "ext/include/xacc.h").read_text()
        self.assertIn(".insn r CUSTOM_0, 0, 1, %0, %1, %2", xdot4)
        self.assertIn(".insn r CUSTOM_1, 0, 0, x0, x0, x0", xacc)
        self.assertIn(".insn r CUSTOM_1, 0, 1, x0, %0, %1", xacc)
        self.assertIn(".insn r CUSTOM_1, 0, 2, %0, x0, x0", xacc)

    def test_reference_vectors(self):
        def dot4(a, b):
            s = lambda v, i: ((v >> (8 * i)) & 0xFF) - (256 if (v >> (8 * i)) & 0x80 else 0)
            return sum(s(a, i) * s(b, i) for i in range(4))
        self.assertEqual(dot4(0x04030201, 0x08070605), 70)
        self.assertEqual(dot4(0xFC03FE01, 0x02FF0403), -16)
        self.assertEqual(dot4(0x80808080, 0x80808080), 65536)
        self.assertEqual(dot4(0x80808080, 0x7F7F7F7F), -65024)


if __name__ == "__main__":
    unittest.main()
