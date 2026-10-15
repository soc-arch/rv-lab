# =============================================================================
# HY-RV | test_viewer_core_identity
# Description: Check that rendered architecture labels follow the actual CPU identity.
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See applicable manifests and verification records for provenance.
# Preserve existing license, copyright, and original author notices.
# =============================================================================
"""Render-only fixtures assert labels; they are not CPU measurements."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import core_config
from viewer import render, catalog


class ViewerCoreIdentityTests(unittest.TestCase):
    @staticmethod
    def label(diagram, name):
        root = ET.fromstring(diagram)
        element = root.find(f".//*[@id='{name}']")
        if element is None:
            raise AssertionError(f"Missing architecture identity label: {name}")
        return "".join(element.itertext())

    def test_all_preset_diagrams_use_the_selected_branch_and_early_jal_values(self):
        for preset in core_config.PRESETS:
            with self.subTest(preset=preset):
                config = core_config.resolve(preset, "ii1")
                diagram = render._diagram({"core_configuration": config})
                expected = "BTFNT" if preset.startswith("btfnt") else "ANT"
                self.assertIn(expected, self.label(diagram, "value-bp-policy").upper())
                state = self.label(diagram, "value-early-jal").upper()
                self.assertIn("ON" if preset.endswith("j1") else "OFF", state)
                self.assertIn("P1", self.label(diagram, "value-architecture-title"))

    def test_external_and_missing_identity_are_reference_views(self):
        for metadata in ({}, {"core_configuration": {"model_id": "external_memory_v1_cpu", "preset": "external",
                             "configuration_status": "parameterless_public_contract", "effective_parameters": {}}}):
            with self.subTest(metadata=metadata):
                diagram = render._diagram(metadata)
                self.assertIn("reference", self.label(diagram, "value-architecture-title").lower())
                self.assertNotIn("Early JAL OFF", self.label(diagram, "value-early-jal"))

    def test_downloaded_svg_and_embedded_svg_are_the_same_selected_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            trace = directory / "fixture.jsonl"
            trace.write_text(json.dumps(dict(cycle=1, fetch={}, execute={}, stages={}, units={}, regs={},
                                             memory={}, commit={}, redirect={})) + "\n")
            assembly = directory / "fixture.dis"
            assembly.write_text("80000000: 00000013 nop\n")
            config = core_config.resolve("btfnt_j1", "ii1")
            render.generate(trace, assembly, directory / "fixture.html",
                            {"title": "Render-only fixture", "core_configuration": config})
            svg = (directory / "microarchitecture.svg").read_text()
            html = (directory / "fixture.html").read_text()
            self.assertIn(svg, html)
            self.assertIn("BTFNT", self.label(svg, "value-bp-policy"))
            self.assertIn("ON", self.label(svg, "value-early-jal"))

    def test_gallery_refresh_and_offline_export_preserve_actual_preset_labels(self):
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            folder = build / "04_muldiv-O2"
            folder.mkdir()
            trace = folder / "trace.jsonl"
            trace.write_text(json.dumps(dict(cycle=1, fetch={}, execute={}, stages={}, units={}, regs={},
                                             memory={}, commit={}, redirect={})) + "\n")
            assembly = folder / "program.dis"
            assembly.write_text("80000000: 00000013 nop\n")
            config = core_config.resolve("btfnt_j1", "ii1")
            render.generate(trace, assembly, folder / "trace.html",
                            {"title": "Render-only fixture", "status": "pass", "elf_sha256": "fixture",
                             "core_configuration": config})
            (folder / "build.json").write_text(json.dumps({"elf_sha256": "fixture"}))
            (folder / "hw.json").write_text(json.dumps({"status": "pass", "elf_sha256": "fixture", "metrics": {}}))
            for _ in range(2):
                catalog.refresh(build)
                svg = (folder / "microarchitecture.svg").read_text()
                self.assertIn("BTFNT", self.label(svg, "value-bp-policy"))
                self.assertIn("ON", self.label(svg, "value-early-jal"))
                self.assertIn(svg, (folder / "trace.html").read_text())
                self.assertIn(svg, (build / "muldiv/trace.html").read_text())
            archive = catalog.export_reports(build)
            with zipfile.ZipFile(archive) as bundle:
                svg = bundle.read("04_muldiv-O2/microarchitecture.svg").decode()
                self.assertIn("ON", self.label(svg, "value-early-jal"))
                self.assertIn("BTFNT", self.label(svg, "value-bp-policy"))


if __name__ == "__main__":
    unittest.main()
