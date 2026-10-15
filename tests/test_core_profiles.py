# =============================================================================
# HY-RV | test_core_profiles
# Description: Verify explicit P1 elaboration, cache identity, and configuration rejection.
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See applicable manifests and verification records for provenance.
# Preserve existing license, copyright, and original author notices.
# =============================================================================
"""Configuration tests inspect actual build arguments without launching a simulator."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core_config
import lab


class CoreProfileTests(unittest.TestCase):
    def test_default_is_ant_without_early_jal_and_ii1_memory(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            config = core_config.resolve()
        self.assertEqual(config["preset"], "ant_j0")
        self.assertEqual(config["memory_adapter"], "ii1")
        self.assertEqual(config["effective_parameters"]["EARLY_JAL_EN"], 0)
        self.assertEqual(config["effective_parameters"]["INSN_QUEUE_DEPTH"], 0)

    def test_all_presets_match_canonical_source_and_configuration_hashes(self):
        pin = json.loads((ROOT / "provenance/p1-static-core.json").read_text())
        actual = core_config.rtl_identity(ROOT / "rtl")
        self.assertEqual(actual, pin["rtl_files_sha256"])
        self.assertEqual(core_config.source_hash(ROOT / "rtl"), pin["source_hash"])
        for preset in core_config.PRESETS:
            with self.subTest(preset=preset):
                config = core_config.resolve(preset, "ii1")
                self.assertEqual(config["model_id"], pin["presets"][preset]["model_id"])
                self.assertEqual(config["effective_parameters"], pin["presets"][preset]["effective_parameters"])
                self.assertEqual(core_config.configuration_sha256(config),
                                 pin["presets"][preset]["preset_config_sha256"])

    def test_explicit_selection_overrides_environment_and_invalid_values_fail(self):
        with mock.patch.dict(os.environ, {"LAB_CORE_PRESET": "btfnt_j1", "LAB_MEMORY_ADAPTER": "frozen"}):
            selected = core_config.resolve("ant_j0", "ii1")
            inherited = core_config.resolve()
        self.assertEqual(selected["preset"], "ant_j0")
        self.assertEqual(selected["memory_adapter"], "ii1")
        self.assertEqual(inherited["preset"], "btfnt_j1")
        self.assertEqual(inherited["memory_adapter"], "frozen")
        for preset, adapter in (("dynamic", "ii1"), ("ANT", "ii1"), ("ant_j0", "missing")):
            with self.subTest(preset=preset, adapter=adapter), self.assertRaises(ValueError):
                core_config.resolve(preset, adapter)

    def test_parameterless_replacement_cannot_claim_btfnt_or_p1_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            rtl = Path(temporary)
            (rtl / "filelist.f").write_text("teaching_cpu.sv\n")
            (rtl / "teaching_cpu.sv").write_text("module teaching_cpu; endmodule\n")
            selected = core_config.resolve("ant_j0", "ii1", rtl)
            self.assertEqual(selected["preset"], "external")
            self.assertNotIn("p1_f0", selected["model_id"])
            with self.assertRaisesRegex(ValueError, "no P1"):
                core_config.resolve("btfnt_j0", "ii1", rtl)

    def test_compilation_flags_and_adapter_change_actual_cache_identity(self):
        commands, receipts, keys = [], {}, set()
        with tempfile.TemporaryDirectory() as temporary:
            def compile_model(command, *unused, **kwargs):
                values = list(map(str, command))
                commands.append(values)
                directory = Path(values[values.index("--Mdir") + 1])
                (directory / "Vtb_cpu_lab").write_bytes(b"fixture simulator")
            with mock.patch.object(lab, "BUILD", Path(temporary)), \
                    mock.patch.object(lab, "tool", return_value="verilator"), \
                    mock.patch.object(lab, "cxx_compiler", return_value="g++"), \
                    mock.patch.object(lab, "version", return_value="fixture compiler version"), \
                    mock.patch.object(lab, "require", side_effect=compile_model):
                for adapter in ("ii1", "frozen"):
                    for preset in core_config.PRESETS:
                        args = argparse.Namespace(rtl_dir=None, core_preset=preset, memory_adapter=adapter)
                        binary, key = lab.build_hardware(args)
                        keys.add(key)
                        identity = json.loads((binary.parent / "build.json").read_text())
                        receipts[preset, adapter] = identity
                        expected = core_config.resolve(preset, adapter)
                        self.assertEqual(identity["core_configuration"], expected)
                        self.assertEqual(identity["configuration_sha256"], core_config.configuration_sha256(expected))
                        self.assertIn(str(core_config.adapter_path(adapter)), commands[-1])
                        for name, value in expected["parameters"].items():
                            self.assertIn(f"+define+HY_RV_{name}={value}", commands[-1])
                        lab.build_hardware(args)
                self.assertEqual(len(keys), 8)
                self.assertEqual(len(commands), 8, "Unchanged builds must reuse their own receipt-bound cache")
                # A cached binary is not accepted when its saved identity is changed.
                identity["rtl_source_hash"] = "tampered"
                (binary.parent / "build.json").write_text(json.dumps(identity))
                with self.assertRaisesRegex(lab.LabError, "cache receipt"):
                    lab.build_hardware(args)


if __name__ == "__main__":
    unittest.main()
