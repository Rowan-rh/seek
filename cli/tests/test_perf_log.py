"""perf 耗时观测测试 — 记录字段、开关、故障隔离、会话关联与脱敏。"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from seek_cli import perf_log


class PerfLogTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_dir = perf_log._LOG_DIR
        self.old_file = perf_log._LOG_FILE
        perf_log._LOG_DIR = Path(self.temp_dir.name)
        perf_log._LOG_FILE = perf_log._LOG_DIR / "perf.jsonl"
        # 单测不依赖用户机器上的 options.perf_log 实际取值；
        # 真实开关链路用例在下方通过 stop/start 该 patcher 验证
        self._enabled_patcher = mock.patch.object(perf_log, "enabled", return_value=True)
        self._enabled_patcher.start()
        self.addCleanup(self._enabled_patcher.stop)

    def tearDown(self):
        perf_log._LOG_DIR = self.old_dir
        perf_log._LOG_FILE = self.old_file
        self.temp_dir.cleanup()

    def _read_entries(self):
        if not perf_log._LOG_FILE.exists():
            return []
        lines = perf_log._LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def test_log_perf_writes_full_entry(self):
        perf_log.log_perf("sls query", "command", 1234, "success", {"count": 5})
        entries = self._read_entries()
        self.assertEqual(1, len(entries))
        entry = entries[0]
        self.assertEqual("sls query", entry["command"])
        self.assertEqual("command", entry["span"])
        self.assertEqual("success", entry["status"])
        self.assertEqual(1234, entry["duration_ms"])
        self.assertIn("timestamp", entry)
        self.assertNotIn("session_id", entry)  # 未设置 SEEK_SESSION_ID 时不带该字段

    def test_disabled_writes_nothing(self):
        with mock.patch.object(perf_log, "enabled", return_value=False):
            perf_log.log_perf("version", "command", 5, "success")
        self.assertEqual([], self._read_entries())

    def test_enabled_reads_options_perf_log(self):
        # 真实开关链路：enabled() → settings.get_setting("options.perf_log") → as_bool
        from seek_cli import settings
        self._enabled_patcher.stop()
        try:
            with mock.patch.object(settings, "get_setting", return_value="false") as get:
                self.assertFalse(perf_log.enabled())
                get.assert_called_once_with("options.perf_log")
            with mock.patch.object(settings, "get_setting", return_value="true"):
                self.assertTrue(perf_log.enabled())
            with mock.patch.object(settings, "get_setting", return_value=None):
                self.assertTrue(perf_log.enabled())  # 未设置默认开启
            with mock.patch.object(settings, "get_setting", side_effect=RuntimeError):
                self.assertTrue(perf_log.enabled())  # fail-open：读配置失败不关观测
        finally:
            self._enabled_patcher.start()

    def test_real_switch_off_blocks_writes_end_to_end(self):
        # spec scenario「开关关闭」：options.perf_log=false 时 log_perf 不追加任何记录
        from seek_cli import settings
        self._enabled_patcher.stop()
        try:
            with mock.patch.object(settings, "get_setting", return_value="false"):
                self.assertFalse(perf_log.enabled())
                perf_log.log_perf("version", "command", 5, "success")
        finally:
            self._enabled_patcher.start()
        self.assertEqual([], self._read_entries())

    def test_write_failure_swallowed(self):
        # perf.jsonl 被目录占位：open 必然失败，但 log_perf 不得抛异常
        perf_log._LOG_FILE.mkdir()
        perf_log.log_perf("version", "command", 5, "success")
        perf_log._LOG_FILE.rmdir()  # 恢复，供 tearDown 正常清理

    def test_session_id_attached_from_env(self):
        os.environ["SEEK_SESSION_ID"] = "e2e123"
        try:
            perf_log.log_perf("sls query", "command", 5, "success")
        finally:
            del os.environ["SEEK_SESSION_ID"]
        self.assertEqual("e2e123", self._read_entries()[0]["session_id"])

    def test_detail_sanitized_and_truncated(self):
        perf_log.log_perf("sls p/l", "sls_query", 5, "success", {
            "PASSWORD": "secret",
            "query": "a" * 300,
            "logstore": "l",
        })
        detail = self._read_entries()[0]["detail"]
        self.assertEqual("***", detail["PASSWORD"])
        self.assertEqual(200, len(detail["query"]))
        self.assertEqual("l", detail["logstore"])

    def test_perf_span_success_path(self):
        with perf_log.perf_span("sls p/l", "sls_query",
                                {"logstore": "l"}) as span:
            span["count"] = 3
        entry = self._read_entries()[0]
        self.assertEqual("success", entry["status"])
        self.assertEqual("sls_query", entry["span"])
        self.assertEqual(3, entry["detail"]["count"])
        self.assertGreaterEqual(entry["duration_ms"], 0)

    def test_perf_span_error_path_records_and_reraises(self):
        with self.assertRaises(RuntimeError):
            with perf_log.perf_span("dms executeScript", "dms_call",
                                    {"tool": "executeScript"}):
                raise RuntimeError("boom")
        entry = self._read_entries()[0]
        self.assertEqual("error", entry["status"])
        self.assertEqual("dms_call", entry["span"])

    def test_a1_failure_recorded_as_error(self):
        # 非零 returncode 的 raise 必须发生在 span 内，否则失败调用被记为 success
        from seek_cli.integrations import a1_client
        fake = subprocess.CompletedProcess(args=["a1"], returncode=1,
                                            stdout="", stderr="boom")
        with mock.patch.object(a1_client, "_check_a1", return_value="/usr/bin/a1"), \
             mock.patch.object(a1_client.subprocess, "run", return_value=fake):
            with self.assertRaises(RuntimeError):
                a1_client._run_a1(["app", "view", "demo"])
        entry = self._read_entries()[0]
        self.assertEqual("error", entry["status"])
        self.assertEqual("a1_subprocess", entry["span"])
        self.assertEqual(1, entry["detail"]["returncode"])

    def test_cli_command_span_via_main(self):
        # 进程内直调 main() 验证 L1 埋点（避免子进程 HOME 重定向破坏 --user 依赖解析）
        from seek_cli import cli as cli_module
        os.environ["SEEK_SESSION_ID"] = "e2e-main"
        try:
            out = io.StringIO()
            with mock.patch.object(sys, "argv", ["seek", "version"]), \
                 mock.patch.object(cli_module, "_check_version_change"), \
                 contextlib.redirect_stdout(out):
                cli_module.main()  # 成功路径不 sys.exit，直接返回
        finally:
            del os.environ["SEEK_SESSION_ID"]
        self.assertIn('"status": "ok"', out.getvalue())
        entries = self._read_entries()
        command_entries = [e for e in entries if e.get("span") == "command"]
        self.assertEqual(1, len(command_entries))
        self.assertEqual("version", command_entries[0]["command"])
        self.assertEqual("success", command_entries[0]["status"])
        self.assertEqual("e2e-main", command_entries[0]["session_id"])


if __name__ == "__main__":
    unittest.main()
