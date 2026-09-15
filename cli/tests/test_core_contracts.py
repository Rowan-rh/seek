"""通用核心的端到端契约测试。"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from seek_cli import agent_eval, chain
from seek_cli.commands import capabilities, chain as chain_cmd, plugin as plugin_cmd
from seek_cli.plugins import PluginMetadata, ProviderManifest, SeekPlugin
from seek_cli.plugins.registry import PluginRegistry


class ExamplePlugin(SeekPlugin):
    metadata = PluginMetadata(
        id="example",
        name="Example Provider",
        version="1.0.0",
        description="test plugin",
        providers=(ProviderManifest(
            id="example.logs",
            name="Example Logs",
            description="abstract log source",
            capabilities=("logs.query",),
        ),),
    )


class CoreContractTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_session_dir = chain._SESSION_DIR
        chain._SESSION_DIR = Path(self.temp_dir.name) / "sessions"

    def tearDown(self):
        chain._SESSION_DIR = self.old_session_dir
        self.temp_dir.cleanup()

    def _complete(self, sid, outputs, evidence=None):
        return chain.complete_step(sid, outputs=outputs, evidence=evidence,
                                   token_usage={"input_tokens": 10, "output_tokens": 5})

    def test_default_chain_is_vendor_neutral_and_has_stable_contract(self):
        chains = chain.list_chains()
        self.assertEqual(["default"], [item["name"] for item in chains])
        self.assertEqual(
            ["define-problem", "collect-evidence", "analyze-cause", "verify-and-report"],
            chains[0]["steps"],
        )
        self.assertEqual("generic.md", chains[0]["reportTemplate"])
        payload = capabilities.cmd_capabilities(None)["data"]
        self.assertIn("plugin", payload["commands"])
        self.assertEqual([], payload["plugins"])

    def test_session_lifecycle_requires_evidence_and_generates_report(self):
        session = chain.start_session("default", problem_description="接口返回 5xx")
        sid = session["session_id"]
        first = chain.get_current_step(sid)
        self.assertEqual("define-problem", first["name"])
        self._complete(sid, {"scope": "api", "impact": "partial", "time_window": "30m"})

        with self.assertRaises(chain.EvidenceValidationError):
            chain.complete_step(sid, {"evidence_summary": "x", "sources_checked": [], "limitations": "none"})
        self.assertEqual(2, chain.get_session(sid)["current_step"])

        evidence = {"status": "FOUND", "sources": [{"tool": "provider logs query", "reference": "q-1"}], "boundary": "30m/api"}
        self._complete(sid, {"evidence_summary": "5xx stack", "sources_checked": ["logs"], "limitations": "none"}, evidence)
        self._complete(sid, {"root_cause": "APPLICATION_FAILURE", "confidence": "medium", "counterevidence": "none"})
        self._complete(sid, {"verification": "reproduced", "status": "confirmed", "recommendation": "add regression test"}, evidence)

        completed = chain.get_session(sid)
        self.assertEqual("completed", completed["status"])
        self.assertEqual(4, len(completed["completed_steps"]))
        usage = chain.get_token_usage(sid)
        self.assertEqual(40, usage["totals"]["input_tokens"])
        report = chain.build_report(sid, "api-5xx")
        self.assertEqual("generic.md", report["template"]["name"])
        self.assertTrue(report["filename"].endswith("-api-5xx.md"))
        self.assertIn(sid, report["header_markdown"])

    def test_plugin_registry_discovers_external_plugins_without_core_provider(self):
        class EntryPoint:
            name = "example"
            value = "example_seek_plugin:plugin"

            def load(self):
                return ExamplePlugin

        registry = PluginRegistry()
        with patch("seek_cli.plugins.registry._entry_points", return_value=[EntryPoint()]):
            self.assertEqual(["example"], [item.metadata.id for item in registry.plugins()])
            self.assertEqual("example", registry.get_provider("example.logs").metadata.id)
        self.assertEqual("example", registry.as_dicts()[0]["id"])

    def test_broken_plugin_isolated_and_cli_plugin_list_is_json(self):
        class BrokenEntryPoint:
            name = "broken"
            value = "broken:plugin"

            def load(self):
                raise ImportError("optional dependency missing")

        registry = PluginRegistry()
        with patch("seek_cli.plugins.registry._entry_points", return_value=[BrokenEntryPoint()]):
            self.assertEqual([], registry.plugins())
            self.assertIn("ImportError: optional dependency missing", registry.load_errors()[0]["error"])
        result = plugin_cmd.cmd_plugin_list(None)
        self.assertEqual("ok", result["status"])
        self.assertEqual("seek.plugins", result["data"]["entryPointGroup"])

    def test_bundled_agent_scenarios_pass_replay(self):
        scenario_path = Path(__file__).resolve().parents[2] / "harness" / "scenarios" / "v1.json"
        scenarios = agent_eval.load_scenario_set(scenario_path)
        report = agent_eval.run_scenarios(scenarios)
        self.assertEqual("ok", report["status"])
        self.assertEqual(4, report["summary"]["total"])
        self.assertEqual(1.0, report["metrics"]["scenario_success_rate"])

    def test_cli_emits_json_for_capabilities(self):
        env = os.environ.copy()
        env["SEEK_HOME"] = self.temp_dir.name
        result = subprocess.run([sys.executable, "-m", "seek_cli.cli", "capabilities"],
                                capture_output=True, text=True, env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("ok", json.loads(result.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
