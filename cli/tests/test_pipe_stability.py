"""管道编排稳定性测试 — 解析错误 JSON 化与 --limit/--max 别名。"""

import contextlib
import io
import json
import unittest

from seek_cli.cli import _build_parser


class PipeStabilityTest(unittest.TestCase):
    def _parse_capture(self, argv):
        """执行 parse_args 并捕获 stdout/stderr。

        Returns:
            (args|None, stdout_text, stderr_text, exit_code|None)
            解析成功时 exit_code 为 None；失败时为 SystemExit.code。
        """
        parser = _build_parser()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                args = parser.parse_args(argv)
                return args, out.getvalue(), err.getvalue(), None
            except SystemExit as e:
                return None, out.getvalue(), err.getvalue(), e.code

    # ── 解析错误输出 JSON 到 stdout ──

    def test_unknown_option_emits_json_on_stdout(self):
        _, out, err, code = self._parse_capture(["sls", "query", "--bogus-flag"])
        self.assertEqual(code, 2)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "ARGPARSE_ERROR")
        self.assertIn("usage", err.lower())

    def test_invalid_choice_emits_json(self):
        _, out, err, code = self._parse_capture(["no-such-command"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["error"]["code"], "ARGPARSE_ERROR")

    def test_missing_required_arg_emits_json(self):
        # sls logs 的 --env 为必填
        _, out, err, code = self._parse_capture(["sls", "logs", "proj"])
        self.assertEqual(code, 2)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "ARGPARSE_ERROR")

    def test_nested_subcommand_missing_emits_json(self):
        # db conn 的下一级子命令为必填（嵌套子命令组同样继承 JSON 错误行为）
        _, out, err, code = self._parse_capture(["db", "conn"])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["error"]["code"], "ARGPARSE_ERROR")

    def test_help_does_not_enter_error_path(self):
        _, out, err, code = self._parse_capture(["sls", "query", "--help"])
        self.assertEqual(code, 0)
        self.assertIn("usage", out.lower())

    # ── --limit 与 --max 等价 ──

    def test_limit_alias_for_sls_query(self):
        args_limit, _, _, c1 = self._parse_capture(
            ["sls", "query", "proj", "--env", "daily", "--query", "q", "--limit", "50"])
        args_max, _, _, c2 = self._parse_capture(
            ["sls", "query", "proj", "--env", "daily", "--query", "q", "--max", "50"])
        self.assertIsNone(c1)
        self.assertIsNone(c2)
        self.assertEqual(args_limit.max, 50)
        self.assertEqual(args_max.max, args_limit.max)

    def test_limit_alias_for_db_query(self):
        args, _, _, code = self._parse_capture(
            ["db", "query", "--conn", "prof", "--sql", "select 1", "--limit", "10"])
        self.assertIsNone(code)
        self.assertEqual(args.max, 10)

    def test_limit_alias_for_trace_query(self):
        args, _, _, code = self._parse_capture(
            ["trace", "query", "proj", "--env", "daily", "--trace-id", "t1", "--limit", "5"])
        self.assertIsNone(code)
        self.assertEqual(args.max, 5)

    def test_native_limit_commands_unchanged(self):
        # chain sessions 原生 --limit 不受影响
        args, _, _, code = self._parse_capture(["chain", "sessions", "--limit", "10"])
        self.assertIsNone(code)
        self.assertEqual(args.limit, 10)


if __name__ == "__main__":
    unittest.main()
