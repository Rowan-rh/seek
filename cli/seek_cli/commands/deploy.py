"""部署信息查询命令 — 通过 A1 CLI 查询部署分支、变更记录等"""

from seek_cli import config
from seek_cli.integrations import a1_client
from seek_cli.output import success, error


_UNCONFIGURED_PROJECT_HINT = (
    "应用未接入 seek。可先用 `a1 app list --keyword <应用名>` 查询候选，"
    "或用本地 git HEAD 作为部署版本参考；后者不是线上版本，必须标注时效性。"
)


def _project_not_found(project: str) -> dict:
    """返回项目未配置时的标准排查 fallback。"""
    return error(f"project '{project}' not found", code="NOT_FOUND",
                 data={"project": project, "fallback_hint": _UNCONFIGURED_PROJECT_HINT})


def cmd_deploy_branch(args) -> dict:
    """查询项目当前部署的分支信息"""
    proj = config.get_project(args.project)
    if not proj:
        return _project_not_found(args.project)

    a1_app = proj.get("a1AppName", "") or args.project
    try:
        result = a1_client.query_deployed_branch(a1_app)
        return success(result, message=f"部署信息: {a1_app}")
    except RuntimeError as e:
        return error(str(e), code="A1_CLI_ERROR", data={"app": a1_app})


def cmd_deploy_info(args) -> dict:
    """查询 Aone 应用详情（完整信息）"""
    proj = config.get_project(args.project)
    if not proj:
        return _project_not_found(args.project)

    a1_app = proj.get("a1AppName", "") or args.project
    try:
        info = a1_client.get_app_info(a1_app)
        return success({
            "project": args.project,
            "a1_app": a1_app,
            "app_info": info,
        }, message=f"应用详情: {a1_app}")
    except RuntimeError as e:
        return error(str(e), code="A1_CLI_ERROR")


def cmd_deploy_orders(args) -> dict:
    """查询部署单列表"""
    proj = config.get_project(args.project)
    if not proj:
        return _project_not_found(args.project)

    a1_app = proj.get("a1AppName", "") or args.project
    try:
        orders = a1_client.list_deploy_orders(a1_app)
        return success(orders, message=f"部署单列表: {a1_app}")
    except RuntimeError as e:
        return error(str(e), code="A1_CLI_ERROR")


def cmd_deploy_order(args) -> dict:
    """查询单个部署单详情"""
    try:
        order = a1_client.get_deploy_order(args.order_id)
        return success(order, message=f"部署单: {args.order_id}")
    except RuntimeError as e:
        return error(str(e), code="A1_CLI_ERROR")


def cmd_deploy_changes(args) -> dict:
    """查询应用的变更单列表"""
    proj = config.get_project(args.project)
    if not proj:
        return _project_not_found(args.project)

    a1_app = proj.get("a1AppName", "") or args.project
    try:
        crs = a1_client.list_change_requests(a1_app)
        return success(crs, message=f"变更单列表: {a1_app}")
    except RuntimeError as e:
        return error(str(e), code="A1_CLI_ERROR")


def cmd_deploy_env(args) -> dict:
    """查询指定环境的部署信息（pipeline + 发布分支 + 变更列表）

    自动完成: pipeline 列表 → 环境匹配 → 分支查询
    """
    proj = config.get_project(args.project)
    if not proj:
        return _project_not_found(args.project)

    a1_app = proj.get("a1AppName", "") or args.project
    env_kw = args.env

    try:
        result = a1_client.query_env_deploy(a1_app, env_keyword=env_kw)
        deployments = result.get("deployments", [])
        msg = f"环境[{env_kw}]部署信息: {a1_app}, 匹配 {result['matched_count']} 个 pipeline"
        if deployments:
            cr_count = sum(len(d.get("changeRequests", [])) for d in deployments)
            msg += f", 共 {cr_count} 个变更单"
        return success(result, message=msg)
    except RuntimeError as e:
        return error(str(e), code="A1_CLI_ERROR", data={"app": a1_app, "env": env_kw})
