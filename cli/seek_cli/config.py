"""配置管理 — 加载和管理项目配置（SLS 地址、仓库路径、A1 应用名等）

配置文件优先级（从高到低）：
1. ~/.seek/config/projects.json  （用户级，可覆盖）
2. 包内 config/projects.json          （包级，种子配置）
"""

import json
import os
import sys
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from seek_cli.paths import seek_path
from seek_cli.utils import atomic_write_json, file_lock

# 包根目录（cli/ 目录）
_PKG_ROOT = Path(__file__).parent
_BUILTIN_CONFIG = _PKG_ROOT / "resources" / "config" / "projects.json"
_USER_CONFIG = seek_path("config", "projects.json")


class ProjectConfigError(Exception):
    """项目配置文件损坏或结构非法。"""


def _read_projects_file(path: Path, source: str) -> dict:
    """读取并校验项目配置文件，保留来源信息供错误提示。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise ProjectConfigError(
            f"{source} project config invalid at {path}: {exc}; "
            "fix the JSON or move the file aside to recover"
        ) from exc
    projects = data.get("projects", {}) if isinstance(data, dict) else None
    if not isinstance(projects, dict):
        raise ProjectConfigError(
            f"{source} project config at {path} must contain an object 'projects'"
        )
    for name, project in projects.items():
        if not isinstance(project, dict):
            raise ProjectConfigError(
                f"{source} project '{name}' at {path} must be an object"
            )
        environments = project.get("environments", {})
        if not isinstance(environments, dict):
            raise ProjectConfigError(
                f"{source} project '{name}' field 'environments' at {path} must be an object"
            )
        for env_name, env_config in environments.items():
            if not isinstance(env_config, dict):
                raise ProjectConfigError(
                    f"{source} project '{name}' environment '{env_name}' at {path} must be an object"
                )
            platforms = env_config.get("platforms", [])
            if not isinstance(platforms, list):
                raise ProjectConfigError(
                    f"{source} project '{name}' environment '{env_name}' field 'platforms'"
                    f" at {path} must be an array"
                )
            for index, platform in enumerate(platforms):
                if not isinstance(platform, dict):
                    raise ProjectConfigError(
                        f"{source} project '{name}' environment '{env_name}' platform[{index}]"
                        f" at {path} must be an object"
                    )
                platform_config = platform.get("config", {})
                if not isinstance(platform_config, dict):
                    raise ProjectConfigError(
                        f"{source} project '{name}' environment '{env_name}' platform[{index}]"
                        f" field 'config' at {path} must be an object"
                    )
    return data


def _merge_project(base: dict, override: dict) -> dict:
    """合并用户项目补丁；环境按名称合并，同一环境整体替换。"""
    merged = deepcopy(base)
    for key, value in override.items():
        if key == "environments" and isinstance(value, dict):
            merged.setdefault("environments", {}).update(deepcopy(value))
        else:
            merged[key] = deepcopy(value)
    return merged


def _load_config() -> dict:
    """加载合并后的配置：包级种子 + 用户级补丁覆盖。"""
    cfg = {"projects": {}}
    if _BUILTIN_CONFIG.exists():
        builtin = _read_projects_file(_BUILTIN_CONFIG, "builtin")
        cfg["projects"].update(deepcopy(builtin.get("projects", {})))
    if _USER_CONFIG.exists():
        user = _read_projects_file(_USER_CONFIG, "user")
        for name, override in user.get("projects", {}).items():
            base = cfg["projects"].get(name, {})
            if not isinstance(override, dict):
                raise ProjectConfigError(f"user project '{name}' must be an object")
            cfg["projects"][name] = _merge_project(base, override)
    return cfg


def _save_user_config(cfg: dict) -> None:
    """原子保存用户级配置，避免中断时损坏 JSON 文件。"""
    atomic_write_json(_USER_CONFIG, cfg)


@contextmanager
def _user_config_lock():
    """为用户配置读改写提供跨进程排他锁。"""
    with file_lock(_USER_CONFIG.with_suffix(".lock")):
        yield


def list_projects() -> list:
    """列出所有已配置的项目"""
    cfg = _load_config()
    projects = []
    for name, info in cfg["projects"].items():
        projects.append({
            "name": name,
            "description": info.get("description", ""),
            "repoPath": info.get("repoPath", ""),
            "a1AppName": info.get("a1AppName", ""),
            "environments": list(info.get("environments", {}).keys()),
        })
    return projects


def get_project(name: str) -> Optional[dict]:
    """获取单个项目的完整配置"""
    cfg = _load_config()
    return cfg["projects"].get(name)


def add_project(name: str, description: str = "", repo_path: str = "",
                a1_app_name: str = "", environments: dict = None) -> dict:
    """添加或更新项目配置

    Args:
        name: 项目名（如 qt-monitor-ops）
        description: 项目描述
        repo_path: 本地代码仓库路径
        a1_app_name: A1 平台应用名（用于查询部署信息）
        environments: 环境配置 dict，如:
            {
              "daily": {"sls": {"endpoint": "...", "project": "...", "logstore": "..."}},
              "prod":  {"sls": {"endpoint": "...", "project": "...", "logstore": "..."}}
            }
    """
    with _user_config_lock():
        cfg = _load_user_or_create()
        project_patch = cfg["projects"].get(name, {})
        if description:
            project_patch["description"] = description
        if repo_path:
            project_patch["repoPath"] = repo_path
        if a1_app_name:
            project_patch["a1AppName"] = a1_app_name
        if environments:
            envs = project_patch.get("environments", {})
            envs.update(environments)
            project_patch["environments"] = envs
        cfg["projects"][name] = project_patch
        _save_user_config(cfg)
        project = _merge_project(_load_config()["projects"].get(name, {}), project_patch)
    return {"name": name, "saved": True, "project": project}


def resolve_env(project, env: str) -> str:
    """解析环境别名，返回用于查配置的环境名。

    优先级：精确匹配 environments > envAliases 映射（目标须存在于 environments）
    > 原样返回。别名目标不存在时不应用，避免把请求导向空环境后误判“无日志”。

    Args:
        project: 项目名（str）或项目配置 dict
        env: 请求的环境名（可能是别名，如 daily）

    Returns:
        解析后的环境名（如 daily → yanlian）
    """
    proj = project if isinstance(project, dict) else get_project(project)
    if not proj:
        return env
    environments = proj.get("environments", {})
    if env in environments:
        return env
    aliases = proj.get("envAliases", {})
    if isinstance(aliases, dict):
        target = aliases.get(env)
        if isinstance(target, str) and target in environments:
            return target
    return env


def get_env_aliases(project) -> dict:
    """返回项目配置的 envAliases（非对象时返回空 dict），供输出展示与报错提示。"""
    proj = project if isinstance(project, dict) else get_project(project)
    if not proj:
        return {}
    aliases = proj.get("envAliases", {})
    return aliases if isinstance(aliases, dict) else {}


def get_sls_config(project: str, env: str) -> Optional[dict]:
    """获取指定项目在指定环境的第一个 SLS 配置（向后兼容）

    注意：一个环境可能配置多个 SLS platform（跨 region），此函数仅返回第一个。
    需要全量查询请使用 get_all_sls_configs()。

    Args:
        project: 项目名（字符串，不是项目配置 dict）
        env: 环境名（daily / pre / prod）

    Returns:
        SLS 配置 dict: {endpoint, project, logstore, ...} 或 None
    """
    configs = get_all_sls_configs(project, env)
    return configs[0]["config"] if configs else None


def get_all_sls_configs(project, env: str) -> list:
    """获取指定项目在指定环境的全部启用 SLS 配置（跨 region 支持）

    Args:
        project: 项目名（str）或项目配置 dict（来自 get_project，便于引擎内部复用）
        env: 环境名（daily / pre / prod）

    Returns:
        [{"name": 平台名, "config": {endpoint, project, logstore}}, ...]，
        按配置顺序返回；无配置时返回空列表
    """
    proj = project if isinstance(project, dict) else get_project(project)
    if not proj:
        return []
    env = resolve_env(proj, env)
    env_cfg = proj.get("environments", {}).get(env)
    if not env_cfg:
        return []
    results = []
    for plat in env_cfg.get("platforms", []):
        if plat.get("type") == "sls" and plat.get("enabled", True):
            cfg = plat.get("config", {})
            if cfg.get("endpoint") and cfg.get("project") and cfg.get("logstore"):
                results.append({"name": plat.get("name", ""), "config": cfg})
    return results


def get_environments(project: str) -> list:
    """获取项目支持的环境列表"""
    proj = get_project(project)
    if not proj:
        return []
    return list(proj.get("environments", {}).keys())


def _load_user_or_create() -> dict:
    """加载用户级配置，不存在则创建空配置。"""
    if _USER_CONFIG.exists():
        return _read_projects_file(_USER_CONFIG, "user")
    return {"projects": {}}


# 服务拓扑文件候选路径（与 _resolve_topology_file 原逻辑保持一致）
_TOPOLOGY_CANDIDATES = [
    Path.home() / ".qoderwork/plugins-custom/log-investigator/skills/QT平台知识库/references/service-topology.md",
    Path.home() / ".qoderwork/plugins/log-investigator/skills/QT平台知识库/references/service-topology.md",
    seek_path("data", "service-topology.md"),
]


def get_topology_file() -> Path:
    """解析服务拓扑文件路径

    优先级：
    1. 环境变量 SEEK_TOPOLOGY_FILE
    2. 统一配置 ~/.seek/config/seek.json 中的 trace.topologyFile
    3. 用户配置 ~/.seek/config/trace.json 中的 topologyFile（兼容）
    4. 默认候选路径列表（按顺序查找第一个存在的）

    Returns:
        Path: 拓扑文件路径（即使文件不存在也会返回第一个候选作为提示路径）

    Note:
        此函数仅解析路径，不读取文件内容；文件读取由调用方负责。
    """
    # 1. 环境变量
    env_path = os.environ.get("SEEK_TOPOLOGY_FILE")
    if env_path:
        if Path(env_path).exists():
            return Path(env_path)
        # 配置了但文件不存在：stderr 警告后回退到候选列表
        print(
            f"[seek] ⚠️ SEEK_TOPOLOGY_FILE={env_path} 不存在，回退到默认候选",
            file=sys.stderr,
        )
    # 2. 统一配置 seek.json
    from seek_cli import settings
    unified_path = settings.get_setting("trace.topologyFile")
    if unified_path:
        if Path(unified_path).exists():
            return Path(unified_path)
        print(
            f"[seek] ⚠️ seek.json#trace.topologyFile={unified_path} 不存在，回退到默认候选",
            file=sys.stderr,
        )
    # 3. 旧用户配置（兼容）
    user_cfg = seek_path("config", "trace.json")
    if user_cfg.exists():
        try:
            with open(user_cfg, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            user_path = cfg.get("topologyFile")
            if user_path:
                if Path(user_path).exists():
                    return Path(user_path)
                # 配置了但文件不存在：stderr 警告
                print(
                    f"[seek] ⚠️ ~/.seek/config/trace.json#topologyFile={user_path} 不存在，回退到默认候选",
                    file=sys.stderr,
                )
        except (json.JSONDecodeError, OSError):
            pass
    # 4. 默认候选路径
    for c in _TOPOLOGY_CANDIDATES:
        if c.exists():
            return c
    # 全部不存在时返回第一个作为"提示路径"
    return _TOPOLOGY_CANDIDATES[0]
