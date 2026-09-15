"""Notification evidence-chain contract tests."""

import tempfile
import unittest
from pathlib import Path

from seek_cli import chain


class NotificationEvidenceChainTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_session_dir = chain._SESSION_DIR
        chain._SESSION_DIR = Path(self.temp_dir.name) / "sessions"

    def tearDown(self):
        chain._SESSION_DIR = self.old_session_dir
        self.temp_dir.cleanup()

    def _complete(self, session_id, outputs):
        return chain.complete_step(session_id, outputs=outputs, evidence={
            "status": "FOUND",
            "sources": [{"tool": "test", "reference": "fixture"}],
            "boundary": "unit test fixture",
        })

    def test_first_step_uses_problem_description(self):
        session = chain.start_session("notification", problem_description="电话通知没收到")
        self.assertTrue(chain.validate_step(session["session_id"], 1)["valid"])
        with self.assertRaisesRegex(ValueError, "missing declared fields"):
            self._complete(session["session_id"], {"channel_type": "CALL"})

    def test_context_cannot_forge_interception_outputs(self):
        session = chain.start_session("notification", problem_description="通知未到", initial_context={
            "interception_type": "DROP",
        })
        session_id = session["session_id"]
        self._complete(session_id, {
            "channel_type": "CALL", "target_recipient": "masked",
            "environment": "prod", "event_time_range": "1h", "notification_event_key": "uuid-1",
        })
        self.assertFalse(chain.validate_step(session_id, 3)["valid"])

    def test_intercepted_path_completes_with_explicit_empty_outputs(self):
        session = chain.start_session("notification", problem_description="通知未到")
        session_id = session["session_id"]
        self._complete(session_id, {
            "channel_type": "CALL", "target_recipient": "masked",
            "environment": "prod", "event_time_range": "1h", "notification_event_key": "uuid-1",
        })
        self._complete(session_id, {
            "notification_group_evidence": "hit", "manual_silence_evidence": "match",
            "auto_silence_evidence": "", "drop_evidence": "",
            "interception_type": "SILENCE", "interception_rule_owner": "alarm_route_rule",
        })
        self._complete(session_id, {
            "delivery_branch": "upstream_intercepted", "branch_rationale": "manual silence matched",
        })
        self._complete(session_id, {
            "upstream_rule_evidence": "rule matched", "notice_service_evidence": "",
            "downstream_delivery_evidence": "", "recipient_schedule_evidence": "", "template_evidence": "",
        })
        result = self._complete(session_id, {
            "root_cause": "SILENCE prevented notification generation",
            "fix_suggestion": "adjust rule", "evidence_boundary": "prod 1h",
            "notification_knowledge_card": {"delivery_branch": "upstream_intercepted"},
        })
        self.assertEqual("completed", result["status"])


if __name__ == "__main__":
    unittest.main()
