"""SLS 日志查询命令"""

import sys

from seek_cli import config
from seek_cli.integrations import sls_client
from seek_cli.output import success, error

_MAX_RESULTS_LIMIT = 1000


def _resolve_query(args) -> tuple:
    """解析查询语句：--query 与 --query-file 二选一

    --query-file 支持普通文件路径和 '-'（stdin），用于规避中文/引号嵌套
    的 shell 转义问题。

    Args:
        args: argparse 命名空间（需含 query / query_file 属性）

    Returns:
        (query, error_message)；合法时 error_message 为空字符串
    """
    query = getattr(args, "query", None)
    query_file = getattr(args, "query_file", None)
    if query and query_file:
        return "", "--query and --query-file are mutually exclusive"
    if query_file:
        try:
            if query_file == "-":
                query = sys.stdin.read()
            else:
                with open(query_file, "r", encoding="utf-8") as f:
                    query = f.read()
        except OSError as e:
            return "", f"failed to read --query-file: {e}"
        query = query.strip()
        if not query:
            return "", "--query-file content is empty"
    if not query:
        return "", "--query or --query-file is required"
    return query, ""


def _validate_max_results(max_results: int) -> str:
    """校验单个 SLS 查询目标的返回条数。"""
    if max_results < 1 or max_results > _MAX_RESULTS_LIMIT:
        return f"--max must be between 1 and {_MAX_RESULTS_LIMIT}"
    return ""


def _direct_query_args(args) -> str:
    """校验裸 SLS 目标直查参数，返回空字符串表示合法。"""
    direct_values = (getattr(args, "endpoint", None), getattr(args, "sls_project", None),
                     getattr(args, "logstore", None))
    if not any(direct_values):
        return ""
    if not all(direct_values):
        return "direct mode requires --endpoint, --sls-project, and --logstore together"
    if getattr(args, "project", None) or getattr(args, "env", None):
        return "direct mode cannot be combined with project or --env"
    return ""


def _add_result_warnings(result: dict, max_results: int) -> dict:
    """标记达到单个查询目标上限而可能不完整的结果。"""
    result.setdefault("warnings", [])
    truncated_sources = result.get("truncatedLogstores", [])
    if "byLogstore" in result:
        result["truncated"] = bool(truncated_sources)
    else:
        result["truncated"] = result.get("count", 0) >= max_results
    if result["truncated"]:
        result["warnings"].append(
            "one or more query targets may be incomplete; consider narrowing time window or raising --max"
        )
    return result


def _sort_result(result: dict, sort_order: str) -> dict:
    """按常见 SLS 时间字段排序；字段缺失时显式提示。"""
    if not sort_order or not result.get("logs"):
        return result
    time_fields = ("__time__", "time", "timestamp", "@timestamp")
    if not all(any(field in log for field in time_fields) for log in result["logs"]):
        result.setdefault("warnings", []).append(
            "sort unavailable: logs do not expose a common time field"
        )
        return result

    def _time_value(log):
        for field in time_fields:
            if field in log:
                return str(log[field])
        return ""

    result["logs"].sort(key=_time_value, reverse=(sort_order == "desc"))
    result["sort"] = sort_order
    return result


def cmd_sls_query(args) -> dict:
    """执行项目配置或裸 SLS 目标查询。"""
    max_error = _validate_max_results(args.max)
    if max_error:
        return error(max_error, code="BAD_ARGUMENT")
    direct_error = _direct_query_args(args)
    if direct_error:
        return error(direct_error, code="BAD_ARGUMENT")
    query, query_error = _resolve_query(args)
    if query_error:
        return error(query_error, code="BAD_ARGUMENT")

    try:
        if getattr(args, "endpoint", None):
            result = sls_client.query_logs(
                endpoint=args.endpoint,
                project=args.sls_project,
                logstore=args.logstore,
                query=query,
                time_range=args.time,
                max_results=args.max,
            )
            result["mode"] = "direct"
        else:
            if not args.project or not args.env:
                return error("project and --env are required unless direct mode is used",
                             code="BAD_ARGUMENT")
            proj = config.get_project(args.project)
            if not proj:
                return error(f"project '{args.project}' not found", code="NOT_FOUND")
            resolved_env = config.resolve_env(proj, args.env)
            result = sls_client.query_by_config(
                project_config=proj,
                env=args.env,
                query=query,
                time_range=args.time,
                max_results=args.max,
            )
            result["mode"] = "configured"
            if resolved_env != args.env:
                result["resolvedEnv"] = resolved_env
                result.setdefault("warnings", []).append(
                    f"env '{args.env}' resolved to '{resolved_env}' via envAliases")
        result = _sort_result(result, getattr(args, "sort", None))
        result = _add_result_warnings(result, args.max)
        message = f"SLS 查询完成: {result['count']} 条结果"
        if result.get("resolvedEnv"):
            message += f"（环境别名 {args.env} → {result['resolvedEnv']}）"
        return success(result, message=message)
    except (RuntimeError, ValueError) as e:
        return error(str(e), code="SLS_QUERY_ERROR",
                     data={"project": getattr(args, "project", None), "env": getattr(args, "env", None),
                           "query": query})


def cmd_sls_logs(args) -> dict:
    """快捷日志查询（自动构造关键词查询）"""
    max_error = _validate_max_results(args.max)
    if max_error:
        return error(max_error, code="BAD_ARGUMENT")
    proj = config.get_project(args.project)
    if not proj:
        return error(f"project '{args.project}' not found", code="NOT_FOUND")

    # 构造查询语句
    parts = []
    if args.level:
        parts.append(f'level: {args.level}')
    if args.keyword:
        parts.append(args.keyword)
    if args.trace_id:
        parts.append(f'"{args.trace_id}"')

    query = " AND ".join(parts) if parts else "*"

    resolved_env = config.resolve_env(proj, args.env)
    try:
        result = sls_client.query_by_config(
            project_config=proj,
            env=args.env,
            query=query,
            time_range=args.time,
            max_results=args.max,
        )
        if resolved_env != args.env:
            result["resolvedEnv"] = resolved_env
            result.setdefault("warnings", []).append(
                f"env '{args.env}' resolved to '{resolved_env}' via envAliases")
        result = _add_result_warnings(result, args.max)
        message = f"日志查询完成: {result['count']} 条"
        if result.get("resolvedEnv"):
            message += f"（环境别名 {args.env} → {result['resolvedEnv']}）"
        return success(result, message=message)
    except (RuntimeError, ValueError) as e:
        return error(str(e), code="SLS_QUERY_ERROR")


def cmd_sls_config(args) -> dict:
    """查看项目的 SLS 配置（列出每个环境的全部 logstore，含跨 region 条目）"""
    proj = config.get_project(args.project)
    if not proj:
        return error(f"project '{args.project}' not found", code="NOT_FOUND")

    env = getattr(args, "env", None)
    if env:
        resolved_env = config.resolve_env(proj, env)
        all_cfgs = config.get_all_sls_configs(args.project, env)
        if not all_cfgs:
            return error(f"no SLS config for env '{env}'", code="NOT_FOUND",
                         data={"available_envs": config.get_environments(args.project),
                               "env_aliases": config.get_env_aliases(proj)})
        payload = {
            "project": args.project,
            "env": env,
            "sls_configs": all_cfgs,
        }
        if resolved_env != env:
            payload["resolvedEnv"] = resolved_env
        return success(
            payload,
            message=f"SLS 配置: {args.project}/{env}"
            + (f"（环境别名 {env} → {resolved_env}）" if resolved_env != env else ""))
    else:
        # 列出所有环境的全部 SLS 配置
        envs = config.get_environments(args.project)
        configs = {}
        for e in envs:
            all_cfgs = config.get_all_sls_configs(args.project, e)
            if all_cfgs:
                configs[e] = all_cfgs
        return success({
            "project": args.project,
            "environments": configs,
            "env_aliases": config.get_env_aliases(proj),
        })
