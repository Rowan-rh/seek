"""能力发现命令。"""

from seek_cli import __version__, chain as chain_engine
from seek_cli.output import error, success
from seek_cli.plugins import get_registry


def _arg(name, **kwargs):
    return {"name": name, **kwargs}


def cmd_capabilities(args) -> dict:
    commands = {
        "capabilities": {"description": "输出命令、插件和数据契约", "subcommands": [], "args": []},
        "plugin": {"description": "插件与 Provider 管理", "subcommands": [
            {"name": "list", "description": "列出插件", "args": []},
            {"name": "show", "description": "查看插件", "args": [_arg("name", required=True)]},
        ]},
        "version": {"description": "输出版本和变更记录", "subcommands": [], "args": []},
        "project": {"description": "项目目录管理", "subcommands": [
            {"name": "list", "description": "列出项目", "args": []},
            {"name": "show", "description": "查看项目", "args": [_arg("name", required=True)]},
            {"name": "add", "description": "添加或更新项目", "args": [_arg("name", required=True), _arg("--desc"), _arg("--repo"), _arg("--metadata")]},
        ]},
        "chain": {"description": "排查 Chain 编排", "subcommands": [
            {"name": name, "description": name, "args": args}
            for name, args in (
                ("list", []), ("show", [_arg("name", required=True)]),
                ("start", [_arg("name", required=True), _arg("--project"), _arg("--problem"), _arg("--context")]),
                ("provide", [_arg("session", required=True), _arg("--inputs", required=True)]),
                ("status", [_arg("session", required=True)]), ("step", [_arg("session", required=True)]),
                ("complete", [_arg("session", required=True), _arg("--summary"), _arg("--outputs"), _arg("--evidence"), _arg("--token-usage")]),
                ("validate", [_arg("session", required=True), _arg("--step", type="int", required=True)]),
                ("amend", [_arg("session", required=True), _arg("--step", type="int", required=True), _arg("--summary"), _arg("--outputs"), _arg("--evidence")]),
                ("context", [_arg("session", required=True)]), ("report", [_arg("session", required=True), _arg("--slug", required=True)]),
                ("usage", [_arg("session", required=True)]), ("sessions", [_arg("--limit", type="int", default=20)]),
            )
        ]},
        "config": {"description": "核心配置管理", "subcommands": [
            {"name": "show", "description": "查看核心配置", "args": []},
            {"name": "get", "description": "读取配置", "args": [_arg("key", required=True)]},
            {"name": "set", "description": "写入配置", "args": [_arg("key", required=True), _arg("value", required=True)]},
            {"name": "unset", "description": "删除配置", "args": [_arg("key", required=True)]},
            {"name": "path", "description": "查看路径", "args": []},
        ]},
        "errors": {"description": "错误日志", "subcommands": [
            {"name": "list", "description": "查看错误", "args": [_arg("--limit", type="int", default=20), _arg("--command")]},
            {"name": "clear", "description": "清理错误", "args": []},
        ]},
        "perf": {"description": "核心性能观测", "subcommands": [
            {"name": "report", "description": "聚合耗时", "args": [_arg("--time", default="24h"), _arg("--keyword"), _arg("--session")]},
            {"name": "clear", "description": "清理耗时", "args": []},
        ]},
        "harness": {"description": "Agent Harness", "subcommands": [
            {"name": "check", "description": "离线检查", "args": []},
            {"name": "evaluate", "description": "场景评测", "args": [_arg("--scenarios", required=True), _arg("--agent-command"), _arg("--timeout", type="int", default=120), _arg("--scenario")]},
        ]},
        "skill": {"description": "可选 Agent Skill 管理", "subcommands": [
            {"name": name, "description": name, "args": [_arg("--dir")]} for name in ("install", "update", "status", "uninstall")
        ]},
    }
    try:
        chains = chain_engine.list_chains()
    except chain_engine.ChainConfigError as exc:
        return error(str(exc), code="CHAIN_CONFIG_ERROR")
    registry = get_registry()
    for installed in registry.plugins():
        for command_name, command_spec in installed.command_capabilities().items():
            commands.setdefault(command_name, command_spec)
    return success({
        "name": "seek",
        "version": __version__,
        "description": "通用 AI Agent 故障排查编排 CLI",
        "output_format": "json (default) | text (--format text)",
        "commands": commands,
        "chains": chains,
        "plugins": registry.as_dicts(),
        "plugin_load_errors": registry.load_errors(),
        "data_contracts": {
            "evidence": chain_engine.EVIDENCE_SCHEMA,
            "token_usage": {**chain_engine.TOKEN_USAGE_SCHEMA, "used_for_scoring": False},
        },
        "config": {
            "seek_home": "SEEK_HOME 环境变量可覆盖，默认 ~/.seek",
            "settings": "${SEEK_HOME:-~/.seek}/config/seek.json",
            "projects": "${SEEK_HOME:-~/.seek}/config/projects.json",
            "sessions": "${SEEK_HOME:-~/.seek}/sessions/",
            "plugins": "entry point group: seek.plugins",
        },
    }, message="seek CLI 能力清单")
