"""通用项目配置。

项目只保存名称、描述、仓库路径和可供插件消费的元数据；核心不认识任何
云厂商、日志平台或内部系统字段。
"""

import json
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from seek_cli.paths import seek_path
from seek_cli.utils import atomic_write_json, file_lock


_PKG_ROOT = Path(__file__).parent
_BUILTIN_CONFIG = _PKG_ROOT / "resources" / "config" / "projects.json"
_USER_CONFIG = seek_path("config", "projects.json")
_PROJECT_FIELDS = {"description", "repoPath", "metadata"}


class ProjectConfigError(Exception):
    """项目配置文件损坏或结构非法。"""


def _read_projects_file(path: Path, source: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise ProjectConfigError(f"{source} project config invalid at {path}: {exc}") from exc
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, dict):
        raise ProjectConfigError(f"{source} project config at {path} must contain an object 'projects'")
    for name, project in projects.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(project, dict):
            raise ProjectConfigError(f"{source} project '{name}' at {path} must be a non-empty object")
        if "repoPath" in project and not isinstance(project["repoPath"], str):
            raise ProjectConfigError(f"{source} project '{name}' field 'repoPath' must be a string")
        if "metadata" in project and not isinstance(project["metadata"], dict):
            raise ProjectConfigError(f"{source} project '{name}' field 'metadata' must be an object")
    return data


def _merge_project(base: dict, override: dict) -> dict:
    merged = deepcopy(base)
    for key, value in override.items():
        if key not in _PROJECT_FIELDS:
            continue
        if key == "metadata" and isinstance(value, dict):
            merged.setdefault("metadata", {}).update(deepcopy(value))
        else:
            merged[key] = deepcopy(value)
    return merged


def _load_config() -> dict:
    cfg = {"projects": {}}
    if _BUILTIN_CONFIG.exists():
        builtin = _read_projects_file(_BUILTIN_CONFIG, "builtin")
        cfg["projects"].update(deepcopy(builtin["projects"]))
    if _USER_CONFIG.exists():
        user = _read_projects_file(_USER_CONFIG, "user")
        for name, override in user["projects"].items():
            cfg["projects"][name] = _merge_project(cfg["projects"].get(name, {}), override)
    return cfg


def _load_user_or_create() -> dict:
    if _USER_CONFIG.exists():
        source = _read_projects_file(_USER_CONFIG, "user")
        return {"projects": {
            name: _merge_project({}, project)
            for name, project in source["projects"].items()
        }}
    return {"projects": {}}


def _save_user_config(cfg: dict) -> None:
    atomic_write_json(_USER_CONFIG, cfg)


@contextmanager
def _user_config_lock():
    with file_lock(_USER_CONFIG.with_suffix(".lock")):
        yield


def list_projects() -> list:
    projects = []
    for name, info in _load_config()["projects"].items():
        projects.append({
            "name": name,
            "description": info.get("description", ""),
            "repoPath": info.get("repoPath", ""),
            "metadata": deepcopy(info.get("metadata", {})),
        })
    return projects


def get_project(name: str) -> Optional[dict]:
    return _load_config()["projects"].get(name)


def add_project(name: str, description: str = "", repo_path: str = "",
                metadata: dict = None) -> dict:
    """添加或更新项目。"""
    if not isinstance(name, str) or not name.strip():
        raise ProjectConfigError("project name must be non-empty")
    with _user_config_lock():
        cfg = _load_user_or_create()
        project = cfg["projects"].get(name, {})
        if description:
            project["description"] = description
        if repo_path:
            project["repoPath"] = repo_path
        if metadata:
            project.setdefault("metadata", {}).update(deepcopy(metadata))
        cfg["projects"][name] = project
        _save_user_config(cfg)
        saved = _load_config()["projects"].get(name, {})
    return {"name": name, "saved": True, "project": saved}
