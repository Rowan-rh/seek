"""chain report — 报告文件名与模板头部构造测试."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import sys

_CLI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_CLI_ROOT))

from seek_cli import chain as chain_mod  # noqa: E402
from seek_cli.commands import chain as chain_commands  # noqa: E402


def _fake_date(iso: str):
    """构造 date.today().isoformat() 返回固定日期的替身。"""
    fake = mock.Mock()
    fake.today.return_value.isoformat.return_value = iso
    return fake


def _mark_completed(session_id: str, completed_at: str = "2026-09-02T12:00:00") -> dict:
    """把会话文件置为 completed（报告构造仅对完成会话开放）。"""
    session = chain_mod.get_session(session_id)
    session["status"] = "completed"
    session["completed_at"] = completed_at
    chain_mod._save_session(session)
    return session


class _ChainReportTestBase(unittest.TestCase):
    """临时目录隔离：会话与用户模板覆盖不读写真实 ~/.seek/。"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self._old_session_dir = chain_mod._SESSION_DIR
        self._old_user_templates = chain_mod._USER_TEMPLATES
        chain_mod._SESSION_DIR = root / "sessions"
        chain_mod._USER_TEMPLATES = root / "templates"  # 空目录，阻断用户模板覆盖干扰

    def tearDown(self):
        chain_mod._SESSION_DIR = self._old_session_dir
        chain_mod._USER_TEMPLATES = self._old_user_templates
        self.temp_dir.cleanup()


class BuildReportTest(_ChainReportTestBase):
    def setUp(self):
        super().setUp()
        self.session = chain_mod.start_session(
            "default", project="demo", problem_description="演练问题: objectList 为空")
        self.session_id = self.session["session_id"]
        _mark_completed(self.session_id)

    def test_filename_uses_production_date_prefix(self):
        with mock.patch.object(chain_mod, "date", _fake_date("2026-09-02")):
            report = chain_mod.build_report(self.session_id, "batch-560d6f3c-objectlist-empty")
        self.assertEqual(report["filename"],
                         "seek-report-2026-09-02-batch-560d6f3c-objectlist-empty.md")
        self.assertEqual(report["report_date"], "2026-09-02")
        self.assertEqual(report["slug"], "batch-560d6f3c-objectlist-empty")
        self.assertEqual(report["chain_name"], "default")
        self.assertEqual(report["template"]["name"], "generic.md")
        self.assertTrue(Path(report["template"]["path"]).is_file())

    def test_header_fills_machine_fields_and_keeps_semantic_placeholders(self):
        with mock.patch.object(chain_mod, "date", _fake_date("2026-09-02")):
            report = chain_mod.build_report(self.session_id, "batch-560d6f3c-objectlist-empty")
        header = report["header_markdown"]
        self.assertIn("# 排查报告 — {主题一句话}", header)
        self.assertIn(self.session_id, header)
        self.assertIn("default", header)
        self.assertIn("2026-09-02T12:00:00", header)
        self.assertIn("演练问题: objectList 为空", header)
        for placeholder in ("{session_id}", "{chain_name}", "{start_time}",
                            "{end_time}", "{problem_description}"):
            self.assertNotIn(placeholder, header, placeholder)
        # 头部块止于首个 '---' 分隔线，不含正文
        self.assertNotIn("---", header.splitlines())

    def test_rejects_incomplete_session(self):
        session = chain_mod.get_session(self.session_id)
        session["status"] = "in_progress"
        chain_mod._save_session(session)
        with self.assertRaises(ValueError) as ctx:
            chain_mod.build_report(self.session_id, "batch-x")
        self.assertIn("not completed", str(ctx.exception))

    def test_rejects_unknown_session(self):
        with self.assertRaises(ValueError):
            chain_mod.build_report("no-such-session", "batch-x")

    def test_rejects_invalid_slugs(self):
        invalid = [
            "", "   ", None,
            "Batch-Uppercase", "batch with space", "batch_underscore",
            "seek-report-batch-x", "2026-09-02-batch-x", "2026-9-2-batch", "batch-x.md",
            "a" * 81, "中文-slug", "batch--double", "-leading", "trailing-",
        ]
        for slug in invalid:
            with self.subTest(slug=slug):
                self.assertIsNotNone(chain_mod.validate_report_slug(slug))

    def test_accepts_valid_slugs(self):
        valid = [
            "batch-560d6f3c-objectlist-empty",
            "template-action-deleted",
            "alert-91e78443-autofix-not-started",
            "x", "a1-b2",
        ]
        for slug in valid:
            with self.subTest(slug=slug):
                self.assertIsNone(chain_mod.validate_report_slug(slug))

    def test_ticket_chain_keeps_flowid_placeholder(self):
        session = chain_mod.start_session(
            "alert-ticket", problem_description="工单问题",
            initial_context={"flow_id": "FLOW-123"})
        _mark_completed(session["session_id"])
        with mock.patch.object(chain_mod, "date", _fake_date("2026-09-02")):
            report = chain_mod.build_report(session["session_id"], "flow-fx9000-npe")
        self.assertEqual(report["template"]["name"], "ticket.md")
        # ticket 模板头部无 problem_description 占位符，验证时间字段已填充、语义占位符保留
        self.assertIn("# 排查报告 — {flowId}", report["header_markdown"])
        self.assertIn("2026-09-02T12:00:00", report["header_markdown"])
        self.assertNotIn("{start_time}", report["header_markdown"])
        self.assertNotIn("{end_time}", report["header_markdown"])

    def test_template_error_raises_chain_config_error(self):
        with mock.patch.object(
                chain_mod, "get_report_template",
                side_effect=chain_mod.ChainConfigError("template missing")):
            with self.assertRaises(chain_mod.ChainConfigError):
                chain_mod.build_report(self.session_id, "batch-x")


class ChainReportCommandTest(_ChainReportTestBase):
    def setUp(self):
        super().setUp()
        self.session = chain_mod.start_session("default", problem_description="测试问题")
        self.session_id = self.session["session_id"]

    def _args(self, session=None, slug="batch-x-objectlist-empty"):
        return SimpleNamespace(session=session or self.session_id, slug=slug)

    def test_success_returns_filename_and_header(self):
        _mark_completed(self.session_id)
        with mock.patch.object(chain_mod, "date", _fake_date("2026-09-02")):
            result = chain_commands.cmd_chain_report(self._args())
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["filename"],
                         "seek-report-2026-09-02-batch-x-objectlist-empty.md")
        self.assertIn("header_markdown", result["data"])
        self.assertIn("template", result["data"])

    def test_incomplete_session_returns_session_not_completed(self):
        result = chain_commands.cmd_chain_report(self._args())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "SESSION_NOT_COMPLETED")

    def test_unknown_session_returns_not_found(self):
        # 合法格式(12位hex)但不存在的会话 → NOT_FOUND；畸形 id → BAD_ARGUMENT 见 test_chain_persistence
        result = chain_commands.cmd_chain_report(self._args(session="000000000000"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "NOT_FOUND")

    def test_bad_slug_returns_bad_slug(self):
        _mark_completed(self.session_id)
        result = chain_commands.cmd_chain_report(self._args(slug="Batch Bad"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "BAD_SLUG")

    def test_template_error_returns_chain_config_error(self):
        # 回归：ChainConfigError 是 ValueError 子类，except 顺序错误会降级为 SESSION_ERROR
        _mark_completed(self.session_id)
        with mock.patch.object(
                chain_mod, "get_report_template",
                side_effect=chain_mod.ChainConfigError("template missing")):
            result = chain_commands.cmd_chain_report(self._args())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "CHAIN_CONFIG_ERROR")


if __name__ == "__main__":
    unittest.main()
