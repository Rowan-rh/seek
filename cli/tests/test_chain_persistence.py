"""Chain definition and session persistence regression tests."""

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from seek_cli import chain
from seek_cli.commands import chain as chain_commands


class ChainPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.old_builtin = chain._BUILTIN_CHAINS
        self.old_user = chain._USER_CHAINS
        self.old_session_dir = chain._SESSION_DIR
        chain._BUILTIN_CHAINS = root / "builtin.json"
        chain._USER_CHAINS = root / "user.json"
        chain._SESSION_DIR = root / "sessions"
        chain._BUILTIN_CHAINS.write_text(json.dumps({"chains": {"sample": {"steps": [{
            "name": "first", "outputs": ["value"], "requiredInputs": [], "constraints": {},
        }]}}}), encoding="utf-8")

    def tearDown(self):
        chain._BUILTIN_CHAINS = self.old_builtin
        chain._USER_CHAINS = self.old_user
        chain._SESSION_DIR = self.old_session_dir
        self.temp_dir.cleanup()

    def test_path_like_session_id_is_rejected(self):
        with self.assertRaises(ValueError):
            chain.get_session("../outside")
        with self.assertRaises(ValueError):
            with chain._session_lock("../../outside"):
                pass

    def test_invalid_chain_file_reports_source_and_path(self):
        chain._USER_CHAINS.parent.mkdir(parents=True, exist_ok=True)

        chain._USER_CHAINS.write_text("{bad", encoding="utf-8")
        with self.assertRaisesRegex(chain.ChainConfigError, "user chain file"):
            chain.list_chains()

    def test_invalid_chain_step_is_rejected(self):
        chain._USER_CHAINS.parent.mkdir(parents=True, exist_ok=True)

        chain._USER_CHAINS.write_text(json.dumps({"chains": {"bad": {"steps": [{
            "name": "", "outputs": [], "requiredInputs": [],
        }]}}}), encoding="utf-8")
        with self.assertRaisesRegex(chain.ChainConfigError, "name"):
            chain.list_chains()

    def test_current_step_does_not_mutate_definition(self):
        session = chain.start_session("sample")
        step = chain.get_current_step(session["session_id"])
        self.assertIn("session_id", step)
        self.assertNotIn("session_id", chain.get_chain("sample")["steps"][0])

    def test_corrupt_session_is_isolated_in_listing(self):
        chain._SESSION_DIR.mkdir(parents=True)
        (chain._SESSION_DIR / "broken.json").write_text("{bad", encoding="utf-8")
        session = chain.start_session("sample")
        entries = chain.list_sessions()
        self.assertIn("corrupt", {entry["status"] for entry in entries})
        self.assertIn(session["session_id"], {entry["session_id"] for entry in entries})

    def test_failed_atomic_save_preserves_existing_session(self):
        session = chain.start_session("sample")
        path = chain._SESSION_DIR / f"{session['session_id']}.json"
        original = path.read_text(encoding="utf-8")
        with patch.object(chain.os, "replace", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(OSError, "disk failure"):
                chain._save_session({**session, "project": "changed"})
        self.assertEqual(original, path.read_text(encoding="utf-8"))

    def test_concurrent_provide_inputs_does_not_lose_keys(self):
        # 回归：读-改-写必须整体在会话锁内；读在锁外时并发注入互相覆盖。
        # 修复前该用例确定性失败（延迟放大窗口后仅剩最后一个线程的键）。
        session = chain.start_session("sample")
        sid = session["session_id"]
        original_get = chain.get_session

        def slow_get_session(session_id):
            time.sleep(0.05)  # 放大读-改-写窗口，让丢更新必现
            return original_get(session_id)

        barrier = threading.Barrier(4)
        errors = []

        def worker(i):
            barrier.wait()
            try:
                chain.provide_inputs(sid, {f"key{i}": i})
            except Exception as exc:  # pragma: no cover - 仅收集意外异常
                errors.append(exc)

        with patch.object(chain, "get_session", side_effect=slow_get_session):
            threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual([], errors)
        final = original_get(sid)
        for i in range(4):
            self.assertIn(f"key{i}", final["context"])

    def test_concurrent_complete_step_serializes(self):
        # 两个线程同时完成同一步骤：锁内串行化后恰好一成功一拒绝，
        # completed_steps 不出现重复条目。
        session = chain.start_session("sample")
        sid = session["session_id"]
        results = []
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            try:
                chain.complete_step(sid, outputs={"value": "x"})
                results.append("ok")
            except ValueError:
                results.append("rejected")

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(["ok", "rejected"], sorted(results))
        final = chain.get_session(sid)
        self.assertEqual("completed", final["status"])
        self.assertEqual(1, len(final["completed_steps"]))


class ChainCommandErrorCodeTest(unittest.TestCase):
    """命令层会话异常映射回归（对齐 CR P1-1/P2-2）。

    六个需要 session 的命令统一走 _guarded_session_call：
    - 非法 session_id（非 12 位小写 hex）→ BAD_ARGUMENT，属用户输入错误，
      不得冒泡到全局兜底误报 INTERNAL_ERROR。
    - 损坏会话文件（合法 id）→ CHAIN_CONFIG_ERROR，保留路径级诊断，
      不被 except ValueError 吞成 NOT_FOUND。
    - 合法格式但不存在 → NOT_FOUND（validate 例外，返回 VALIDATION_FAILED）。
    """

    _SESSION_COMMANDS = (
        chain_commands.cmd_chain_status,
        chain_commands.cmd_chain_step,
        chain_commands.cmd_chain_validate,
        chain_commands.cmd_chain_context,
        chain_commands.cmd_chain_report,
        chain_commands.cmd_chain_usage,
    )

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_session_dir = chain._SESSION_DIR
        chain._SESSION_DIR = Path(self.temp_dir.name) / "sessions"
        chain._SESSION_DIR.mkdir(parents=True)

    def tearDown(self):
        chain._SESSION_DIR = self.old_session_dir
        self.temp_dir.cleanup()

    def test_malformed_session_id_returns_bad_argument(self):
        for bad_id in ("../escape", "ABCDEF012345", "too-short", ""):
            for cmd in self._SESSION_COMMANDS:
                with self.subTest(bad_id=bad_id, cmd=cmd.__name__):
                    result = cmd(SimpleNamespace(session=bad_id, step=1))
                    self.assertEqual("error", result["status"])
                    self.assertEqual("BAD_ARGUMENT", result["error"]["code"])

    def test_corrupt_session_returns_chain_config_error(self):
        (chain._SESSION_DIR / "000000000000.json").write_text("{bad", encoding="utf-8")
        for cmd in self._SESSION_COMMANDS:
            with self.subTest(cmd=cmd.__name__):
                result = cmd(SimpleNamespace(session="000000000000", step=1))
                self.assertEqual("error", result["status"])
                self.assertEqual("CHAIN_CONFIG_ERROR", result["error"]["code"])
                self.assertIn("corrupt", result["error"]["message"])

    def test_wellformed_missing_session_returns_not_found(self):
        not_found_commands = (
            chain_commands.cmd_chain_status,
            chain_commands.cmd_chain_step,
            chain_commands.cmd_chain_context,
            chain_commands.cmd_chain_report,
            chain_commands.cmd_chain_usage,
        )
        for cmd in not_found_commands:
            with self.subTest(cmd=cmd.__name__):
                result = cmd(SimpleNamespace(session="000000000000", step=1))
                self.assertEqual("error", result["status"])
                self.assertEqual("NOT_FOUND", result["error"]["code"])


if __name__ == "__main__":
    unittest.main()
