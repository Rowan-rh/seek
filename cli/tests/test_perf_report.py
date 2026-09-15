"""perf report/clear 测试 — 聚合口径、窗口与过滤、损坏行容错、清理行为。"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from seek_cli import perf_log
from seek_cli.commands import perf as perf_cmd


class PerfReportTestBase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_dir = perf_log._LOG_DIR
        self.old_file = perf_log._LOG_FILE
        perf_log._LOG_DIR = Path(self.temp_dir.name)
        perf_log._LOG_FILE = perf_log._LOG_DIR / "perf.jsonl"
        self.addCleanup(self._restore)

    def _restore(self):
        perf_log._LOG_DIR = self.old_dir
        perf_log._LOG_FILE = self.old_file
        self.temp_dir.cleanup()

    def _write_records(self, *records):
        lines = [json.dumps(r, ensure_ascii=False) for r in records]
        perf_log._LOG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _args(self, time="24h", keyword="", session=""):
        return SimpleNamespace(time=time, keyword=keyword, session=session)


def _rec(command, span, duration_ms, status="success", session_id=None,
         minutes_ago=0):
    entry = {
        "timestamp": (datetime.now() - timedelta(minutes=minutes_ago)).isoformat(),
        "command": command,
        "span": span,
        "status": status,
        "duration_ms": duration_ms,
    }
    if session_id:
        entry["session_id"] = session_id
    return entry


class PerfReportAggregationTest(PerfReportTestBase):
    def test_aggregates_commands_and_io_spans(self):
        self._write_records(
            _rec("sls query", "command", 100, minutes_ago=10),
            _rec("sls query", "command", 200, minutes_ago=9),
            _rec("sls query", "command", 300, minutes_ago=8),
            _rec("sls query", "command", 1000, status="error", minutes_ago=7),
            _rec("sls p/l", "sls_query", 50, minutes_ago=10),
            _rec("sls p/l", "sls_query", 150, minutes_ago=9),
            _rec("dms executeScript", "dms_call", 900, minutes_ago=8),
        )
        result = perf_cmd.cmd_perf_report(self._args())
        self.assertEqual("ok", result["status"])
        data = result["data"]
        self.assertEqual(7, data["totalRecords"])
        self.assertEqual(0, data["skippedCorrupt"])

        # 命令级分组：sls query，4 条 1 错误，totalMs=1600
        commands = {c["command"]: c for c in data["commands"]}
        cmd_group = commands["sls query"]
        self.assertEqual(4, cmd_group["count"])
        self.assertEqual(1, cmd_group["errors"])
        self.assertEqual(1600, cmd_group["totalMs"])
        self.assertEqual(400, cmd_group["avgMs"])
        # nearest-rank: p50 = ceil(0.5*4)=2 → 200；p95 = ceil(0.95*4)=4 → 1000
        self.assertEqual(200, cmd_group["p50Ms"])
        self.assertEqual(1000, cmd_group["p95Ms"])
        self.assertEqual(1000, cmd_group["maxMs"])

        # IO 级分组：按 (span, command) 组合键
        io = {(s["span"], s["label"]): s for s in data["ioSpans"]}
        self.assertIn(("sls_query", "sls p/l"), io)
        self.assertIn(("dms_call", "dms executeScript"), io)
        self.assertEqual(2, io[("sls_query", "sls p/l")]["count"])
        self.assertEqual(200, io[("sls_query", "sls p/l")]["totalMs"])

        # 总量与占比：commandMs=1600，ioMs=50+150+900=1100 → 69%
        totals = data["totals"]
        self.assertEqual(4, totals["commandCount"])
        self.assertEqual(1600, totals["commandMs"])
        self.assertEqual(3, totals["ioCount"])
        self.assertEqual(1100, totals["ioMs"])
        self.assertEqual(69, totals["ioSharePct"])
        self.assertEqual(1, totals["errorCommands"])
        self.assertEqual(0, totals["errorIoCalls"])

        # hint：占比 ≥60 → IO 并行方向 + 近似语义边界说明
        self.assertIn("IO 并行", data["hint"])
        self.assertIn("粗略近似", data["hint"])

    def test_low_io_share_hint_suggests_batching(self):
        self._write_records(
            _rec("chain step", "command", 4000, minutes_ago=5),
            _rec("sls p/l", "sls_query", 100, minutes_ago=5),
        )
        result = perf_cmd.cmd_perf_report(self._args())
        # 100/4000 = 2.5% → round=2 → 低占比方向
        self.assertIn("批量化", result["data"]["hint"])

    def test_window_excludes_old_records(self):
        self._write_records(
            _rec("sls query", "command", 100, minutes_ago=30),
            _rec("sls query", "command", 200, minutes_ago=60 * 40),  # 40h 前，窗外
        )
        result = perf_cmd.cmd_perf_report(self._args(time="24h"))
        data = result["data"]
        self.assertEqual(1, data["totalRecords"])
        self.assertEqual(1, data["totals"]["commandCount"])
        self.assertEqual(100, data["totals"]["commandMs"])

    def test_session_and_keyword_filters(self):
        self._write_records(
            _rec("sls query", "command", 100, session_id="s1", minutes_ago=5),
            _rec("deploy env", "command", 200, session_id="s2", minutes_ago=5),
            _rec("sls p/l", "sls_query", 50, session_id="s1", minutes_ago=5),
        )
        # 会话过滤
        result = perf_cmd.cmd_perf_report(self._args(session="s1"))
        data = result["data"]
        self.assertEqual(2, data["totalRecords"])
        self.assertEqual("s1", data["filters"]["session"])
        self.assertEqual(1, data["totals"]["commandCount"])
        sessions = {s["session_id"]: s for s in data["sessions"]}
        self.assertEqual(1, sessions["s1"]["commandCount"])
        self.assertEqual(100, sessions["s1"]["commandMs"])
        self.assertEqual(50, sessions["s1"]["ioMs"])
        # keyword 过滤（大小写不敏感，命中 command 名与 IO 动作描述）
        result = perf_cmd.cmd_perf_report(self._args(keyword="SLS"))
        self.assertEqual(2, result["data"]["totalRecords"])
        self.assertEqual("SLS", result["data"]["filters"]["keyword"])

    def test_sessions_sorted_by_command_ms_desc(self):
        self._write_records(
            _rec("chain step", "command", 100, session_id="slow", minutes_ago=5),
            _rec("chain step", "command", 5000, session_id="hot", minutes_ago=5),
        )
        result = perf_cmd.cmd_perf_report(self._args())
        sessions = result["data"]["sessions"]
        self.assertEqual("hot", sessions[0]["session_id"])
        self.assertEqual("slow", sessions[1]["session_id"])


class PerfReportRobustnessTest(PerfReportTestBase):
    def test_skips_corrupt_lines(self):
        good = _rec("sls query", "command", 100, minutes_ago=5)
        perf_log._LOG_FILE.write_text(
            json.dumps(good) + "\nnot-a-json\n\n"
            + json.dumps({"command": "x"}) + "\n",  # 缺 timestamp
            encoding="utf-8")
        result = perf_cmd.cmd_perf_report(self._args())
        data = result["data"]
        self.assertEqual(1, data["totalRecords"])
        self.assertEqual(2, data["skippedCorrupt"])
        self.assertEqual(1, data["totals"]["commandCount"])

    def test_missing_file_returns_ok_with_empty_hint(self):
        result = perf_cmd.cmd_perf_report(self._args())
        self.assertEqual("ok", result["status"])
        data = result["data"]
        self.assertEqual(0, data["totalRecords"])
        self.assertEqual(0, data["totals"]["commandCount"])
        self.assertIn("无 command 记录", data["hint"])

    def test_invalid_time_range_returns_bad_argument(self):
        self._write_records(_rec("sls query", "command", 100, minutes_ago=5))
        result = perf_cmd.cmd_perf_report(self._args(time="not-a-range"))
        self.assertEqual("error", result["status"])
        self.assertEqual("BAD_ARGUMENT", result["error"]["code"])


class PerfClearTest(PerfReportTestBase):
    def test_clear_returns_count_and_empties_file(self):
        self._write_records(
            _rec("sls query", "command", 100, minutes_ago=5),
            _rec("sls p/l", "sls_query", 50, minutes_ago=5),
        )
        result = perf_cmd.cmd_perf_clear(SimpleNamespace())
        self.assertEqual("ok", result["status"])
        self.assertEqual(2, result["data"]["cleared"])
        self.assertEqual("", perf_log._LOG_FILE.read_text(encoding="utf-8").strip())
        # 清空后 report 无数据
        report = perf_cmd.cmd_perf_report(self._args())
        self.assertEqual(0, report["data"]["totalRecords"])

    def test_clear_missing_file_returns_zero(self):
        result = perf_cmd.cmd_perf_clear(SimpleNamespace())
        self.assertEqual("ok", result["status"])
        self.assertEqual(0, result["data"]["cleared"])


if __name__ == "__main__":
    unittest.main()
