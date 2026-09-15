"""SLS 环境别名（envAliases）解析与结果标注测试。"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from seek_cli import config
from seek_cli.commands import sls as sls_cmd

_PROJECTS = {"projects": {
    # 有别名：daily → yanlian（精确环境无 daily）
    "demo": {
        "envAliases": {"daily": "yanlian"},
        "environments": {
            "yanlian": {"platforms": [{"type": "sls", "name": "yl",
                                        "config": {"endpoint": "e1", "project": "p1", "logstore": "l1"}}]},
            "prod": {"platforms": [{"type": "sls", "name": "pd",
                                    "config": {"endpoint": "e2", "project": "p2", "logstore": "l2"}}]},
        },
    },
    # 精确环境与别名键重名：精确优先
    "exact": {
        "envAliases": {"daily": "yanlian"},
        "environments": {
            "daily": {"platforms": [{"type": "sls", "name": "dd",
                                     "config": {"endpoint": "e3", "project": "p3", "logstore": "l3"}}]},
            "yanlian": {"platforms": [{"type": "sls", "name": "yl",
                                       "config": {"endpoint": "e4", "project": "p4", "logstore": "l4"}}]},
        },
    },
    # 别名目标不存在
    "dangling": {
        "envAliases": {"daily": "nosuchenv"},
        "environments": {
            "prod": {"platforms": [{"type": "sls", "name": "pd",
                                    "config": {"endpoint": "e5", "project": "p5", "logstore": "l5"}}]},
        },
    },
    # 无 envAliases / 非法 envAliases
    "plain": {"environments": {
        "prod": {"platforms": [{"type": "sls", "name": "pd",
                                "config": {"endpoint": "e6", "project": "p6", "logstore": "l6"}}]},
    }},
    "badaliases": {
        "envAliases": "not-a-dict",
        "environments": {
            "prod": {"platforms": [{"type": "sls", "name": "pd",
                                    "config": {"endpoint": "e7", "project": "p7", "logstore": "l7"}}]},
        },
    },
}}


class EnvAliasTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.old_builtin = config._BUILTIN_CONFIG
        self.old_user = config._USER_CONFIG
        config._BUILTIN_CONFIG = root / "builtin.json"
        config._USER_CONFIG = root / "user.json"
        config._BUILTIN_CONFIG.write_text(json.dumps(_PROJECTS), encoding="utf-8")

    def tearDown(self):
        config._BUILTIN_CONFIG = self.old_builtin
        config._USER_CONFIG = self.old_user
        self.temp_dir.cleanup()

    # ── resolve_env 解析规则 ──

    def test_alias_resolves_to_target(self):
        self.assertEqual(config.resolve_env("demo", "daily"), "yanlian")

    def test_exact_match_wins_over_alias(self):
        self.assertEqual(config.resolve_env("exact", "daily"), "daily")

    def test_dangling_alias_not_applied(self):
        self.assertEqual(config.resolve_env("dangling", "daily"), "daily")
        self.assertEqual(config.get_all_sls_configs("dangling", "daily"), [])

    def test_no_alias_passthrough(self):
        self.assertEqual(config.resolve_env("plain", "prod"), "prod")
        self.assertEqual(config.resolve_env("plain", "daily"), "daily")

    def test_invalid_alias_field_ignored(self):
        self.assertEqual(config.resolve_env("badaliases", "daily"), "daily")
        self.assertEqual(config.get_env_aliases("badaliases"), {})

    def test_unknown_project_passthrough(self):
        self.assertEqual(config.resolve_env("no-such-project", "daily"), "daily")

    # ── get_all_sls_configs 接入别名 ──

    def test_get_all_sls_configs_via_alias(self):
        cfgs = config.get_all_sls_configs("demo", "daily")
        self.assertEqual(len(cfgs), 1)
        self.assertEqual(cfgs[0]["config"]["endpoint"], "e1")  # yanlian 的配置

    def test_query_by_config_resolves_alias_before_lookup(self):
        from seek_cli.integrations import sls_client
        with patch.object(sls_client, "query_logs",
                          return_value={"logs": [], "count": 0, "query": "q", "timeRange": {}}) as query:
            result = sls_client.query_by_config(config.get_project("demo"), "daily", "q")
        self.assertEqual(0, result["count"])
        query.assert_called_once()

    # ── sls config 命令标注 ──

    def test_sls_config_resolved_env_annotation(self):
        result = sls_cmd.cmd_sls_config(
            SimpleNamespace(project="demo", env="daily", format="json"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["resolvedEnv"], "yanlian")
        self.assertEqual(result["data"]["sls_configs"][0]["config"]["endpoint"], "e1")

    def test_sls_config_exact_env_no_annotation(self):
        result = sls_cmd.cmd_sls_config(
            SimpleNamespace(project="demo", env="prod", format="json"))
        self.assertEqual(result["status"], "ok")
        self.assertNotIn("resolvedEnv", result["data"])

    def test_sls_config_error_includes_aliases(self):
        result = sls_cmd.cmd_sls_config(
            SimpleNamespace(project="demo", env="staging", format="json"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "NOT_FOUND")
        self.assertIn("available_envs", result["data"])
        self.assertEqual(result["data"]["env_aliases"], {"daily": "yanlian"})

    def test_sls_config_overview_includes_aliases(self):
        result = sls_cmd.cmd_sls_config(
            SimpleNamespace(project="demo", env=None, format="json"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["env_aliases"], {"daily": "yanlian"})

    # ── sls query/logs 结果标注（mock 查询层，不触网） ──

    def _query_args(self, env):
        return SimpleNamespace(project="demo", env=env, query="q", query_file=None,
                               time="15m", max=10, sort=None,
                               endpoint=None, sls_project=None, logstore=None,
                               format="json")

    def test_sls_query_annotates_resolved_env(self):
        with patch.object(sls_cmd.sls_client, "query_by_config",
                          return_value={"logs": [], "count": 0, "query": "q"}):
            result = sls_cmd.cmd_sls_query(self._query_args("daily"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["resolvedEnv"], "yanlian")
        self.assertTrue(any("envAliases" in w for w in result["data"]["warnings"]))

    def test_sls_query_exact_env_no_annotation(self):
        with patch.object(sls_cmd.sls_client, "query_by_config",
                          return_value={"logs": [], "count": 0, "query": "q"}):
            result = sls_cmd.cmd_sls_query(self._query_args("prod"))
        self.assertEqual(result["status"], "ok")
        self.assertNotIn("resolvedEnv", result["data"])

    def test_sls_logs_annotates_resolved_env(self):
        args = SimpleNamespace(project="demo", env="daily", level=None, keyword="k",
                               trace_id=None, time="15m", max=10, format="json")
        with patch.object(sls_cmd.sls_client, "query_by_config",
                          return_value={"logs": [], "count": 0, "query": "k"}):
            result = sls_cmd.cmd_sls_logs(args)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["resolvedEnv"], "yanlian")


if __name__ == "__main__":
    unittest.main()
