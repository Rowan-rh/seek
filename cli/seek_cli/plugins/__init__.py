"""seek 插件系统。

核心只依赖这里定义的插件协议。具体云厂商、观测平台和协作工具由 Provider
插件提供，第三方包通过 ``seek.plugins`` entry point 注册。
"""

from seek_cli.plugins.api import PluginError, PluginMetadata, ProviderManifest, SeekPlugin
from seek_cli.plugins.registry import get_plugin, get_provider, get_registry, list_plugins

__all__ = [
    "PluginError",
    "PluginMetadata",
    "ProviderManifest",
    "SeekPlugin",
    "get_plugin",
    "get_provider",
    "get_registry",
    "list_plugins",
]
