"""Alibaba Provider 适配器。

这是现有内部集成的兼容适配层。核心命令通过这里按逻辑服务名获取实现，
未来可将本模块拆成独立的 ``seek-provider-alibaba`` 分发包，而无需改动
Chain、会话和报告代码。
"""

import importlib
import shutil
from typing import Any, Dict

from seek_cli import __version__
from seek_cli.plugins.api import PluginError, PluginMetadata, ProviderManifest, SeekPlugin


class AlibabaPlugin(SeekPlugin):
    metadata = PluginMetadata(
        id="alibaba",
        name="Alibaba integrations",
        version=__version__,
        description="Alibaba Cloud and Alibaba internal investigation integrations",
        providers=(ProviderManifest(
            id="alibaba",
            name="Alibaba Provider",
            description="A1, SLS, DingTalk, tickets, notifications, DMS and local DB",
            capabilities=(
                "deployment.inspect",
                "logs.query",
                "trace.query",
                "chat.search",
                "chat.send",
                "ticket.get",
                "ticket.search",
                "notification.query",
                "database.query",
            ),
            optional_dependencies=("aliyun-log-python-sdk", "PyMySQL"),
        ),),
    )

    _SERVICE_MODULES = {
        "a1": "seek_cli.integrations.a1_client",
        "sls": "seek_cli.integrations.sls_client",
        "dingtalk": "seek_cli.integrations.dingtalk_client",
        "expert": "seek_cli.integrations.expert_client",
        "roar": "seek_cli.integrations.roar_client",
        "dms": "seek_cli.integrations.dms_client",
        "db_store": "seek_cli.integrations.db_store",
        "db_local": "seek_cli.integrations.db_local",
    }

    def service(self, name: str) -> Any:
        module_name = self._SERVICE_MODULES.get(name)
        if not module_name:
            raise PluginError(
                f"provider '{self.metadata.id}' does not provide service '{name}'"
            )
        return importlib.import_module(module_name)

    def healthcheck(self) -> Dict[str, Any]:
        """检查本地可选依赖和外部命令，不访问线上业务数据。"""
        sls = self.service("sls")
        dms = self.service("dms")
        dms_config = getattr(dms, "_MCP_CONFIG", None)
        checks = {
            "slsSdk": {
                "available": bool(getattr(sls, "SDK_AVAILABLE", False)),
                "dependency": "aliyun-log-python-sdk",
            },
            "a1": {"available": bool(shutil.which("a1"))},
            "dws": {"available": bool(shutil.which("dws"))},
            "dms": {
                "available": bool(dms_config and dms_config.exists()),
                "mode": "stdio-jsonrpc",
                "config": str(dms_config) if dms_config else None,
            },
        }
        available = sum(1 for item in checks.values() if item.get("available"))
        status = "ready" if available == len(checks) else "partial" if available else "unavailable"
        return {
            "status": status,
            "checks": checks,
            "networkAccessed": False,
        }


def get_plugin() -> AlibabaPlugin:
    """Entry point 风格的工厂，便于未来拆包复用。"""
    return AlibabaPlugin()
