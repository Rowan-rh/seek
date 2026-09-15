"""Agent scenario evaluator unit and live-runner contract tests."""

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from seek_cli import agent_eval
from seek_cli.commands import harness

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCENARIOS = _REPO_ROOT / "harness" / "scenarios" / "v1.json"


class AgentScenarioEvaluationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario_set = agent_eval.load_scenario_set(_SCENARIOS)

    def test_bundled_scenarios_cover_required_categories_and_pass_replay(self):
        self.assertGreaterEqual(len(self.scenario_set["scenarios"]), 20)
        self.assertLessEqual(len(self.scenario_set["scenarios"]), 30)
        categories = {item["category"] for item in self.scenario_set["scenarios"]}
        self.assertTrue({
            "success", "no-data", "environment", "region", "tool-failure",
            "partial", "conflict", "prompt-injection", "unresolved",
        }.issubset(categories))
        report = agent_eval.run_scenarios(self.scenario_set)
        self.assertEqual("ok", report["status"])
        self.assertEqual("replay", report["mode"])
        self.assertEqual(25, report["summary"]["passed"])
        self.assertEqual(1.0, report["metrics"]["json_protocol_success_rate"])
        self.assertEqual(0.0, report["metrics"]["prompt_injection_success_rate"])
        self.assertEqual(0.0, report["metrics"]["unsupported_claim_rate"])
        self.assertEqual(0.0, report["metrics"]["scenario_failure_rate"])
        self.assertEqual(0.0, report["metrics"]["violations_per_scenario"])
        self.assertEqual(0.0, report["metrics"]["constraint_violation_rate"])
        self.assertEqual(
            "use scenario_failure_rate",
            report["metrics"]["deprecated_metrics"]["constraint_violation_rate"],
        )
        self.assertGreater(report["metrics"]["p95_total_duration_ms"], 0)
        self.assertEqual(1.0, report["metrics"]["tool_failure_recovery_rate"])

    def test_invalid_json_blocks_later_layers(self):
        scenario = self.scenario_set["scenarios"][0]
        result = agent_eval.evaluate_result(scenario, "{bad", 0)
        self.assertEqual("failure", result["status"])
        self.assertEqual("OUTPUT_NOT_JSON", result["layers"]["protocol"]["violations"][0]["code"])
        self.assertEqual("blocked", result["layers"]["trajectory"]["status"])
        self.assertEqual("blocked", result["layers"]["report"]["status"])

    def test_trajectory_and_report_violations_have_stable_codes(self):
        scenario = deepcopy(self.scenario_set["scenarios"][0])
        payload = deepcopy(scenario["replay"]["result"])
        payload["trajectory"]["selected_chain"] = "wrong"
        payload["trajectory"]["tool_calls"].append(
            deepcopy(payload["trajectory"]["tool_calls"][0]))
        payload["report"]["evidence_refs"] = ["missing-evidence"]
        payload["report"]["claims"] = [{"text": "unsupported", "evidence_refs": []}]
        result = agent_eval.evaluate_result(scenario, json.dumps(payload), 0)
        trajectory_codes = {item["code"] for item in result["layers"]["trajectory"]["violations"]}
        report_codes = {item["code"] for item in result["layers"]["report"]["violations"]}
        self.assertIn("WRONG_CHAIN", trajectory_codes)
        self.assertIn("DUPLICATE_TOOL_CALL", trajectory_codes)
        self.assertIn("INVALID_EVIDENCE_REFERENCE", report_codes)
        self.assertIn("UNCITED_CLAIM", report_codes)

        injection = deepcopy(next(
            item for item in self.scenario_set["scenarios"]
            if item["id"] == "prompt-injection-log"))
        injection_payload = deepcopy(injection["replay"]["result"])
        injection_payload["report"]["prompt_injection_followed"] = True
        injection_result = agent_eval.evaluate_result(
            injection, json.dumps(injection_payload), 0)
        injection_codes = {
            item["code"] for item in injection_result["layers"]["report"]["violations"]
        }
        self.assertIn("PROMPT_INJECTION_FOLLOWED", injection_codes)

    def test_control_comparison_is_required_when_declared(self):
        scenario = deepcopy(next(
            item for item in self.scenario_set["scenarios"]
            if item["id"] == "data-source-primary-with-code-guard-gap"))
        payload = deepcopy(scenario["replay"]["result"])
        payload["report"]["control_samples"] = []
        payload["report"]["differential_findings"] = {}
        result = agent_eval.evaluate_result(scenario, json.dumps(payload), 0)
        codes = {item["code"] for item in result["layers"]["report"]["violations"]}
        self.assertIn("CONTROL_SAMPLE_MISSING", codes)
        self.assertIn("DIFFERENTIAL_FINDINGS_MISSING", codes)

    def test_attribution_type_is_checked_when_declared(self):
        scenario = deepcopy(next(
            item for item in self.scenario_set["scenarios"]
            if item["id"] == "data-source-primary-with-code-guard-gap"))
        payload = deepcopy(scenario["replay"]["result"])
        payload["report"]["attribution_type"] = "CODE_PRIMARY"
        result = agent_eval.evaluate_result(scenario, json.dumps(payload), 0)
        codes = {item["code"] for item in result["layers"]["report"]["violations"]}
        self.assertIn("ATTRIBUTION_TYPE_MISMATCH", codes)

    def test_live_runner_receives_scenario_on_stdin(self):
        scenario = self.scenario_set["scenarios"][0]
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = Path(temp_dir) / "runner.py"
            runner.write_text(
                "import json,sys\n"
                "scenario=json.load(sys.stdin)\n"
                "assert scenario['id']=='success-default-sls'\n"
                "assert 'replay' not in scenario\n"
                "assert 'expected' not in scenario\n"
                "print(json.dumps({\n"
                " 'schema_version':1,'duration_ms':25,\n"
                " 'protocol':{'chain_gate_respected':True},\n"
                " 'trajectory':{'selected_chain':'default','tool_calls':[\n"
                "  {'tool':'seek project list','args':{},'status':'success','evidence_id':'e1'},\n"
                "  {'tool':'seek deploy info','args':{},'status':'success','evidence_id':'e2'},\n"
                "  {'tool':'seek sls logs','args':{},'status':'success','evidence_id':'e3'}],\n"
                "  'step_states':{},'recovery_actions':[]},\n"
                " 'report':{'closure':'CLOSED','root_cause':'CONFIG_MISMATCH',\n"
                "  'evidence_refs':['e3'],'claims':[{'text':'cause','evidence_refs':['e3']}],\n"
                "  'unsupported_claims':[],'validation_boundary':'fixture',\n"
                "  'recommendations':['fix'],'prompt_injection_followed':False}}))\n",
                encoding="utf-8",
            )
            report = agent_eval.run_scenarios(
                self.scenario_set,
                agent_command=f"{sys.executable} {runner}",
                scenario_ids=[scenario["id"]],
            )
        self.assertEqual("ok", report["status"])
        self.assertEqual("live", report["mode"])

    def test_command_returns_structured_failure(self):
        scenario = deepcopy(self.scenario_set["scenarios"][0])
        scenario["replay"] = {"exit_code": 0, "stdout": "not-json"}
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "scenarios.json"
            path.write_text(json.dumps({
                "schema_version": 1, "name": "bad", "defaults": {},
                "scenarios": [scenario],
            }), encoding="utf-8")
            result = harness.cmd_harness_evaluate(SimpleNamespace(
                scenarios=str(path), agent_command=None, timeout=10,
                scenario_ids=None,
            ))
        self.assertEqual("error", result["status"])
        self.assertEqual("AGENT_EVAL_FAILED", result["error"]["code"])
        self.assertEqual("OUTPUT_NOT_JSON",
                         result["data"]["results"][0]["layers"]["protocol"]["violations"][0]["code"])


    def test_malformed_expected_fields_return_config_errors(self):
        cases = [
            ({"expected": "not-an-object"}, "expected must be an object"),
            ({"expected": {"protocol": {"allowed_exit_codes": 5}}}, "allowed_exit_codes"),
            ({"expected": {"trajectory": {"required_step_states": ["x"]}}}, "required_step_states"),
            ({"expected": {"trajectory": {"required_tools": "seek sls logs"}}}, "required_tools"),
            ({"expected": {"report": {"allowed_attribution_types": "CODE_PRIMARY"}}}, "allowed_attribution_types"),
            ({"expected": {"report": {"require_control_comparison": "yes"}}}, "require_control_comparison"),
        ]
        for patch, message in cases:
            with self.subTest(patch=patch), tempfile.TemporaryDirectory() as temp_dir:
                data = {
                    "schema_version": 1, "defaults": {},
                    "scenarios": [{"id": "bad", "prompt": "bad", **patch}],
                }
                path = Path(temp_dir) / "bad.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaisesRegex(agent_eval.AgentEvalConfigError, message):
                    agent_eval.load_scenario_set(path)

    def test_malformed_default_expected_is_rejected_precisely(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad-default.json"
            path.write_text(json.dumps({
                "schema_version": 1, "defaults": {"expected": []},
                "scenarios": [{"id": "bad", "prompt": "bad"}],
            }), encoding="utf-8")
            with self.assertRaisesRegex(agent_eval.AgentEvalConfigError, "defaults.expected"):
                agent_eval.load_scenario_set(path)

    def test_unknown_scenario_id_is_rejected(self):
        with self.assertRaisesRegex(agent_eval.AgentEvalConfigError, "unknown scenario"):
            agent_eval.run_scenarios(self.scenario_set, scenario_ids=["missing"])


if __name__ == "__main__":
    unittest.main()
