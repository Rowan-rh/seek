"""seek CLI 主入口。

核心只负责项目目录、Chain、证据、会话、报告和插件发现；具体日志、指标、
部署、工单和通知能力由外部 Provider 插件注册。
"""

import argparse
import sys
import time

from seek_cli import __version__, config, error_log, perf_log
from seek_cli.commands import capabilities, chain, config_cmd, harness, perf, plugin, project, skill, version_cmd
from seek_cli.output import error, print_result, success
from seek_cli.paths import seek_path


def _add_global_args(parser: argparse.ArgumentParser, root: bool = False) -> None:
    parser.add_argument("--format", choices=["json", "text"],
                        default="json" if root else argparse.SUPPRESS,
                        help="输出格式: json(默认,供 agent) | text(供人阅读)")


class _JsonArgumentParser(argparse.ArgumentParser):
    """保证参数错误也输出可解析 JSON。"""

    def error(self, message):
        self.print_usage(sys.stderr)
        print_result(error(f"argument error: {message}", code="ARGPARSE_ERROR"), fmt="json")
        sys.exit(2)


def _build_parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(
        prog="seek",
        description="面向 AI agent 的证据驱动故障排查与事件响应编排 CLI",
    )
    _add_global_args(parser, root=True)
    sub = parser.add_subparsers(dest="command", required=True)

    cap = sub.add_parser("capabilities", help="输出命令、插件和数据契约")
    _add_global_args(cap)
    cap.set_defaults(func=capabilities.cmd_capabilities)

    plug = sub.add_parser("plugin", help="插件与 Provider 管理")
    plug_sub = plug.add_subparsers(dest="subcommand", required=True)
    _add_global_args(plug)
    plug_list = plug_sub.add_parser("list", help="列出已发现的插件和 Provider")
    _add_global_args(plug_list)
    plug_list.set_defaults(func=plugin.cmd_plugin_list)
    plug_show = plug_sub.add_parser("show", help="查看插件元数据和本地健康检查")
    plug_show.add_argument("name", help="插件 ID")
    _add_global_args(plug_show)
    plug_show.set_defaults(func=plugin.cmd_plugin_show)

    ver = sub.add_parser("version", help="输出版本和变更记录")
    _add_global_args(ver)
    ver.set_defaults(func=version_cmd.cmd_version)

    proj = sub.add_parser("project", help="项目目录管理")
    proj_sub = proj.add_subparsers(dest="subcommand", required=True)
    _add_global_args(proj)
    proj_list = proj_sub.add_parser("list", help="列出项目")
    _add_global_args(proj_list)
    proj_list.set_defaults(func=project.cmd_project_list)
    proj_show = proj_sub.add_parser("show", help="查看项目")
    proj_show.add_argument("name")
    _add_global_args(proj_show)
    proj_show.set_defaults(func=project.cmd_project_show)
    proj_add = proj_sub.add_parser("add", help="添加或更新项目")
    proj_add.add_argument("name")
    proj_add.add_argument("--desc", help="项目描述")
    proj_add.add_argument("--repo", help="本地仓库路径")
    proj_add.add_argument("--metadata", help="供 Provider 使用的 JSON 对象")
    _add_global_args(proj_add)
    proj_add.set_defaults(func=project.cmd_project_add)

    ch = sub.add_parser("chain", help="排查 Chain 编排")
    ch_sub = ch.add_subparsers(dest="subcommand", required=True)
    _add_global_args(ch)
    c_list = ch_sub.add_parser("list", help="列出 Chain")
    _add_global_args(c_list)
    c_list.set_defaults(func=chain.cmd_chain_list)
    c_show = ch_sub.add_parser("show", help="查看 Chain")
    c_show.add_argument("name")
    _add_global_args(c_show)
    c_show.set_defaults(func=chain.cmd_chain_show)
    c_start = ch_sub.add_parser("start", help="开始排查会话")
    c_start.add_argument("name")
    c_start.add_argument("--project")
    c_start.add_argument("--problem")
    c_start.add_argument("--context")
    _add_global_args(c_start)
    c_start.set_defaults(func=chain.cmd_chain_start)
    c_provide = ch_sub.add_parser("provide", help="补充会话输入")
    c_provide.add_argument("session")
    c_provide.add_argument("--inputs", required=True)
    _add_global_args(c_provide)
    c_provide.set_defaults(func=chain.cmd_chain_provide)
    c_status = ch_sub.add_parser("status", help="查看会话状态")
    c_status.add_argument("session")
    _add_global_args(c_status)
    c_status.set_defaults(func=chain.cmd_chain_status)
    c_step = ch_sub.add_parser("step", help="查看当前步骤")
    c_step.add_argument("session")
    _add_global_args(c_step)
    c_step.set_defaults(func=chain.cmd_chain_step)
    c_complete = ch_sub.add_parser("complete", help="完成当前步骤")
    c_complete.add_argument("session")
    c_complete.add_argument("--summary")
    c_complete.add_argument("--outputs")
    c_complete.add_argument("--evidence")
    c_complete.add_argument("--token-usage")
    _add_global_args(c_complete)
    c_complete.set_defaults(func=chain.cmd_chain_complete)
    c_validate = ch_sub.add_parser("validate", help="验证步骤约束")
    c_validate.add_argument("session")
    c_validate.add_argument("--step", type=int, required=True)
    _add_global_args(c_validate)
    c_validate.set_defaults(func=chain.cmd_chain_validate)
    c_amend = ch_sub.add_parser("amend", help="更正已完成步骤")
    c_amend.add_argument("session")
    c_amend.add_argument("--step", type=int, required=True)
    c_amend.add_argument("--summary")
    c_amend.add_argument("--outputs")
    c_amend.add_argument("--evidence")
    _add_global_args(c_amend)
    c_amend.set_defaults(func=chain.cmd_chain_amend)
    c_context = ch_sub.add_parser("context", help="获取会话上下文")
    c_context.add_argument("session")
    _add_global_args(c_context)
    c_context.set_defaults(func=chain.cmd_chain_context)
    c_report = ch_sub.add_parser("report", help="生成报告信息")
    c_report.add_argument("session")
    c_report.add_argument("--slug", required=True)
    _add_global_args(c_report)
    c_report.set_defaults(func=chain.cmd_chain_report)
    c_usage = ch_sub.add_parser("usage", help="汇总 token 使用量")
    c_usage.add_argument("session")
    _add_global_args(c_usage)
    c_usage.set_defaults(func=chain.cmd_chain_usage)
    c_sessions = ch_sub.add_parser("sessions", help="列出会话")
    c_sessions.add_argument("--limit", type=int, default=20)
    _add_global_args(c_sessions)
    c_sessions.set_defaults(func=chain.cmd_chain_sessions)

    cfg = sub.add_parser("config", help="核心配置管理")
    cfg_sub = cfg.add_subparsers(dest="subcommand", required=True)
    _add_global_args(cfg)
    cfg_show = cfg_sub.add_parser("show", help="查看核心配置")
    _add_global_args(cfg_show)
    cfg_show.set_defaults(func=config_cmd.cmd_config_show)
    cfg_get = cfg_sub.add_parser("get", help="读取配置")
    cfg_get.add_argument("key")
    _add_global_args(cfg_get)
    cfg_get.set_defaults(func=config_cmd.cmd_config_get)
    cfg_set = cfg_sub.add_parser("set", help="写入配置")
    cfg_set.add_argument("key")
    cfg_set.add_argument("value")
    _add_global_args(cfg_set)
    cfg_set.set_defaults(func=config_cmd.cmd_config_set)
    cfg_unset = cfg_sub.add_parser("unset", help="删除配置")
    cfg_unset.add_argument("key")
    _add_global_args(cfg_unset)
    cfg_unset.set_defaults(func=config_cmd.cmd_config_unset)
    cfg_path = cfg_sub.add_parser("path", help="查看状态路径")
    _add_global_args(cfg_path)
    cfg_path.set_defaults(func=config_cmd.cmd_config_path)

    errors = sub.add_parser("errors", help="查看/清理错误日志")
    errors_sub = errors.add_subparsers(dest="subcommand", required=True)
    _add_global_args(errors)
    errors_list = errors_sub.add_parser("list", help="查看错误")
    errors_list.add_argument("--limit", type=int, default=20)
    errors_list.add_argument("--command")
    _add_global_args(errors_list)
    errors_list.set_defaults(func=lambda args: success({"errors": error_log.read_errors(limit=args.limit, command=args.command)}, message="错误日志"))
    errors_clear = errors_sub.add_parser("clear", help="清理错误")
    _add_global_args(errors_clear)
    errors_clear.set_defaults(func=lambda args: success({"cleared": error_log.clear_errors()}, message="错误日志已清理"))

    perf_cmd = sub.add_parser("perf", help="核心性能观测")
    perf_sub = perf_cmd.add_subparsers(dest="subcommand", required=True)
    _add_global_args(perf_cmd)
    perf_report = perf_sub.add_parser("report", help="聚合耗时日志")
    perf_report.add_argument("--time", default="24h")
    perf_report.add_argument("--keyword")
    perf_report.add_argument("--session")
    _add_global_args(perf_report)
    perf_report.set_defaults(func=perf.cmd_perf_report)
    perf_clear = perf_sub.add_parser("clear", help="清理耗时日志")
    _add_global_args(perf_clear)
    perf_clear.set_defaults(func=perf.cmd_perf_clear)

    harness_cmd = sub.add_parser("harness", help="Agent Harness 检查与评测")
    harness_sub = harness_cmd.add_subparsers(dest="subcommand", required=True)
    _add_global_args(harness_cmd)
    harness_check = harness_sub.add_parser("check", help="离线就绪检查")
    _add_global_args(harness_check)
    harness_check.set_defaults(func=harness.cmd_harness_check)
    harness_eval = harness_sub.add_parser("evaluate", help="运行 Agent 场景评测")
    harness_eval.add_argument("--scenarios", required=True)
    harness_eval.add_argument("--agent-command")
    harness_eval.add_argument("--timeout", type=int, default=120)
    harness_eval.add_argument("--scenario", action="append", dest="scenario_ids")
    _add_global_args(harness_eval)
    harness_eval.set_defaults(func=harness.cmd_harness_evaluate)

    sk = sub.add_parser("skill", help="可选 Agent Skill 管理")
    sk_sub = sk.add_subparsers(dest="subcommand", required=True)
    _add_global_args(sk)
    for name, func, help_text in (
        ("install", skill.cmd_skill_install, "安装 Skill"),
        ("update", skill.cmd_skill_update, "更新 Skill"),
        ("status", skill.cmd_skill_status, "查看 Skill 状态"),
        ("uninstall", skill.cmd_skill_uninstall, "卸载 Skill"),
    ):
        item = sk_sub.add_parser(name, help=help_text)
        item.add_argument("--dir")
        _add_global_args(item)
        item.set_defaults(func=func)

    from seek_cli.plugins import get_registry
    get_registry().register_cli(sub)
    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()
    fmt = getattr(args, "format", "json")
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        sys.exit(1)
    _check_version_change()
    cmd_name = args.command
    if getattr(args, "subcommand", None):
        cmd_name = f"{args.command} {args.subcommand}"
    perf_start = time.perf_counter()
    perf_status = "error"
    try:
        try:
            result = func(args)
            perf_status = "success" if not (isinstance(result, dict) and result.get("status") == "error") else "error"
        finally:
            perf_log.log_perf(cmd_name, "command", (time.perf_counter() - perf_start) * 1000, perf_status)
        print_result(result, fmt=fmt)
        if isinstance(result, dict) and result.get("status") == "error":
            err = result.get("error", {})
            error_log.log_error(cmd_name, err.get("code", "UNKNOWN"), err.get("message", ""), result.get("data"))
            sys.exit(1)
    except SystemExit:
        raise
    except config.ProjectConfigError as exc:
        result = error(str(exc), code="CONFIG_ERROR")
        print_result(result, fmt=fmt)
        error_log.log_error(cmd_name, "CONFIG_ERROR", str(exc))
        sys.exit(1)
    except Exception as exc:
        result = error(f"unexpected error: {exc}", code="INTERNAL_ERROR")
        print_result(result, fmt=fmt)
        error_log.log_error(cmd_name, "INTERNAL_ERROR", str(exc))
        sys.exit(1)


def _check_version_change():
    version_file = seek_path("version")
    try:
        version_file.parent.mkdir(parents=True, exist_ok=True)
        last_version = version_file.read_text().strip() if version_file.exists() else None
        if last_version == __version__:
            return
        if last_version is None:
            print(f"[seek] v{__version__} — 首次安装", file=sys.stderr)
        else:
            print(f"[seek] 版本更新: {last_version} → {__version__}", file=sys.stderr)
        version_file.write_text(__version__, encoding="utf-8")
    except OSError as exc:
        print(f"[seek] 版本标记不可写(忽略): {version_file}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
