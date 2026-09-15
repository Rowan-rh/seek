"""Declarative conditional chain routing regression tests."""

import json
import tempfile
import unittest
from pathlib import Path

from seek_cli import chain


def _sample_chain(condition=None, skip_outputs=None):
    return {
        "steps": [
            {
                "name": "decide",
                "requiredInputs": [],
                "outputs": ["flag", "kind"],
                "constraints": {},
            },
            {
                "name": "conditional",
                "requiredInputs": ["flag"],
                "outputs": ["value"],
                "constraints": {"requires_step": 1},
                "evidenceRequired": True,
                "when": condition or {"path": "decide.flag", "equals": True},
                "skipOutputs": {"value": ""} if skip_outputs is None else skip_outputs,
            },
            {
                "name": "finish",
                "requiredInputs": ["value"],
                "outputs": ["done"],
                "constraints": {"requires_step": 2},
            },
        ]
    }


class ConditionalChainRoutingTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.old_builtin = chain._BUILTIN_CHAINS
        self.old_user = chain._USER_CHAINS
        self.old_session_dir = chain._SESSION_DIR
        chain._BUILTIN_CHAINS = root / "builtin.json"
        chain._USER_CHAINS = root / "user.json"
        chain._SESSION_DIR = root / "sessions"
        self._write_chains({"sample": _sample_chain()})

    def tearDown(self):
        chain._BUILTIN_CHAINS = self.old_builtin
        chain._USER_CHAINS = self.old_user
        chain._SESSION_DIR = self.old_session_dir
        self.temp_dir.cleanup()

    def _write_chains(self, chains):
        chain._BUILTIN_CHAINS.write_text(
            json.dumps({"chains": chains}), encoding="utf-8")

    def test_false_condition_skips_evidence_step_and_supplies_outputs(self):
        session = chain.start_session("sample")
        updated = chain.complete_step(
            session["session_id"], {"flag": False, "kind": "none"})

        self.assertEqual(3, updated["current_step"])
        self.assertEqual({}, updated["step_evidence"])
        self.assertEqual(1, len(updated["skipped_steps"]))
        skipped = updated["skipped_steps"][0]
        self.assertEqual("conditional", skipped["name"])
        self.assertEqual({"path": "decide.flag", "equals": True}, skipped["condition"])
        self.assertFalse(skipped["condition_result"])
        self.assertEqual({"exists": True, "value": False}, skipped["observed"])
        self.assertEqual({"value": ""}, updated["step_outputs"]["conditional"])
        self.assertEqual({"value": ""}, updated["context"]["conditional"])
        self.assertTrue(chain.validate_step(session["session_id"], 3)["valid"])

        skipped_validation = chain.validate_step(session["session_id"], 2)
        self.assertFalse(skipped_validation["valid"])
        self.assertEqual("skipped", skipped_validation["state"])

        context = chain.get_context(session["session_id"])
        self.assertEqual([skipped], context["skipped_steps"])

    def test_true_condition_keeps_step_executable_and_evidence_required(self):
        session = chain.start_session("sample")
        updated = chain.complete_step(
            session["session_id"], {"flag": True, "kind": "match"})

        self.assertEqual(2, updated["current_step"])
        self.assertEqual([], updated["skipped_steps"])
        self.assertEqual("conditional", chain.get_current_step(session["session_id"])["name"])
        with self.assertRaises(chain.EvidenceValidationError):
            chain.complete_step(session["session_id"], {"value": "found"})

    def test_consecutive_false_conditions_can_complete_chain(self):
        multi = {
            "steps": [
                {"name": "decide", "requiredInputs": [], "outputs": ["flag"], "constraints": {}},
                {
                    "name": "optional-a", "requiredInputs": ["flag"], "outputs": ["a"],
                    "constraints": {"requires_step": 1},
                    "when": {"path": "decide.flag", "equals": True},
                    "skipOutputs": {"a": []},
                },
                {
                    "name": "optional-b", "requiredInputs": ["a"], "outputs": ["b"],
                    "constraints": {"requires_step": 2},
                    "when": {"path": "decide.flag", "in": [True]},
                    "skipOutputs": {"b": {}},
                },
            ]
        }
        self._write_chains({"multi": multi})
        session = chain.start_session("multi")
        updated = chain.complete_step(session["session_id"], {"flag": False})

        self.assertEqual("completed", updated["status"])
        self.assertEqual(["optional-a", "optional-b"],
                         [entry["name"] for entry in updated["skipped_steps"]])
        self.assertEqual({"a": []}, updated["step_outputs"]["optional-a"])
        self.assertEqual({"b": {}}, updated["step_outputs"]["optional-b"])
        self.assertIsNone(chain.get_current_step(session["session_id"]))

    def test_initial_context_can_skip_first_step(self):
        initial = {
            "steps": [{
                "name": "optional", "requiredInputs": [], "outputs": ["value"],
                "constraints": {},
                "when": {"path": "mode", "equals": "run"},
                "skipOutputs": {"value": "not-run"},
            }]
        }
        self._write_chains({"initial": initial})
        session = chain.start_session("initial", initial_context={"mode": "skip"})

        self.assertEqual("completed", session["status"])
        self.assertEqual("not-run", session["context"]["optional"]["value"])
        self.assertIsNone(chain.get_current_step(session["session_id"]))

    def test_legacy_session_without_routing_contract_remains_linear(self):
        session = chain.start_session("sample")
        session.pop("routing_contract_version")
        chain._save_session(session)

        updated = chain.complete_step(
            session["session_id"], {"flag": False, "kind": "none"})
        self.assertEqual(2, updated["current_step"])
        self.assertEqual([], updated["skipped_steps"])

    def test_equals_in_and_exists_conditions(self):
        context = {"decision": {"flag": True, "kind": "incident"}}
        self.assertTrue(chain._condition_matches(
            context, {"path": "decision.flag", "equals": True}))
        self.assertTrue(chain._condition_matches(
            context, {"path": "decision.kind", "in": ["incident", "change"]}))
        self.assertTrue(chain._condition_matches(
            context, {"path": "decision.kind", "exists": True}))
        self.assertTrue(chain._condition_matches(
            context, {"path": "decision.missing", "exists": False}))
        self.assertFalse(chain._condition_matches(
            context, {"path": "decision.missing", "equals": None}))

    def test_invalid_conditions_and_skip_outputs_are_rejected(self):
        invalid_cases = [
            ({"equals": True}, {"value": ""}, "path"),
            ({"path": "decide.flag", "equals": True, "in": [True]}, {"value": ""}, "exactly one"),
            ({"path": "decide.flag", "in": True}, {"value": ""}, "array"),
            ({"path": "decide.flag", "exists": "yes"}, {"value": ""}, "boolean"),
            ({"path": "decide..flag", "equals": True}, {"value": ""}, "path"),
            ({"path": "decide.flag", "equals": True, "script": "danger"}, {"value": ""}, "unsupported"),
            ({"path": "decide.flag", "equals": True}, {}, "exactly cover"),
        ]
        for condition, skip_outputs, message in invalid_cases:
            with self.subTest(condition=condition, skip_outputs=skip_outputs):
                self._write_chains({"bad": _sample_chain(condition, skip_outputs)})
                with self.assertRaisesRegex(chain.ChainConfigError, message):
                    chain.list_chains()


if __name__ == "__main__":
    unittest.main()
