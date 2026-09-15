"""Regression tests for control-sample root-cause attribution contracts."""

import json
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHAINS = _REPO_ROOT / "cli" / "seek_cli" / "resources" / "chains" / "default.json"


class RootCauseAttributionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chains = json.loads(_CHAINS.read_text(encoding="utf-8"))["chains"]

    def test_default_chain_requires_control_sample_before_root_cause(self):
        steps = self.chains["default"]["steps"]
        names = [step["name"] for step in steps]
        self.assertEqual(
            ["identify-service", "query-deploy", "query-logs", "query-trace",
             "compare-control-samples", "analyze-root-cause"],
            names,
        )
        comparison = steps[4]
        self.assertTrue(comparison["evidenceRequired"])
        for output in (
            "abnormal_sample", "control_samples", "sample_comparability",
            "differential_findings", "counterevidence", "attribution_type",
            "attribution_confidence",
        ):
            self.assertIn(output, comparison["outputs"])
        root_cause = steps[5]
        self.assertEqual(5, root_cause["constraints"]["requires_step"])
        for field in ("direct_failure_point", "primary_trigger", "contributing_factor"):
            self.assertIn(field, root_cause["outputs"])

    def test_alert_ticket_carries_comparison_into_report(self):
        steps = {step["name"]: step for step in self.chains["alert-ticket"]["steps"]}
        deep = steps["deep-investigate"]
        report = steps["generate-report"]
        for field in (
            "control_samples", "comparison_dimensions", "differential_findings", "counterevidence",
            "attribution_type", "attribution_confidence",
        ):
            self.assertIn(field, deep["outputs"])
            self.assertIn(field, report["requiredInputs"])
        self.assertIn("INSUFFICIENT_EVIDENCE", deep["agentInstructions"])


if __name__ == "__main__":
    unittest.main()
