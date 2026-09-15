"""通用插件和 Provider 协议。

插件只需要声明自己的能力，并通过 ``service`` 暴露具体实现；Chain 引擎和 CLI
不应直接依赖 Provider SDK。
"""

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple


class PluginError(RuntimeError):
    """插件未安装、配置错误或加载失败。"""


@dataclass(frozen=True)
class ProviderManifest:
    """一个插件提供的逻辑 Provider 描述。"""

    id: str
    name: str
    description: str
    capabilities: Tuple[str, ...] = ()
    optional_dependencies: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "optionalDependencies": list(self.optional_dependencies),
        }


@dataclass(frozen=True)
class PluginMetadata:
    """插件公开元数据。"""

    id: str
    name: str
    version: str
    description: str
    providers: Tuple[ProviderManifest, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "providers": [provider.as_dict() for provider in self.providers],
        }


class SeekPlugin:
    """第三方插件的最小实现协议。

    插件包可以继承此类并实现 ``service``。CLI 扩展可覆盖
    ``register_cli``，但核心不会要求插件修改内置命令。
    """

    metadata = PluginMetadata(
        id="unknown",
        name="Unknown plugin",
        version="0",
        description="未声明元数据的插件",
    )

    def service(self, name: str) -> Any:
        raise PluginError(f"plugin '{self.metadata.id}' does not provide service '{name}'")

    def healthcheck(self) -> Mapping[str, Any]:
        """返回不主动访问业务数据的本地配置检查结果。"""
        return {"status": "unknown", "detail": "plugin has no healthcheck"}

    def command_capabilities(self) -> Mapping[str, Any]:
        """返回插件新增命令的 capabilities 描述，默认不新增命令。"""
        return {}

    def register_cli(self, subparsers: Any) -> None:
        """可选的 CLI 扩展点，默认不增加命令。"""
        return None


def validate_plugin(plugin: Any) -> SeekPlugin:
    """校验 entry point 返回值，避免坏插件破坏核心 CLI。"""
    if not isinstance(plugin, SeekPlugin):
        raise PluginError("plugin entry point must return a SeekPlugin instance")
    metadata = plugin.metadata
    if not isinstance(metadata, PluginMetadata) or not metadata.id.strip():
        raise PluginError("plugin metadata must contain a non-empty id")
    return plugin
