"""chain start 首步输入前置校验与 chain provide 补注入测试。"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from seek_cli import chain
from seek_cli.commands import chain as chain_cmd

_CHAINS = {"chains": {
    # 首步外部输入为标识型（必须 --context 注入）
    "ticket-like": {"steps": [
        {"name": "init", "outputs": ["detail"], "requiredInputs": ["flow_id"], "constraints": {}},
        {"name": "analyze", "outputs": [], "requiredInputs": ["detail"], "constraints": {}},
    ]},
    # 首步外部输入为描述型（可被非空 --problem 满足）
    "desc-like": {"steps": [
        {"name": "identify", "outputs": [], "requiredInputs": ["task_id_or_description"], "constraints": {}},
    ]},
    # 首步 requiredInput 有声明生产步骤 → 不算外部输入
    "produced-like": {"steps": [
        {"name": "probe", "outputs": [], "requiredInputs": ["env_info"], "constraints": {}},
        {"name": "collect", "outputs": ["env_info"], "requiredInputs": [], "constraints": {}},
    ]},
}}


def _start_args(name, context=None, problem=""):
    return SimpleNamespace(name=name, project="", problem=problem, context=context, format="json")


class ChainStartInputsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.old_builtin = chain._BUILTIN_CHAINS
        self.old_user = chain._USER_CHAINS
        self.old_session_dir = chain._SESSION_DIR
        chain._BUILTIN_CHAINS = root / "builtin.json"
        chain._USER_CHAINS = root / "user.json"
        chain._SESSION_DIR = root / "sessions"
        chain._BUILTIN_CHAINS.write_text(json.dumps(_CHAINS), encoding="utf-8")

    def tearDown(self):
        chain._BUILTIN_CHAINS = self.old_builtin
        chain._USER_CHAINS = self.old_user
        chain._SESSION_DIR = self.old_session_dir
        self.temp_dir.cleanup()

    # ── firstStepInputs 能力发现 ──

    def test_list_chains_exposes_first_step_inputs(self):
        by_name = {c["name"]: c for c in chain.list_chains()}
        self.assertEqual(by_name["ticket-like"]["firstStepInputs"], ["flow_id"])
        self.assertEqual(by_name["desc-like"]["firstStepInputs"], ["task_id_or_description"])
        # 有生产者的 requiredInput 不算外部输入
        self.assertEqual(by_name["produced-like"]["firstStepInputs"], [])

    # ── chain start 前置校验 ──

    def test_start_missing_context_blocked_without_session(self):
        result = chain_cmd.cmd_chain_start(_start_args("ticket-like"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "MISSING_CONTEXT")
        self.assertEqual(result["data"]["missing_inputs"], ["flow_id"])
        self.assertEqual(result["data"]["required_inputs"], ["flow_id"])
        self.assertIn("--context", result["data"]["hint"])
        # 会话文件不落盘
        self.assertFalse(chain._SESSION_DIR.exists() and list(chain._SESSION_DIR.glob("*.json")))

    def test_start_missing_hint_mentions_problem_for_description_inputs(self):
        result = chain_cmd.cmd_chain_start(_start_args("desc-like"))
        self.assertEqual(result["error"]["code"], "MISSING_CONTEXT")
        self.assertIn("--problem", result["data"]["hint"])

    def test_start_problem_satisfies_description_input(self):
        result = chain_cmd.cmd_chain_start(_start_args("desc-like", problem="任务卡住不推进"))
        self.assertEqual(result["status"], "ok")
        self.assertIn("session", result["data"])

    def test_start_with_context_passes(self):
        result = chain_cmd.cmd_chain_start(
            _start_args("ticket-like", context='{"flow_id": "FLOW-1"}'))
        self.assertEqual(result["status"], "ok")
        session = chain.get_session(result["data"]["session"]["session_id"])
        self.assertEqual(session["context"]["flow_id"], "FLOW-1")

    def test_start_extra_context_keys_allowed(self):
        result = chain_cmd.cmd_chain_start(
            _start_args("ticket-like", context='{"flow_id": "FLOW-1", "extra_note": "n"}'))
        self.assertEqual(result["status"], "ok")

    def test_start_chain_not_found(self):
        result = chain_cmd.cmd_chain_start(_start_args("no-such-chain"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "CHAIN_NOT_FOUND")

    # ── chain provide 补注入 ──

    def _start_session_without_block(self, name="ticket-like"):
        # 直接走引擎建会话，模拟前置校验上线前遗留的缺键会话
        return chain.start_session(name)

    def test_provide_injects_inputs_and_validates(self):
        session = self._start_session_without_block()
        self.assertFalse(chain.validate_step(session["session_id"], 1)["valid"])
        result = chain_cmd.cmd_chain_provide(
            SimpleNamespace(session=session["session_id"],
                            inputs='{"flow_id": "FLOW-2"}', format="json"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["injected_keys"], ["flow_id"])
        self.assertTrue(result["data"]["validation"]["valid"])
        self.assertEqual(chain.get_session(session["session_id"])["context"]["flow_id"], "FLOW-2")

    def test_provide_completed_session_rejected(self):
        session = self._start_session_without_block("desc-like")
        chain.provide_inputs(session["session_id"], {"task_id_or_description": "x"})
        chain.complete_step(session["session_id"], outputs={}, summary="done")
        result = chain_cmd.cmd_chain_provide(
            SimpleNamespace(session=session["session_id"], inputs='{"flow_id": "F"}', format="json"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "SESSION_ERROR")

    def test_provide_step_name_conflict_rejected(self):
        session = self._start_session_without_block()
        result = chain_cmd.cmd_chain_provide(
            SimpleNamespace(session=session["session_id"], inputs='{"init": "x"}', format="json"))
        self.assertEqual(result["status"], "error")
        self.assertNotIn("init", chain.get_session(session["session_id"]).get("context", {}))

    def test_provide_bad_json_rejected(self):
        session = self._start_session_without_block()
        result = chain_cmd.cmd_chain_provide(
            SimpleNamespace(session=session["session_id"], inputs="{bad", format="json"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "BAD_JSON")

    def test_provide_session_not_found(self):
        result = chain_cmd.cmd_chain_provide(
            SimpleNamespace(session="no-such-session", inputs='{"flow_id": "F"}', format="json"))
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "SESSION_ERROR")


if __name__ == "__main__":
    unittest.main()
