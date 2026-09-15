"""Structured evidence and token usage contract tests."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from seek_cli import chain
from seek_cli.commands import chain as chain_commands


def evidence(status="FOUND", *, reason=None):
    value = {
        "status": status,
        "sources": [{"tool": "seek project list", "reference": "fixture-1"}],
        "boundary": "unit test",
    }
    if reason is not None:
        value["reason"] = reason
    return value


class ChainEvidenceUsageTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_session_dir = chain._SESSION_DIR
        chain._SESSION_DIR = Path(self.temp_dir.name) / "sessions"

    def tearDown(self):
        chain._SESSION_DIR = self.old_session_dir
        self.temp_dir.cleanup()

    def test_current_step_exposes_evidence_schema(self):
        session = chain.start_session("default", problem_description="service error")
        step = chain.get_current_step(session["session_id"])
        self.assertTrue(step["evidenceRequired"])
        self.assertEqual(sorted(chain.EVIDENCE_STATUSES), step["evidenceSchema"]["status"])

    def test_required_evidence_missing_rejected_without_advancing(self):
        session = chain.start_session("default", problem_description="service error")
        with self.assertRaises(chain.EvidenceValidationError):
            chain.complete_step(session["session_id"], {"target_project": "qt"})
        self.assertEqual(1, chain.get_session(session["session_id"])["current_step"])

    def test_legacy_session_without_contract_version_is_grandfathered(self):
        session = chain.start_session("default", problem_description="service error")
        session.pop("evidence_contract_version")
        chain._save_session(session)
        updated = chain.complete_step(session["session_id"], {"target_project": "qt"})
        self.assertEqual(2, updated["current_step"])

    def test_no_data_requires_reason(self):
        session = chain.start_session("default", problem_description="service error")
        with self.assertRaisesRegex(chain.EvidenceValidationError, "reason"):
            chain.complete_step(session["session_id"], {"target_project": "qt"},
                                evidence=evidence("NO_DATA"))

    def test_evidence_and_token_usage_persist_and_aggregate(self):
        session = chain.start_session("default", problem_description="service error")
        session_id = session["session_id"]
        first_evidence = evidence()
        chain.complete_step(session_id, {"target_project": "qt"},
                            evidence=first_evidence,
                            token_usage={"input_tokens": 100, "output_tokens": 20,
                                         "cached_input_tokens": 50})
        chain.complete_step(session_id, {
            "deployed_branch": "main", "deployed_commit": "abc", "deploy_time": "now",
            "recent_changes": [], "environment": "daily",
        }, evidence=evidence("NO_DATA", reason="no recent deployment"))
        stored = chain.get_session(session_id)
        self.assertEqual(first_evidence, stored["step_evidence"]["identify-service"])
        context = chain.get_context(session_id)
        self.assertEqual(first_evidence, context["step_evidence"]["identify-service"])
        self.assertFalse(context["token_usage"]["used_for_scoring"])
        usage = chain.get_token_usage(session_id)
        self.assertEqual(100, usage["totals"]["input_tokens"])
        self.assertEqual(120, usage["totals"]["total_tokens"])
        self.assertEqual(20, usage["totals"]["output_tokens"])
        self.assertFalse(usage["complete"])
        self.assertFalse(usage["used_for_scoring"])

    def test_amend_preserves_original_and_updates_current_evidence(self):
        session = chain.start_session("default", problem_description="service error")
        session_id = session["session_id"]
        original = evidence()
        chain.complete_step(session_id, {"target_project": "qt"}, evidence=original)
        corrected = evidence("NO_DATA", reason="project mapping not found")
        updated = chain.amend_step(session_id, 1, {"target_project": ""},
                                   summary="corrected", evidence=corrected)
        self.assertEqual(original, updated["completed_steps"][0]["evidence"])
        self.assertEqual(corrected, updated["amendments"][-1]["evidence"])
        self.assertEqual(corrected, updated["step_evidence"]["identify-service"])

    def test_evidence_source_requires_tool_and_reference(self):
        session = chain.start_session("default", problem_description="service error")
        invalid = {"status": "FOUND", "sources": [{"tool": "seek project list"}],
                   "boundary": "unit test"}
        with self.assertRaisesRegex(chain.EvidenceValidationError, "reference"):
            chain.complete_step(session["session_id"], {"target_project": "qt"},
                                evidence=invalid)

    def test_invalid_token_usage_rejected_without_advancing(self):
        session = chain.start_session("default", problem_description="service error")
        for usage in ({}, {"input_tokens": -1}, {"input_tokens": True}, {"unknown": 1}):
            with self.subTest(usage=usage), self.assertRaises(chain.TokenUsageValidationError):
                chain.complete_step(session["session_id"], {"target_project": "qt"},
                                    evidence=evidence(), token_usage=usage)
        self.assertEqual(1, chain.get_session(session["session_id"])["current_step"])

    def test_command_returns_specific_validation_codes(self):
        session = chain.start_session("default", problem_description="service error")
        base = {"session": session["session_id"], "summary": "", "format": "json"}
        result = chain_commands.cmd_chain_complete(SimpleNamespace(
            **base, outputs='{"target_project":"qt"}', evidence=None, token_usage=None))
        self.assertEqual("EVIDENCE_REQUIRED", result["error"]["code"])
        result = chain_commands.cmd_chain_complete(SimpleNamespace(
            **base, outputs='{"target_project":"qt"}',
            evidence='{"status":"FOUND","sources":[{"tool":"x","reference":"y"}],"boundary":"b"}',
            token_usage='{"input_tokens":true}'))
        self.assertEqual("BAD_TOKEN_USAGE", result["error"]["code"])

    def test_usage_command_reports_missing_session(self):
        # 合法格式(12位hex)但不存在 → NOT_FOUND；畸形 id → BAD_ARGUMENT 见 test_chain_persistence
        result = chain_commands.cmd_chain_usage(SimpleNamespace(session="000000000000"))
        self.assertEqual("NOT_FOUND", result["error"]["code"])


if __name__ == "__main__":
    unittest.main()
