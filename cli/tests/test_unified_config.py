"""Unified configuration and version regression tests."""

import ast
import os
import runpy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from seek_cli import __version__, config, settings
from seek_cli.commands import config_cmd
from seek_cli.integrations import dms_client


class UnifiedConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_settings_file = settings.SETTINGS_FILE
        self.old_topology_candidates = config._TOPOLOGY_CANDIDATES
        settings.SETTINGS_FILE = Path(self.temp_dir.name) / "seek.json"
        config._TOPOLOGY_CANDIDATES = [Path(self.temp_dir.name) / "default-topology.md"]
        for key in ("QT_EXPERT_HOST", "ROAR_HOST", "SEEK_TOPOLOGY_FILE"):
            os.environ.pop(key, None)

    def tearDown(self):
        settings.SETTINGS_FILE = self.old_settings_file
        config._TOPOLOGY_CANDIDATES = self.old_topology_candidates
        self.temp_dir.cleanup()

    def test_default_hosts_are_reported_as_effective(self):
        expert = config_cmd._effective("hosts.expert")
        roar = config_cmd._effective("hosts.roar")
        self.assertEqual("default:built-in", expert["source"])
        self.assertEqual("default:built-in", roar["source"])
        self.assertIsNotNone(expert["value"])
        self.assertIsNotNone(roar["value"])

    def test_default_topology_reports_candidate_source(self):
        topology = config_cmd._effective("trace.topologyFile")
        self.assertEqual("default:candidate-missing", topology["source"])
        self.assertTrue(topology["value"].endswith("default-topology.md"))

        Path(topology["value"]).write_text("topology", encoding="utf-8")
        topology = config_cmd._effective("trace.topologyFile")
        self.assertEqual("default:candidate", topology["source"])

    def test_invalid_topology_setting_reports_actual_fallback(self):
        settings.set_setting("trace.topologyFile", str(Path(self.temp_dir.name) / "missing.md"))
        fallback = Path(self.temp_dir.name) / "default-topology.md"
        fallback.write_text("topology", encoding="utf-8")
        entry = config_cmd._effective("trace.topologyFile")
        self.assertEqual(str(fallback), entry["value"])
        self.assertEqual("fallback:invalid-seek.json", entry["source"])

    def test_explicit_unified_host_overrides_default(self):
        settings.set_setting("hosts.roar", "https://roar.example")
        entry = config_cmd._effective("hosts.roar")
        self.assertEqual("https://roar.example", entry["value"])
        self.assertEqual(str(settings.SETTINGS_FILE), entry["source"])

    def test_secret_remains_masked(self):
        settings.set_setting("sls.access_key_id", "LTAI123456")
        settings.set_setting("sls.access_key_secret", "secret-value")
        entry = config_cmd._effective("sls.access_key_secret")
        self.assertNotEqual("secret-value", entry["value"])
        self.assertIn("*", entry["value"])


class VersionSourceTest(unittest.TestCase):
    def test_setup_reads_runtime_version_source(self):
        setup_path = Path(__file__).parents[1] / "setup.py"
        with patch("setuptools.setup") as setup:
            runpy.run_path(str(setup_path), run_name="__main__")
        self.assertEqual(__version__, setup.call_args.kwargs["version"])

    def test_dms_client_uses_runtime_version(self):
        self.assertEqual(__version__, dms_client._CLIENT_INFO["version"])


if __name__ == "__main__":
    unittest.main()
