"""Tests for the external integration initialization guide."""

import argparse
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from seek_cli.commands import init_cmd


class InitCommandTest(unittest.TestCase):
    def test_missing_dependencies_return_actionable_guidance(self):
        missing = Path("/tmp/seek-test-missing-mcp.json")
        with mock.patch.object(init_cmd.shutil, "which", return_value=None), \
                mock.patch.object(init_cmd.dms_client, "_MCP_CONFIG", missing), \
                mock.patch.object(init_cmd.sls_client, "SDK_AVAILABLE", False):
            result = init_cmd.cmd_init(argparse.Namespace(verify=False))

        self.assertEqual("ok", result["status"])
        self.assertFalse(result["data"]["ready"])
        integrations = {item["name"]: item for item in result["data"]["integrations"]}
        self.assertEqual("missing", integrations["A1 CLI"]["status"])
        self.assertEqual("missing", integrations["DMS MCP"]["status"])
        self.assertEqual("missing_dependency", integrations["SLS"]["status"])
        self.assertEqual(init_cmd.A1_CLI_GUIDE_URL, integrations["A1 CLI"]["documentation"])
        self.assertEqual(init_cmd.DMS_MCP_GUIDE_URL, integrations["DMS MCP"]["documentation"])

    def test_local_checks_do_not_run_external_verification(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "mcp.json"
            a1_config = Path(temp_dir) / "a1-config.yaml"
            a1_config.write_text("auth: configured", encoding="utf-8")
            config_path.write_text(json.dumps({
                "mcpServers": {
                    "dms-mcp-server": {"command": "uvx", "args": ["dms-package"]}
                }
            }), encoding="utf-8")
            with mock.patch.object(init_cmd.shutil, "which", side_effect=lambda name: f"/bin/{name}"), \
                    mock.patch.object(init_cmd, "A1_CONFIG", a1_config), \
                    mock.patch.object(init_cmd.dms_client, "_MCP_CONFIG", config_path), \
                    mock.patch.object(init_cmd.sls_client, "SDK_AVAILABLE", True), \
                    mock.patch.object(init_cmd.sls_client, "_get_credentials", return_value={
                        "access_key_id": "secret-ak", "access_key_secret": "secret-sk"
                    }), \
                    mock.patch.object(init_cmd.subprocess, "run") as run, \
                    mock.patch.object(init_cmd.dms_client, "DmsMcpClient") as client:
                report = init_cmd.build_initialization_report(verify=False)

        self.assertTrue(report["ready"])
        self.assertFalse(report["fully_ready"])
        run.assert_not_called()
        client.assert_not_called()
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("secret-ak", serialized)
        self.assertNotIn("secret-sk", serialized)

    def test_verify_reports_a1_and_dms_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "mcp.json"
            a1_config = Path(temp_dir) / "a1-config.yaml"
            a1_config.write_text("auth: configured", encoding="utf-8")
            config_path.write_text(json.dumps({
                "mcpServers": {
                    "dms-mcp-server": {"command": "uvx", "args": ["dms-package"]}
                }
            }), encoding="utf-8")
            completed = mock.Mock(returncode=0)
            client = mock.Mock()
            client.list_tools.return_value = [{"name": "executeScript"}]
            with mock.patch.object(init_cmd.shutil, "which", side_effect=lambda name: f"/bin/{name}"), \
                    mock.patch.object(init_cmd, "A1_CONFIG", a1_config), \
                    mock.patch.object(init_cmd.dms_client, "_MCP_CONFIG", config_path), \
                    mock.patch.object(init_cmd.sls_client, "SDK_AVAILABLE", True), \
                    mock.patch.object(init_cmd.sls_client, "_get_credentials", return_value={
                        "access_key_id": "ak", "access_key_secret": "sk"
                    }), \
                    mock.patch.object(init_cmd.subprocess, "run", return_value=completed), \
                    mock.patch.object(init_cmd.dms_client, "DmsMcpClient", return_value=client):
                report = init_cmd.build_initialization_report(verify=True)

        integrations = {item["name"]: item for item in report["integrations"]}
        self.assertTrue(report["ready"])
        self.assertTrue(report["fully_ready"])
        integrations = {item["name"]: item for item in report["integrations"]}
        self.assertEqual("doctor", integrations["SLS"]["verification_scope"])
        self.assertNotIn("SLS: seek doctor --liveness-window 24h", report["next_actions"])
        self.assertTrue(integrations["A1 CLI"]["verified"])
        self.assertEqual("ready", integrations["A1 CLI"]["status"])
        self.assertTrue(integrations["A1 CLI"]["configured"])
        self.assertTrue(integrations["DMS MCP"]["verified"])
        client.close.assert_called_once_with()

    def test_verify_failures_do_not_leak_external_error_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "mcp.json"
            a1_config = Path(temp_dir) / "a1-auth.yaml"
            a1_config.write_text("auth: present", encoding="utf-8")
            config_path.write_text(json.dumps({
                "mcpServers": {
                    "dms-mcp-server": {
                        "command": "uvx",
                        "args": ["dms-package"],
                        "env": {"ACCESS_KEY_SECRET": "TOP-SECRET"},
                    }
                }
            }), encoding="utf-8")
            completed = mock.Mock(returncode=1, stderr="token=TOP-SECRET")
            client = mock.Mock()
            client.list_tools.side_effect = RuntimeError("key=TOP-SECRET")
            with mock.patch.object(init_cmd.shutil, "which", side_effect=lambda name: f"/bin/{name}"), \
                    mock.patch.object(init_cmd, "A1_CONFIG", a1_config), \
                    mock.patch.object(init_cmd.dms_client, "_MCP_CONFIG", config_path), \
                    mock.patch.object(init_cmd.sls_client, "SDK_AVAILABLE", True), \
                    mock.patch.object(init_cmd.sls_client, "_get_credentials", return_value={
                        "access_key_id": "ak", "access_key_secret": "TOP-SECRET"
                    }), \
                    mock.patch.object(init_cmd.subprocess, "run", return_value=completed), \
                    mock.patch.object(init_cmd.dms_client, "DmsMcpClient", return_value=client):
                report = init_cmd.build_initialization_report(verify=True)

        serialized = json.dumps(report, ensure_ascii=False)
        self.assertFalse(report["ready"])
        self.assertFalse(report["fully_ready"])
        self.assertNotIn("TOP-SECRET", serialized)
        statuses = {item["name"]: item["status"] for item in report["integrations"]}
        self.assertEqual("needs_auth", statuses["A1 CLI"])
        self.assertEqual("verification_failed", statuses["DMS MCP"])
        # 回归：即使 auth.yaml 存在，--verify 认证失败也必须将 configured 降级为 false
        a1 = next(item for item in report["integrations"] if item["name"] == "A1 CLI")
        self.assertFalse(a1["configured"])

    def test_invalid_dms_json_is_reported_without_exception(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "mcp.json"
            config_path.write_text("{bad", encoding="utf-8")
            with mock.patch.object(init_cmd.shutil, "which", return_value="/bin/a1"), \
                    mock.patch.object(init_cmd.dms_client, "_MCP_CONFIG", config_path), \
                    mock.patch.object(init_cmd.sls_client, "SDK_AVAILABLE", True), \
                    mock.patch.object(init_cmd.sls_client, "_get_credentials", return_value={
                        "access_key_id": "ak", "access_key_secret": "sk"
                    }):
                report = init_cmd.build_initialization_report()
        dms = next(item for item in report["integrations"] if item["name"] == "DMS MCP")
        self.assertEqual("invalid", dms["status"])
        self.assertFalse(dms["configured"])

    def test_a1_auth_present_defaults_to_configured_unverified(self):
        """回归：auth.yaml 存在时默认不得误报 needs_auth（历史误探测 config.yaml）。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "mcp.json"
            a1_config = Path(temp_dir) / "a1-auth.yaml"
            a1_config.write_text("auth: present", encoding="utf-8")
            config_path.write_text(json.dumps({
                "mcpServers": {
                    "dms-mcp-server": {"command": "uvx", "args": ["dms-package"]}
                }
            }), encoding="utf-8")
            with mock.patch.object(init_cmd.shutil, "which", side_effect=lambda name: f"/bin/{name}"), \
                    mock.patch.object(init_cmd, "A1_CONFIG", a1_config), \
                    mock.patch.object(init_cmd.dms_client, "_MCP_CONFIG", config_path), \
                    mock.patch.object(init_cmd.sls_client, "SDK_AVAILABLE", True), \
                    mock.patch.object(init_cmd.sls_client, "_get_credentials", return_value={
                        "access_key_id": "ak", "access_key_secret": "sk"
                    }), \
                    mock.patch.object(init_cmd.subprocess, "run") as run:
                report = init_cmd.build_initialization_report(verify=False)
        run.assert_not_called()
        a1 = next(item for item in report["integrations"] if item["name"] == "A1 CLI")
        self.assertEqual("configured_unverified", a1["status"])
        self.assertTrue(a1["configured"])
        self.assertTrue(report["ready"])

    def test_verify_success_overrides_missing_auth_file(self):
        """凭据不在探测路径（如 keychain）时，--verify 以 whoami 实测为准置 configured=true。"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "mcp.json"
            missing_a1 = Path(temp_dir) / "no-such-auth.yaml"
            config_path.write_text(json.dumps({
                "mcpServers": {
                    "dms-mcp-server": {"command": "uvx", "args": ["dms-package"]}
                }
            }), encoding="utf-8")
            completed = mock.Mock(returncode=0)
            client = mock.Mock()
            client.list_tools.return_value = [{"name": "executeScript"}]
            with mock.patch.object(init_cmd.shutil, "which", side_effect=lambda name: f"/bin/{name}"), \
                    mock.patch.object(init_cmd, "A1_CONFIG", missing_a1), \
                    mock.patch.object(init_cmd.dms_client, "_MCP_CONFIG", config_path), \
                    mock.patch.object(init_cmd.sls_client, "SDK_AVAILABLE", True), \
                    mock.patch.object(init_cmd.sls_client, "_get_credentials", return_value={
                        "access_key_id": "ak", "access_key_secret": "sk"
                    }), \
                    mock.patch.object(init_cmd.subprocess, "run", return_value=completed), \
                    mock.patch.object(init_cmd.dms_client, "DmsMcpClient", return_value=client):
                report = init_cmd.build_initialization_report(verify=True)
        a1 = next(item for item in report["integrations"] if item["name"] == "A1 CLI")
        self.assertEqual("ready", a1["status"])
        self.assertTrue(a1["configured"])
        self.assertTrue(a1["verified"])
        self.assertTrue(report["ready"])


if __name__ == "__main__":
    unittest.main()
