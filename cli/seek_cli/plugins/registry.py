"""插件发现、注册和 Provider 查找。"""

from importlib import metadata as importlib_metadata
from typing import Any, Dict, Iterable, List, Optional

from seek_cli.plugins.api import PluginError, SeekPlugin, validate_plugin
from seek_cli.plugins.alibaba import AlibabaPlugin


ENTRY_POINT_GROUP = "seek.plugins"


class PluginRegistry:
    """进程级插件注册表。

    内置插件和第三方 entry point 都经过同一套校验。单个坏插件只会出现在
    ``load_errors``，不会让 ``seek chain`` 或 ``seek capabilities`` 整体不可用。
    """

    def __init__(self) -> None:
        self._plugins: Dict[str, SeekPlugin] = {}
        self._load_errors: List[Dict[str, str]] = []
        self._discovered = False

    def register(self, plugin: SeekPlugin) -> None:
        plugin = validate_plugin(plugin)
        plugin_id = plugin.metadata.id
        if plugin_id in self._plugins:
            raise PluginError(f"duplicate plugin id: {plugin_id}")
        self._plugins[plugin_id] = plugin

    def discover(self) -> "PluginRegistry":
        if self._discovered:
            return self
        self._discovered = True
        self.register(AlibabaPlugin())
        for entry_point in _entry_points():
            try:
                loaded = entry_point.load()
                plugin = loaded() if isinstance(loaded, type) or callable(loaded) else loaded
                self.register(plugin)
            except Exception as exc:
                self._load_errors.append({
                    "name": getattr(entry_point, "name", "unknown"),
                    "value": getattr(entry_point, "value", "unknown"),
                    "error": f"{type(exc).__name__}: {exc}",
                })
        return self

    def plugins(self) -> List[SeekPlugin]:
        self.discover()
        return [self._plugins[key] for key in sorted(self._plugins)]

    def get_plugin(self, plugin_id: str) -> SeekPlugin:
        self.discover()
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            available = ", ".join(sorted(self._plugins)) or "none"
            raise PluginError(f"plugin '{plugin_id}' not found; available: {available}")
        return plugin

    def get_provider(self, provider_id: str) -> SeekPlugin:
        self.discover()
        for plugin in self._plugins.values():
            if any(provider.id == provider_id for provider in plugin.metadata.providers):
                return plugin
        raise PluginError(f"provider '{provider_id}' not found")

    def load_errors(self) -> List[Dict[str, str]]:
        self.discover()
        return list(self._load_errors)

    def register_cli(self, subparsers: Any) -> None:
        """调用插件 CLI 扩展点；单个插件失败不影响内置命令。"""
        for plugin in self.plugins():
            try:
                plugin.register_cli(subparsers)
            except Exception as exc:
                self._load_errors.append({
                    "name": plugin.metadata.id,
                    "value": "register_cli",
                    "error": f"{type(exc).__name__}: {exc}",
                })

    def as_dicts(self) -> List[Dict[str, Any]]:
        return [plugin.metadata.as_dict() for plugin in self.plugins()]


def _entry_points() -> Iterable[Any]:
    """兼容 Python 3.8 到当前版本的 importlib.metadata API。"""
    points = importlib_metadata.entry_points()
    if hasattr(points, "select"):
        return points.select(group=ENTRY_POINT_GROUP)
    return points.get(ENTRY_POINT_GROUP, ())


_REGISTRY: Optional[PluginRegistry] = None


def get_registry() -> PluginRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = PluginRegistry()
    return _REGISTRY


def list_plugins() -> List[Dict[str, Any]]:
    return get_registry().as_dicts()


def get_plugin(plugin_id: str) -> SeekPlugin:
    return get_registry().get_plugin(plugin_id)


def get_provider(provider_id: str) -> SeekPlugin:
    return get_registry().get_provider(provider_id)
