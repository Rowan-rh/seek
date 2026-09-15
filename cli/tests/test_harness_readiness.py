"""Harness readiness、SEEK_HOME 与离线评测入口测试。"""

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from seek_cli import paths
from seek_cli.commands import harness

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNNER = _REPO_ROOT / "harness" / "run_evals.py"
_AGENT_RUNNER = _REPO_ROOT / "harness" / "run_agent_evals.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("seek_harness_runner", _RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SeekHomeTest(unittest.TestCase):
    def test_seek_home_override(self):
        with mock.patch.dict(os.environ, {"SEEK_HOME": "/tmp/seek-isolated"}):
            self.assertEqual(paths.seek_home(), Path("/tmp/seek-isolated"))
            self.assertEqual(paths.seek_path("sessions"), Path("/tmp/seek-isolated/sessions"))
            self.assertEqual(paths.seek_home_source(), "SEEK_HOME")

    def test_default_seek_home(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(paths.Path, "home", return_value=Path("/home/test")):
            self.assertEqual(paths.seek_home(), Path("/home/test/.seek"))
            self.assertEqual(paths.seek_home_source(), "default")

    def test_help_has_no_seek_home_side_effect(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = Path(temp_dir) / "state"
            env = os.environ.copy()
            env["SEEK_HOME"] = str(state)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            result = subprocess.run(
                [sys.executable, "-m", "seek_cli", "--help"],
                cwd=str(_REPO_ROOT / "cli"), env=env,
                capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(state.exists())


class HarnessCheckTest(unittest.TestCase):
    def test_storage_probe_uses_resolved_home(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            home = Path(temp_dir) / "state"
            with mock.patch.object(harness, "seek_home", return_value=home), \
                    mock.patch.object(harness, "seek_home_source", return_value="SEEK_HOME"):
                result = harness._check_storage()
            self.assertEqual(result["status"], "pass")
            self.assertTrue(home.is_dir())
            self.assertEqual([], list(home.glob(".harness-probe-*")))

    def test_failures_return_harness_not_ready(self):
        report = {
            "ready": False,
            "summary": {"pass": 0, "warning": 0, "failure": 1},
            "checks": [{"name": "storage", "status": "failure", "message": "denied"}],
        }
        with mock.patch.object(harness, "build_readiness_report", return_value=report):
            result = harness.cmd_harness_check(argparse.Namespace())
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"]["code"], "HARNESS_NOT_READY")
        self.assertEqual(result["data"], report)

    def test_optional_command_missing_is_warning(self):
        with mock.patch.object(harness.shutil, "which", return_value=None):
            checks = harness._check_external_commands()
        self.assertTrue(checks)
        self.assertTrue(all(item["status"] == "warning" for item in checks))


class HarnessRunnerTest(unittest.TestCase):
    def test_summarize_failure_returns_error(self):
        runner = _load_runner()
        report = runner.summarize([
            {"name": "ok", "status": "pass", "detail": "ok"},
            {"name": "bad", "status": "failure", "detail": "bad"},
        ])
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["summary"], {"total": 2, "passed": 1, "failed": 1})

    def test_runner_black_box_passes(self):
        result = subprocess.run(
            [sys.executable, str(_RUNNER)], cwd=str(_REPO_ROOT),
            capture_output=True, text=True, timeout=60,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["summary"]["failed"], 0)

    def test_agent_scenario_runner_replay_passes(self):
        result = subprocess.run(
            [sys.executable, str(_AGENT_RUNNER)], cwd=str(_REPO_ROOT),
            capture_output=True, text=True, timeout=60,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["mode"], "replay")
        self.assertEqual(payload["summary"], {"total": 25, "passed": 25, "failed": 0})


if __name__ == "__main__":
    unittest.main()
