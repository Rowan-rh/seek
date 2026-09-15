"""Report template resolution tests."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys

_CLI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_CLI_ROOT))

from seek_cli import chain as chain_mod  # noqa: E402

_REPO_ROOT = _CLI_ROOT.parent
_REPO_TEMPLATES = _CLI_ROOT / "chains" / "templates"
_PKG_TEMPLATES = _CLI_ROOT / "seek_cli" / "resources" / "chains" / "templates"


class TemplateMirrorTest(unittest.TestCase):
    def test_repo_and_package_templates_are_identical(self):
        for name in ("generic.md", "ticket.md"):
            with self.subTest(template=name):
                self.assertTrue((_REPO_TEMPLATES / name).is_file())
                self.assertTrue((_PKG_TEMPLATES / name).is_file())
                self.assertEqual(
                    (_REPO_TEMPLATES / name).read_text(encoding="utf-8"),
                    (_PKG_TEMPLATES / name).read_text(encoding="utf-8"),
                )

    def test_generic_template_has_required_sections_and_no_ticket_placeholders(self):
        content = (_REPO_TEMPLATES / "generic.md").read_text(encoding="utf-8")
        for section in ("快速结论", "可复用排查路径与证据点", "排查过程",
                        "样本对比与归因", "根因分析", "修复建议", "未决事项", "更正记录"):
            with self.subTest(section=section):
                self.assertIn(section, content)
        for ticket_placeholder in ("{flowId}", "{questionTitle}", "{ticket_category}",
                                  "{dutyPerson}", "{handoff_target}"):
            with self.subTest(placeholder=ticket_placeholder):
                self.assertNotIn(ticket_placeholder, content)

    def test_ticket_template_keeps_ticket_sections(self):
        content = (_REPO_TEMPLATES / "ticket.md").read_text(encoding="utf-8")
        for section in ("工单信息", "相似工单分析", "推荐联系人", "通知类固定证据项",
                        "异常样本与正常样本对比"):
            with self.subTest(section=section):
                self.assertIn(section, content)

    def test_fault_templates_separate_failure_point_from_trigger(self):
        for template in ("generic.md", "ticket.md"):
            content = (_REPO_TEMPLATES / template).read_text(encoding="utf-8")
            with self.subTest(template=template):
                self.assertIn("直接报错点", content)
                self.assertIn("首要触发根因", content)
                self.assertIn("次生容错/放大问题", content)
                self.assertIn("INSUFFICIENT_EVIDENCE", content)


class TemplateResolutionTest(unittest.TestCase):
    def test_alert_ticket_resolves_to_ticket_template(self):
        resolved = chain_mod.get_report_template("alert-ticket")
        self.assertEqual(resolved["name"], "ticket.md")
        self.assertTrue(Path(resolved["path"]).is_file())

    def test_chains_without_field_fall_back_to_generic(self):
        for name in ("default", "alert-enrichment", "notification",
                     "cron-task-health", "emergency-response", "emergency-stuck-task"):
            with self.subTest(chain=name):
                resolved = chain_mod.get_report_template(name)
                self.assertEqual(resolved["name"], "generic.md")
                self.assertTrue(Path(resolved["path"]).is_file())

    def test_unknown_chain_raises_value_error(self):
        with self.assertRaises(ValueError):
            chain_mod.get_report_template("no-such-chain")

    def test_declared_missing_template_raises_with_search_paths(self):
        chains = {"broken": {"title": "t", "reportTemplate": "absent.md",
                             "steps": [{"name": "s1", "outputs": [], "requiredInputs": []}]}}
        with mock.patch.object(chain_mod, "_load_chains", return_value=chains):
            with self.assertRaises(chain_mod.ChainConfigError) as ctx:
                chain_mod.get_report_template("broken")
        message = str(ctx.exception)
        self.assertIn("absent.md", message)
        self.assertIn(str(chain_mod._USER_TEMPLATES), message)
        self.assertIn(str(chain_mod._BUILTIN_TEMPLATES), message)

    def test_user_override_wins_over_builtin(self):
        with mock.patch.object(chain_mod, "_USER_TEMPLATES", _REPO_TEMPLATES):
            resolved = chain_mod.get_report_template("default")
            self.assertEqual(resolved["path"], str(_REPO_TEMPLATES / "generic.md"))

    def test_validate_chain_rejects_path_like_report_template(self):
        with self.assertRaises(chain_mod.ChainConfigError):
            chain_mod._validate_chain("bad", {
                "reportTemplate": "../../secrets.txt",
                "steps": [{"name": "s1", "outputs": [], "requiredInputs": []}],
            }, "test")

    def test_validate_chain_rejects_empty_report_template(self):
        with self.assertRaises(chain_mod.ChainConfigError):
            chain_mod._validate_chain("bad", {
                "reportTemplate": "  ",
                "steps": [{"name": "s1", "outputs": [], "requiredInputs": []}],
            }, "test")


class OutputExposureTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_session_dir = chain_mod._SESSION_DIR
        chain_mod._SESSION_DIR = Path(self.temp_dir.name) / "sessions"

    def tearDown(self):
        chain_mod._SESSION_DIR = self.old_session_dir
        self.temp_dir.cleanup()

    def test_list_chains_includes_report_template(self):
        entries = {item["name"]: item for item in chain_mod.list_chains()}
        self.assertEqual(entries["alert-ticket"]["reportTemplate"], "ticket.md")
        self.assertEqual(entries["default"]["reportTemplate"], "generic.md")

    def test_get_context_includes_resolved_report_template(self):
        session = chain_mod.start_session("default", problem_description="测试问题")
        try:
            context = chain_mod.get_context(session["session_id"])
            self.assertIn("report_template", context)
            self.assertEqual(context["report_template"]["name"], "generic.md")
            self.assertTrue(Path(context["report_template"]["path"]).is_file())
        finally:
            path = chain_mod._SESSION_DIR / f"{session['session_id']}.json"
            path.unlink(missing_ok=True)

    def test_get_context_degrades_to_error_field_on_missing_template(self):
        session = chain_mod.start_session("default", problem_description="测试问题")
        try:
            with mock.patch.object(chain_mod, "get_report_template",
                                   side_effect=chain_mod.ChainConfigError("missing")):
                context = chain_mod.get_context(session["session_id"])
            self.assertIn("error", context["report_template"])
        finally:
            path = chain_mod._SESSION_DIR / f"{session['session_id']}.json"
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
