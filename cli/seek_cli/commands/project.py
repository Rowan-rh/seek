"""项目配置管理命令"""

from seek_cli import config
from seek_cli.output import success, error


def cmd_project_list(args) -> dict:
    """列出所有已配置的项目"""
    try:
        projects = config.list_projects()
    except config.ProjectConfigError as exc:
        return error(str(exc), code="CONFIG_ERROR")
    return success({
        "projects": projects,
        "total": len(projects),
    }, message=f"共 {len(projects)} 个项目")


def cmd_project_show(args) -> dict:
    """查看项目详情"""
    try:
        proj = config.get_project(args.name)
    except config.ProjectConfigError as exc:
        return error(str(exc), code="CONFIG_ERROR")
    if not proj:
        return error(f"project '{args.name}' not found", code="NOT_FOUND")
    return success(proj, message=f"项目: {args.name}")


def cmd_project_add(args) -> dict:
    """添加或更新项目配置"""
    # 构建 environments
    environments = {}
    try:
        if args.sls_daily:
            environments["daily"] = _build_env_config(args.sls_daily)
        if args.sls_pre:
            environments["pre"] = _build_env_config(args.sls_pre)
        if args.sls_prod:
            environments["prod"] = _build_env_config(args.sls_prod)
    except ValueError as exc:
        # --sls-xxx 格式非法属于用户输入错误，不落入 main() 兜底 INTERNAL_ERROR
        return error(str(exc), code="BAD_ARGUMENT")

    try:
        result = config.add_project(
            name=args.name,
            description=args.desc or "",
            repo_path=args.repo or "",
            a1_app_name=args.a1_app or "",
            environments=environments if environments else None,
        )
    except config.ProjectConfigError as exc:
        return error(str(exc), code="CONFIG_ERROR")
    return success(result, message=f"项目 '{args.name}' 配置已保存")


def _build_env_config(sls_str: str) -> dict:
    """解析 --sls-xxx 参数为环境配置

    格式: endpoint/project/logstore
    如: cn-hangzhou.log.aliyuncs.com/qt-monitor-ops-cn-hangzhou/qt_monitor_ops_log_daily
    """
    parts = sls_str.split("/")
    if len(parts) < 3:
        raise ValueError(
            f"invalid SLS config '{sls_str}'; expected format: endpoint/project/logstore"
        )
    return {
        "platforms": [{
            "type": "sls",
            "name": f"SLS-{parts[1]}",
            "enabled": True,
            "config": {
                "endpoint": parts[0],
                "project": parts[1],
                "logstore": parts[2],
            },
        }],
        "queryDefaults": {
            "timeRange": "15m",
            "maxResults": 100,
            "sortOrder": "desc",
        },
    }
