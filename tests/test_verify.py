# =============================================================================
# HY-RV | test_verify
# Description: Verify the public CPU laboratory contract and preserve source-bound evidence.
# Purpose: Computer architecture and RTL design education and lab exercises.
# Maintained by: DSAL (Digital System Architecture Lab), Hanyang University
# Website: https://dsa.hanyang.ac.kr
# Supervisor: Prof. Ji-Hoon Kim (jhoonkim@hanyang.ac.kr)
# AI tools such as Codex or Claude may have assisted in creating or modifying
# this file. See applicable manifests and verification records for provenance.
# Preserve existing license, copyright, and original author notices.
# =============================================================================

"""Receipt integrity tests; no compiler or RTL simulator is launched."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verify


class VerificationReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "lab"
        self.rtl = self.root / "rtl"
        self.rtl.mkdir(parents=True)
        (self.rtl / "filelist.f").write_text("cpu.sv\n")
        (self.rtl / "cpu.sv").write_text("module cpu; endmodule\n")
        (self.root / "runtime").mkdir()
        (self.root / "runtime/start.S").write_text("_start: nop\n")
        self.build = self.root / "generated"
        self.output = self.build / "validation/run"

    def invoke(self, execute, gates=None):
        with patch.object(verify, "execute_gate", side_effect=execute), \
             patch.object(verify, "tool_provenance", return_value={}), \
             patch.object(verify, "gate_plan", return_value=gates or [("doctor", ["fake"]), ("smoke", ["fake"]) ]):
            code = verify.run_verification(self.root, self.rtl, self.build, self.output)
        return code, json.loads((self.output / "receipt.json").read_text())

    def test_failure_stops_gates_and_preserves_failed_report(self):
        calls = []
        def execute(command, cwd, env, log):
            calls.append(command)
            log.write_text("diagnostic output\n")
            (self.build / "regression.json").write_text('{"status":"fail"}')
            return 7
        code, receipt = self.invoke(execute, [("smoke", ["bad"]), ("regression", ["never"])])
        self.assertEqual(code, 7)
        self.assertEqual(calls, [["bad"]])
        self.assertEqual(receipt["status"], "fail")
        self.assertEqual(receipt["gates"][0]["exit_code"], 7)
        self.assertTrue((self.output / "01-smoke/reports/regression.json").is_file())
        self.assertFalse(receipt["source_drift"]["detected"])

    def test_smoke_report_survives_full_regression_overwrite(self):
        def execute(command, cwd, env, log):
            self.assertEqual(env["LAB_RTL_DIR"], str(self.rtl))
            self.assertEqual(env["LAB_BUILD_DIR"], str(self.build))
            log.write_text("passed\n")
            (self.build / "regression.json").write_text(json.dumps({"suite": command[0]}))
            return 0
        code, receipt = self.invoke(execute, [("smoke", ["smoke"]), ("regression", ["full"])])
        self.assertEqual(code, 0)
        smoke = json.loads((self.output / "01-smoke/reports/regression.json").read_text())
        self.assertEqual(smoke["suite"], "smoke")
        self.assertEqual(receipt["browser_ui"]["status"], "not_run")

    def test_source_drift_rejects_otherwise_successful_run(self):
        def execute(command, cwd, env, log):
            log.write_text("passed\n")
            (self.root / "runtime/start.S").write_text("_start: ebreak\n")
            return 0
        code, receipt = self.invoke(execute)
        self.assertEqual(code, 1)
        self.assertEqual(receipt["source_drift"]["changes"], {"framework": ["runtime/start.S"]})

    def test_replacement_rtl_reaches_every_make_gate(self):
        gates = verify.gate_plan(self.rtl)
        self.assertEqual([name for name, _ in gates][:3], ["doctor", "compare", "smoke"])
        checked = 0
        for _, command in gates:
            if command[1:2] == ["--no-print-directory"]:
                self.assertIn(f"RTL_DIR={self.rtl}", command)
                checked += 1
        self.assertEqual(checked, len(gates) - 5)
        self.assertEqual(len(verify.gate_plan(self.rtl, True)), 3)

    def test_current_manifest_is_distinct_from_historical_pin(self):
        pin = self.root / "provenance/p1-static-core.json"
        pin.parent.mkdir()
        pin.write_text('{"description":"current P1 manifest","rtl_files_sha256":{"cpu.sv":"known"}}')
        with patch("core_config.rtl_identity", return_value={"cpu.sv": "known"}), \
                patch("core_config.source_hash", return_value="actual-source"):
            identity = verify.pin_identity(self.root, {})
        self.assertEqual(identity["status"], "current_p1_manifest")
        self.assertEqual(identity["sha256"], verify.sha256(pin))
        self.assertTrue(identity["matches_manifest"])
        self.assertNotIn("matches_snapshot", identity)


if __name__ == "__main__":
    unittest.main()
