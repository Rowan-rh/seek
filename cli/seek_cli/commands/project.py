"""通用项目目录命令。"""

import json

from seek_cli import config
from seek_cli.output import success, error


def cmd_project_list(args) -> dict:
    try:
        projects = config.list_projects()
    except config.ProjectConfigError as exc:
        return error(str(exc), code="CONFIG_ERROR")
    return success({"projects": projects, "total": len(projects)},
                   message=f"共 {len(projects)} 个项目")


def cmd_project_show(args) -> dict:
    try:
        project = config.get_project(args.name)
    except config.ProjectConfigError as exc:
        return error(str(exc), code="CONFIG_ERROR")
    if not project:
        return error(f"project '{args.name}' not found", code="NOT_FOUND")
    return success(project, message=f"项目: {args.name}")


def cmd_project_add(args) -> dict:
    metadata = {}
    if getattr(args, "metadata", None):
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            return error("invalid JSON for --metadata", code="BAD_JSON")
        if not isinstance(metadata, dict):
            return error("--metadata must be a JSON object", code="BAD_JSON")
    try:
        result = config.add_project(
            name=args.name,
            description=getattr(args, "desc", "") or "",
            repo_path=getattr(args, "repo", "") or "",
            metadata=metadata,
        )
    except config.ProjectConfigError as exc:
        return error(str(exc), code="CONFIG_ERROR")
    return success(result, message=f"项目 '{args.name}' 配置已保存")
