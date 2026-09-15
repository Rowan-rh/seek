"""插件发现和 Provider 边界测试。"""

import unittest
from unittest.mock import patch

from seek_cli.commands import plugin as plugin_cmd
from seek_cli.plugins import PluginMetadata, ProviderManifest, SeekPlugin
from seek_cli.plugins.alibaba import AlibabaPlugin
from seek_cli.plugins.registry import PluginRegistry


class ExamplePlugin(SeekPlugin):
    metadata = PluginMetadata(
        id="example",
        name="Example",
        version="1.0.0",
        description="test plugin",
        providers=(ProviderManifest(
            id="example",
            name="Example Provider",
            description="test provider",
            capabilities=("logs.query",),
        ),),
    )


class PluginTest(unittest.TestCase):
    def test_builtin_alibaba_provider_exposes_legacy_services(self):
        plugin = AlibabaPlugin()
        self.assertEqual("alibaba", plugin.metadata.id)
        self.assertEqual("seek_cli.integrations.sls_client", plugin._SERVICE_MODULES["sls"])
        self.assertTrue(hasattr(plugin.service("sls"), "query_logs"))

    def test_entry_point_plugin_is_discovered(self):
        class EntryPoint:
            name = "example"
            value = "example_seek_plugin:get_plugin"

            def load(self):
                return ExamplePlugin

        registry = PluginRegistry()
        with patch("seek_cli.plugins.registry._entry_points", return_value=[EntryPoint()]):
            self.assertEqual(
                ["alibaba", "example"],
                [plugin.metadata.id for plugin in registry.plugins()],
            )
        self.assertEqual("example", registry.get_provider("example").metadata.id)

    def test_broken_entry_point_is_reported_without_breaking_builtin(self):
        class BrokenEntryPoint:
            name = "broken"
            value = "broken:plugin"

            def load(self):
                raise ImportError("optional dependency missing")

        registry = PluginRegistry()
        with patch("seek_cli.plugins.registry._entry_points", return_value=[BrokenEntryPoint()]):
            self.assertEqual(["alibaba"], [plugin.metadata.id for plugin in registry.plugins()])
            self.assertEqual("ImportError: optional dependency missing", registry.load_errors()[0]["error"])

    def test_plugin_list_is_json_contract(self):
        result = plugin_cmd.cmd_plugin_list(None)
        self.assertEqual("ok", result["status"])
        self.assertGreaterEqual(result["data"]["count"], 1)
        self.assertEqual("seek.plugins", result["data"]["entryPointGroup"])


if __name__ == "__main__":
    unittest.main()
