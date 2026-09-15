"""插件与 Provider 能力发现命令。"""

from seek_cli.output import error, success
from seek_cli.plugins import PluginError, get_plugin, get_registry


def cmd_plugin_list(args) -> dict:
    """列出内置和通过 entry point 安装的插件。"""
    registry = get_registry()
    plugins = registry.as_dicts()
    return success({
        "plugins": plugins,
        "count": len(plugins),
        "loadErrors": registry.load_errors(),
        "entryPointGroup": "seek.plugins",
    }, message=f"已发现 {len(plugins)} 个插件")


def cmd_plugin_show(args) -> dict:
    """显示单个插件元数据和本地健康检查。"""
    try:
        plugin = get_plugin(args.name)
        health = plugin.healthcheck()
    except PluginError as exc:
        return error(str(exc), code="PLUGIN_NOT_FOUND")
    return success({
        "plugin": plugin.metadata.as_dict(),
        "health": dict(health),
    }, message=f"插件: {args.name}")
