"""Reliability hardening regression tests."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from seek_cli import chain, config, error_log
from seek_cli.commands import project as project_commands
from seek_cli.commands import sls
from seek_cli.commands import chain as chain_commands
from seek_cli.integrations import a1_client, sls_client


class ProjectConfigMergeTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_builtin = config._BUILTIN_CONFIG
        self.old_user = config._USER_CONFIG
        root = Path(self.temp_dir.name)
        config._BUILTIN_CONFIG = root / "builtin.json"
        config._USER_CONFIG = root / "user.json"
        config._BUILTIN_CONFIG.write_text(json.dumps({"projects": {
            "app": {"description": "old", "a1AppName": "a1", "environments": {
                "daily": {"platforms": [{"type": "sls", "config": {}}]},
                "prod": {"platforms": [{"type": "sls", "config": {}}]},
            }},
        }}), encoding="utf-8")

    def tearDown(self):
        config._BUILTIN_CONFIG = self.old_builtin
        config._USER_CONFIG = self.old_user
        self.temp_dir.cleanup()

    def test_user_patch_preserves_builtin_project_fields(self):
        config.add_project("app", description="new")
        project = config.get_project("app")
        self.assertEqual("new", project["description"])
        self.assertEqual("a1", project["a1AppName"])
        self.assertEqual({"daily", "prod"}, set(project["environments"]))
        stored = json.loads(config._USER_CONFIG.read_text(encoding="utf-8"))
        self.assertNotIn("a1AppName", stored["projects"]["app"])

    def test_invalid_project_structure_has_clear_error(self):
        invalid_projects = [
            {"environments": []},
            {"environments": {"prod": []}},
            {"environments": {"prod": {"platforms": {}}}},
            {"environments": {"prod": {"platforms": ["sls"]}}},
            {"environments": {"prod": {"platforms": [{"config": []}]}}},
        ]
        for project in invalid_projects:
            with self.subTest(project=project):
                config._USER_CONFIG.write_text(
                    json.dumps({"projects": {"app": project}}), encoding="utf-8"
                )
                with self.assertRaises(config.ProjectConfigError):
                    config.list_projects()

    def _args(self, **kwargs):
        values = {"project": "app", "env": "prod", "level": None, "keyword": None,
                  "trace_id": None, "time": "15m", "max": 100}
        values.update(kwargs)
        return SimpleNamespace(**values)

    def test_logs_validates_max_before_query(self):
        with patch.object(sls.config, "get_project") as get_project:
            result = sls.cmd_sls_logs(self._args(max=0))
        self.assertEqual("BAD_ARGUMENT", result["error"]["code"])
        get_project.assert_not_called()

    def test_configured_multi_store_truncation_is_per_store(self):
        project = {"environments": {"prod": {"platforms": [
            {"type": "sls", "name": "a", "config": {"endpoint": "e", "project": "p", "logstore": "a"}},
            {"type": "sls", "name": "b", "config": {"endpoint": "e", "project": "p", "logstore": "b"}},
        ]}}}
        response = {"logs": [{"x": "1"}] * 60, "count": 60, "query": "q", "timeRange": {}}
        with patch.object(sls_client, "query_logs", return_value=response):
            result = sls_client.query_by_config(project, "prod", "q", max_results=100)
        self.assertFalse(result["truncated"])
        self.assertEqual([], result["truncatedLogstores"])


class ProjectAddArgumentTest(unittest.TestCase):
    def _args(self, **kwargs):
        values = {"name": "app", "desc": None, "repo": None, "a1_app": None,
                  "sls_daily": None, "sls_pre": None, "sls_prod": None}
        values.update(kwargs)
        return SimpleNamespace(**values)

    def test_invalid_sls_config_returns_bad_argument(self):
        # --sls-xxx 格式非法属于用户输入错误，不得落入 INTERNAL_ERROR
        result = project_commands.cmd_project_add(
            self._args(sls_daily="only-two/parts"))
        self.assertEqual("error", result["status"])
        self.assertEqual("BAD_ARGUMENT", result["error"]["code"])
        self.assertIn("invalid SLS config", result["error"]["message"])


class ErrorLogContextSanitizeTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_dir = error_log._LOG_DIR
        self.old_file = error_log._LOG_FILE
        error_log._LOG_DIR = Path(self.temp_dir.name)
        error_log._LOG_FILE = error_log._LOG_DIR / "errors.jsonl"

    def tearDown(self):
        error_log._LOG_DIR = self.old_dir
        error_log._LOG_FILE = self.old_file
        self.temp_dir.cleanup()

    def _last_entry(self):
        entries = error_log.read_errors(limit=1)
        self.assertTrue(entries)
        return entries[0]

    def test_context_masks_sensitive_keys_and_truncates_long_values(self):
        error_log.log_error(
            "cmd x", "CODE", "msg",
            context={"password": "secret-value", "query": "x" * 3000,
                     "note": "ok", "nested": {"a": 1}})
        context = self._last_entry()["context"]
        self.assertEqual("***", context["password"])
        self.assertEqual(2000, len(context["query"]))
        self.assertEqual("ok", context["note"])
        self.assertEqual({"a": 1}, context["nested"])

    def test_nested_and_camel_case_sensitive_keys_are_masked(self):
        error_log.log_error(
            "cmd x", "CODE", "msg",
            context={"response": {"accessKeySecret": "secret", "items": [{"securityToken": "tok"}]}})
        context = self._last_entry()["context"]
        self.assertEqual("***", context["response"]["accessKeySecret"])
        self.assertEqual("***", context["response"]["items"][0]["securityToken"])

    def test_write_failure_does_not_override_command_error(self):
        with patch.object(error_log, "_log_lock", side_effect=PermissionError("denied")):
            error_log.log_error("harness check", "HARNESS_NOT_READY", "storage denied")

    def test_context_budget_truncates_large_and_deep_values(self):
        context = {"items": [{"value": "x" * 100} for _ in range(error_log._CONTEXT_MAX_NODES * 2)]}
        nested = value = {}
        for _ in range(error_log._CONTEXT_MAX_DEPTH + 2):
            nested["child"] = {}
            nested = nested["child"]
        context["deep"] = value
        error_log.log_error("cmd x", "CODE", "msg", context=context)
        entry = self._last_entry()
        serialized = json.dumps(entry, ensure_ascii=False)
        self.assertLessEqual(len(serialized.encode("utf-8")), error_log._CONTEXT_MAX_BYTES + 1000)
        self.assertIn(error_log._CONTEXT_TRUNCATED, serialized)
        self.assertEqual("***", error_log._sanitize_context({"accessKeySecret": "secret"})["accessKeySecret"])

    def test_non_dict_context_is_truncated(self):
        error_log.log_error("cmd x", "CODE", "msg", context="y" * 5000)
        context = self._last_entry()["context"]
        self.assertEqual(2000, len(context))

    def test_invalid_time_ranges_return_value_errors(self):
        for value in ("1700000000,", ",1700001000", "1,2,3", "1700001000,1700000000"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    sls_client.parse_time_range(value)


class A1MatchingTest(unittest.TestCase):
    def test_prod_does_not_match_non_prod_and_handles_none(self):
        pipelines = [
            {"pipelineId": 1, "pipelineName": "非正式发布", "latestPipelineInstanceId": 1},
            {"pipelineId": 2, "pipelineName": "正式发布", "latestPipelineInstanceId": 2},
            {"pipelineId": 3, "pipelineName": None},
        ]
        with patch.object(a1_client, "list_pipelines", return_value=pipelines), \
             patch.object(a1_client, "get_pipeline_branch", return_value={"branch": "main"}) as branch:
            result = a1_client.query_env_deploy("app", "prod")
        self.assertEqual(1, result["matched_count"])
        branch.assert_called_once_with("app", 2)


class ChainReliabilityTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_dir = chain._SESSION_DIR
        chain._SESSION_DIR = Path(self.temp_dir.name) / "sessions"

    def tearDown(self):
        chain._SESSION_DIR = self.old_dir
        self.temp_dir.cleanup()

    def test_completed_session_step_returns_completed_error(self):
        session = chain.start_session("default", problem_description="error")
        session_id = session["session_id"]
        payloads = [
            {"target_project": "p"},
            {"deployed_branch": "b", "deployed_commit": "c", "deploy_time": "t", "recent_changes": [], "environment": "prod"},
            {"error_logs": [], "exception_stack": "", "log_patterns": [], "timeline": []},
            {"call_chain_analysis": "", "upstream_downstream": [], "trace_info": {}},
            {"abnormal_sample": {}, "control_samples": [], "sample_comparability": "",
             "comparison_dimensions": [], "differential_findings": {},
             "counterevidence": [], "attribution_type": "INSUFFICIENT_EVIDENCE",
             "attribution_confidence": "low"},
            {"root_cause": "", "direct_failure_point": "", "primary_trigger": "",
             "contributing_factor": "", "attribution_type": "INSUFFICIENT_EVIDENCE",
             "attribution_confidence": "low", "recommendation": "", "urgency": ""},
        ]
        for payload in payloads:
            chain.complete_step(session_id, payload, evidence={
                "status": "FOUND",
                "sources": [{"tool": "test", "reference": "fixture"}],
                "boundary": "unit test fixture",
            })
        result = chain_commands.cmd_chain_step(SimpleNamespace(session=session_id))
        self.assertEqual("SESSION_COMPLETED", result["error"]["code"])


if __name__ == "__main__":
    unittest.main()
