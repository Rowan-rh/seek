"""排查复盘优化项回归测试（v0.4.0）。

覆盖：
- sls: 人类可读时间窗解析、--query-file 解析、索引形态探测警告、indexHint
- doctor: --liveness-window 参数校验
- deploy: 环境同义词扩展、deploy branch 真实部署分支
- chain: cron-task-health 链路与首步 problem 输入
"""

import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from seek_cli import chain
from seek_cli.commands import doctor, sls
from seek_cli.integrations import a1_client, sls_client


class TimeRangeParseTest(unittest.TestCase):
    def test_absolute_human_readable_range(self):
        from_t, to_t = sls_client._parse_time_range(
            "2026-08-03 00:00:00,2026-08-10 00:00:00")
        self.assertEqual(7 * 86400, to_t - from_t)

    def test_date_only_range(self):
        from_t, to_t = sls_client._parse_time_range("2026-08-03,2026-08-04")
        self.assertEqual(86400, to_t - from_t)

    def test_unix_range_still_supported(self):
        self.assertEqual((1, 2), sls_client._parse_time_range("1,2"))

    def test_relative_still_supported(self):
        from_t, to_t = sls_client._parse_time_range("15m")
        self.assertAlmostEqual(15 * 60, to_t - from_t, delta=2)

    def test_invalid_datetime_raises(self):
        with self.assertRaises(ValueError):
            sls_client._parse_time_range("昨天,今天")


class ResolveQueryTest(unittest.TestCase):
    def _args(self, **kwargs):
        values = {"query": None, "query_file": None}
        values.update(kwargs)
        return SimpleNamespace(**values)

    def test_query_file_reads_utf8_sql(self):
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False,
                                         encoding="utf-8") as f:
            f.write("* | select date_format(from_unixtime(__time__), '%Y-%m-%d')\n"
                    "where message like '%指标同步%'\n")
            path = f.name
        query, err = sls._resolve_query(self._args(query_file=path))
        Path(path).unlink()
        self.assertEqual("", err)
        self.assertIn("指标同步", query)
        self.assertFalse(query.endswith("\n"))

    def test_query_and_query_file_conflict(self):
        _, err = sls._resolve_query(self._args(query="q", query_file="f.sql"))
        self.assertIn("mutually exclusive", err)

    def test_missing_query_is_bad_argument(self):
        _, err = sls._resolve_query(self._args())
        self.assertIn("required", err)

    def test_query_file_stdin(self):
        with patch.object(sls.sys, "stdin", io.StringIO("level: ERROR")):
            query, err = sls._resolve_query(self._args(query_file="-"))
        self.assertEqual("", err)
        self.assertEqual("level: ERROR", query)


class IndexWarningTest(unittest.TestCase):
    def test_no_fulltext_index_warns_on_empty_keyword_query(self):
        summary = {"exists": True, "fullText": False,
                   "indexedFields": ["level"], "error": None}
        with patch.object(sls_client, "get_index_summary", return_value=summary):
            warns, check = sls_client._empty_result_index_check(
                "e", "p", "ls", "MetricSyncTask")
        self.assertEqual(1, len(warns))
        self.assertIn("无全文索引", warns[0])
        self.assertIn("level", warns[0])
        self.assertEqual(summary, check)

    def test_sql_query_skips_index_probe(self):
        with patch.object(sls_client, "get_index_summary") as probe:
            warns, check = sls_client._empty_result_index_check(
                "e", "p", "ls", "* | select count(*)")
        self.assertEqual([], warns)
        self.assertIsNone(check)
        probe.assert_not_called()

    def test_fulltext_ok_warns_tokenizer_mismatch_on_empty(self):
        summary = {"exists": True, "fullText": True,
                   "indexedFields": ["message", "level"], "error": None}
        with patch.object(sls_client, "get_index_summary", return_value=summary):
            warns, check = sls_client._empty_result_index_check(
                "e", "p", "ls", "MetricSyncTask")
        self.assertEqual(1, len(warns))
        self.assertIn("分词", warns[0])
        self.assertIn("like", warns[0])
        self.assertEqual(summary, check)

    def test_index_hint_short_circuits_probe(self):
        with patch.object(sls_client, "get_index_summary") as probe:
            warns, _ = sls_client._empty_result_index_check(
                "e", "p", "ls", "DataSyncTask", index_hint="message 无索引")
        self.assertIn("message 无索引", warns[0])
        probe.assert_not_called()

    def test_query_by_config_aggregates_warnings_with_source(self):
        project = {"environments": {"prod": {"platforms": [
            {"type": "sls", "name": "a",
             "config": {"endpoint": "e", "project": "p", "logstore": "a",
                        "indexHint": "message 无全文索引"}},
        ]}}}
        response = {"logs": [], "count": 0, "query": "kw",
                    "warnings": ["0 条结果且该 logstore 已预置索引提示: message 无全文索引"],
                    "timeRange": {}}
        with patch.object(sls_client, "query_logs", return_value=response) as q:
            merged = sls_client.query_by_config(project, "prod", "kw")
        q.assert_called_once()
        self.assertEqual("message 无全文索引", q.call_args.kwargs["index_hint"])
        self.assertTrue(any(w.startswith("p/a: ") for w in merged["warnings"]))


class DoctorLivenessTest(unittest.TestCase):
    def test_invalid_liveness_window_rejected(self):
        result = doctor.cmd_doctor(SimpleNamespace(no_live=False,
                                                   liveness_window="昨天"))
        self.assertEqual("error", result["status"])
        self.assertEqual("BAD_ARGUMENT", result["error"]["code"])

    def test_liveness_requires_live_mode(self):
        result = doctor.cmd_doctor(SimpleNamespace(no_live=True,
                                                   liveness_window="30d"))
        self.assertEqual("error", result["status"])
        self.assertEqual("BAD_ARGUMENT", result["error"]["code"])


class DeployEnvSynonymTest(unittest.TestCase):
    def test_prod_keyword_matches_formal_pipeline(self):
        pipelines = [
            {"pipelineId": 1, "pipelineName": "正式-云网络ASO",
             "latestPipelineInstanceId": 11},
            {"pipelineId": 2, "pipelineName": "日常-云网络",
             "latestPipelineInstanceId": 12},
        ]
        with patch.object(a1_client, "list_pipelines", return_value=pipelines), \
             patch.object(a1_client, "get_pipeline_branch",
                          return_value={"releaseBranch": "release/x"}):
            result = a1_client.query_env_deploy("app", "生产")
        self.assertEqual(1, result["matched_count"])
        self.assertEqual("", result["hint"])

    def test_prod_still_excludes_informal_pipeline(self):
        pipelines = [
            {"pipelineId": 1, "pipelineName": "非正式发布",
             "latestPipelineInstanceId": 1},
            {"pipelineId": 2, "pipelineName": "正式发布",
             "latestPipelineInstanceId": 2},
        ]
        with patch.object(a1_client, "list_pipelines", return_value=pipelines), \
             patch.object(a1_client, "get_pipeline_branch",
                          return_value={"releaseBranch": "b"}):
            result = a1_client.query_env_deploy("app", "prod")
        self.assertEqual(1, result["matched_count"])

    def test_no_match_hint_lists_real_pipeline_names(self):
        pipelines = [{"pipelineId": 1, "pipelineName": "灰度-某环境",
                      "latestPipelineInstanceId": 1}]
        with patch.object(a1_client, "list_pipelines", return_value=pipelines):
            result = a1_client.query_env_deploy("app", "生产")
        self.assertEqual(0, result["matched_count"])
        self.assertIn("灰度-某环境", result["hint"])
        self.assertIn("生产", result["hint"])


class DeployBranchTest(unittest.TestCase):
    def test_branch_returns_release_branches_from_pipelines(self):
        pipelines = [
            {"pipelineId": 1, "pipelineName": "正式", "status": "SUCCESS",
             "latestPipelineInstanceId": 10},
            {"pipelineId": 2, "pipelineName": "日常", "status": "SUCCESS",
             "latestPipelineInstanceId": None},
        ]
        branch_info = {"releaseBranch": "release/20260813",
                       "changeRequests": [{"commitId": "abc123"}]}
        with patch.object(a1_client, "get_app_info", return_value={"name": "app"}), \
             patch.object(a1_client, "list_pipelines", return_value=pipelines), \
             patch.object(a1_client, "get_pipeline_branch", return_value=branch_info):
            result = a1_client.query_deployed_branch("app")
        self.assertEqual(["release/20260813"], result["release_branches"])
        self.assertEqual(["abc123"], result["commits"])
        self.assertEqual("正式", result["deployments"][0]["pipelineName"])

    def test_branch_without_pipelines_warns_metadata_only(self):
        with patch.object(a1_client, "get_app_info", return_value={}), \
             patch.object(a1_client, "list_pipelines", return_value=[]):
            result = a1_client.query_deployed_branch("app")
        self.assertEqual([], result["deployments"])
        self.assertTrue(any("不能代表线上版本" in w for w in result["warnings"]))


class CronTaskHealthChainTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_dir = chain._SESSION_DIR
        chain._SESSION_DIR = Path(self.temp_dir.name) / "sessions"

    def tearDown(self):
        chain._SESSION_DIR = self.old_dir
        self.temp_dir.cleanup()

    def test_chain_registered_with_five_steps(self):
        chains = {c["name"]: c for c in chain.list_chains()}
        self.assertIn("cron-task-health", chains)
        self.assertEqual(5, len(chains["cron-task-health"]["steps"]))

    def test_first_step_satisfied_by_problem_description(self):
        session = chain.start_session(
            "cron-task-health",
            problem_description="stability-monitor MetricSyncTask 是否每日触发")
        validation = chain.validate_step(session["session_id"], 1)
        self.assertTrue(validation["valid"], validation.get("reason"))


if __name__ == "__main__":
    unittest.main()
