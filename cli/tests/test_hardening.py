"""seek CLI CR 整改回归测试。"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from seek_cli import chain, config
from seek_cli.commands import db, doctor
from seek_cli.commands import chain as chain_commands


def _evidence(status="FOUND"):
    data = {
        "status": status,
        "sources": [{"tool": "test", "reference": "fixture"}],
        "boundary": "unit test fixture",
    }
    if status != "FOUND":
        data["reason"] = "fixture reason"
    return data


class ReadOnlySqlTest(unittest.TestCase):
    def test_accepts_read_only_queries(self):
        for sql in (
            "SELECT * FROM events",
            "WITH recent AS (SELECT * FROM events) SELECT * FROM recent",
            "EXPLAIN SELECT * FROM events",
            "SELECT 'DELETE FROM events' AS example",
            "/* report */ SELECT * FROM events;",
        ):
            self.assertEqual("", db._validate_read_only_sql(sql))

    def test_rejects_write_and_multi_statement_queries(self):
        for sql in (
            "DELETE FROM events",
            "WITH doomed AS (DELETE FROM events RETURNING id) SELECT * FROM doomed",
            "SELECT * FROM events; DELETE FROM events",
            "SELECT * INTO OUTFILE '/tmp/export' FROM events",
            "SELECT * FROM events FOR UPDATE",
            "SELECT * FROM events FOR UPDATE OF events",
            "SELECT * FROM events FOR SHARE",
            "SELECT * FROM events LOCK IN SHARE MODE",
            "SELECT 1 /*!50100 INTO OUTFILE '/tmp/export' */",
            "SELECT 1 /*!50100; DELETE FROM events */",
        ):
            self.assertTrue(db._validate_read_only_sql(sql), sql)

    def test_rejected_query_does_not_call_dms(self):
        args = SimpleNamespace(database="db-1", sql="DROP TABLE events")
        with patch.object(db.dms_client, "call_dms") as call_dms:
            result = db.cmd_db_query(args)
        self.assertEqual("error", result["status"])
        self.assertEqual("READ_ONLY_SQL_REQUIRED", result["error"]["code"])
        call_dms.assert_not_called()


class ChainContractTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_session_dir = chain._SESSION_DIR
        chain._SESSION_DIR = Path(self.temp_dir.name) / "sessions"

    def tearDown(self):
        chain._SESSION_DIR = self.old_session_dir
        self.temp_dir.cleanup()

    def test_first_step_requires_external_input(self):
        session = chain.start_session("alert-ticket")
        validation = chain.validate_step(session["session_id"], 1)
        self.assertFalse(validation["valid"])
        self.assertEqual(["flow_id"], validation["missing_inputs"])

    def test_problem_description_satisfies_descriptive_first_input(self):
        session = chain.start_session("default", problem_description="service error")
        self.assertTrue(chain.validate_step(session["session_id"], 1)["valid"])

    def test_problem_description_satisfies_all_descriptive_chains(self):
        descriptive_chains = (
            ("default", "service error"),
            ("notification", "电话通知没收到"),
            ("cron-task-health", "MetricSyncTask 是否每日触发"),
            ("emergency-response", "凌晨误告警风暴需要应急止血"),
            ("emergency-stuck-task", "变更卡住需要应急推进"),
        )
        for chain_name, problem in descriptive_chains:
            session = chain.start_session(chain_name, problem_description=problem)
            validation = chain.validate_step(session["session_id"], 1)
            self.assertTrue(validation["valid"], f"{chain_name}: {validation.get('reason')}")

    def test_complete_requires_all_declared_outputs(self):
        session = chain.start_session("default", problem_description="service error")
        chain.complete_step(session["session_id"], {"target_project": "qt"}, evidence=_evidence())
        with self.assertRaisesRegex(ValueError, "missing declared fields"):
            chain.complete_step(session["session_id"], {"environment": "daily"})

    def test_declared_output_must_come_from_its_producer(self):
        session = chain.start_session("default", problem_description="service error")
        session_id = session["session_id"]
        chain.complete_step(session_id, {"target_project": "qt"}, evidence=_evidence())
        chain.complete_step(session_id, {
            "deployed_branch": "main",
            "deployed_commit": "abc",
            "deploy_time": "now",
            "recent_changes": [],
            "environment": "daily",
        }, evidence=_evidence())
        chain.complete_step(session_id, {
            "error_logs": [],
            "exception_stack": "",
            "log_patterns": [],
            "timeline": [],
        }, evidence=_evidence(status="NO_DATA"))
        with self.assertRaisesRegex(ValueError, "undeclared fields"):
            chain.complete_step(session_id, {
                "call_chain_analysis": {},
                "upstream_downstream": [],
                "trace_info": {},
                "deployed_branch": "forged",
            }, evidence=_evidence())

    def test_initial_context_cannot_forge_produced_input(self):
        session = chain.start_session("default", initial_context={
            "alert_or_error_description": "service error",
            "environment": "forged",
        })
        self.assertTrue(chain.validate_step(session["session_id"], 1)["valid"])
        chain.complete_step(session["session_id"], {"target_project": "qt"}, evidence=_evidence())
        self.assertTrue(chain.validate_step(session["session_id"], 2)["valid"])
        chain.complete_step(session["session_id"], {
            "deployed_branch": "main",
            "deployed_commit": "abc",
            "deploy_time": "now",
            "recent_changes": [],
            "environment": "daily",
        }, evidence=_evidence())
        self.assertTrue(chain.validate_step(session["session_id"], 3)["valid"])

    def test_command_rejects_non_object_outputs(self):
        session = chain.start_session("default", problem_description="service error")
        result = chain_commands.cmd_chain_complete(SimpleNamespace(
            session=session["session_id"], outputs='["bad"]', summary="",
        ))
        self.assertEqual("error", result["status"])
        self.assertEqual("BAD_JSON", result["error"]["code"])


class DoctorTest(unittest.TestCase):
    def test_live_check_skipped_is_incomplete(self):
        project = {
            "environments": {
                "prod": {
                    "platforms": [{
                        "type": "sls",
                        "enabled": True,
                        "config": {"endpoint": "endpoint", "project": "project", "logstore": "store"},
                    }],
                },
            },
        }
        with patch.object(doctor.config, "list_projects", return_value=[{"name": "p"}]), \
             patch.object(doctor.config, "get_project", return_value=project), \
             patch.object(doctor, "_live_check", return_value={"status": "skipped", "detail": "no creds"}), \
             patch.object(doctor, "_db_conn_checks", return_value=[]):
            result = doctor.cmd_doctor(SimpleNamespace(no_live=False))
        self.assertEqual("error", result["status"])
        self.assertEqual("DOCTOR_INCOMPLETE", result["error"]["code"])
        self.assertEqual(1, result["data"]["skipped"])


class ConfigWriteTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_user_config = config._USER_CONFIG
        config._USER_CONFIG = Path(self.temp_dir.name) / "projects.json"

    def tearDown(self):
        config._USER_CONFIG = self.old_user_config
        self.temp_dir.cleanup()

    def test_add_project_writes_valid_json(self):
        config.add_project("project-a", description="first")
        config.add_project("project-b", description="second")
        saved = json.loads(config._USER_CONFIG.read_text(encoding="utf-8"))
        self.assertEqual("first", saved["projects"]["project-a"]["description"])
        self.assertEqual("second", saved["projects"]["project-b"]["description"])

    def test_failed_atomic_write_preserves_previous_config(self):
        config._USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        original = '{"projects":{"stable":{"description":"keep"}}}'
        config._USER_CONFIG.write_text(original, encoding="utf-8")
        with patch.object(config.os, "replace", side_effect=OSError("disk failure")):
            with self.assertRaisesRegex(OSError, "disk failure"):
                config._save_user_config({"projects": {"new": {}}})
        self.assertEqual(original, config._USER_CONFIG.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
