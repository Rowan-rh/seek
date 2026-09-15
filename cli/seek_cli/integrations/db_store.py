"""本地数据库连接 profile 存储 — ~/.seek/config/db.json

存储 seek db 本地直连使用的连接 profile（host/port/user/password/bind）。
- 文件权限强制 0600（含密码等凭证）
- 写入使用文件锁 + 原子替换（与 seek.json / projects.json 相同模式）
- 密码支持 "env:VAR" 前缀引用环境变量，运行时由 resolve_password 解析
"""

import json
import os
from contextlib import contextmanager
from typing import Optional

from seek_cli.paths import seek_path
from seek_cli.utils import atomic_write_json, file_lock

DB_FILE = seek_path("config", "db.json")

# profile 必填字段
_REQUIRED_FIELDS = ("type", "host", "port", "database", "user", "password")

# bind.env 命中以下规则视为生产类环境，直连默认拒绝
_PROD_ENVS = ("prod", "online")
_PROD_ENV_PREFIXES = ("publish",)


class DbStoreError(Exception):
    """profile 存储配置错误（结构非法/profile 不存在等）"""


def load_connections() -> dict:
    """加载全部连接 profile，文件不存在或损坏时分别返回空/抛错"""
    if not DB_FILE.exists():
        return {}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise DbStoreError(
            f"db.json invalid at {DB_FILE}: {exc}; fix the JSON or move the file aside"
        ) from exc
    conns = data.get("connections", {}) if isinstance(data, dict) else None
    if not isinstance(conns, dict):
        raise DbStoreError(f"db.json at {DB_FILE} must contain an object 'connections'")
    return conns


def get_connection(name: str) -> Optional[dict]:
    """按名称获取单个 profile，不存在返回 None"""
    return load_connections().get(name)


def add_connection(name: str, profile: dict) -> dict:
    """新增或覆盖一个 profile，返回保存后的 profile"""
    missing = [k for k in _REQUIRED_FIELDS if not profile.get(k)]
    if missing:
        raise DbStoreError(f"profile '{name}' 缺少必填字段: {missing}")
    port = profile["port"]
    if not isinstance(port, int) or not (1 <= port <= 65535):
        raise DbStoreError(f"profile '{name}' port 非法: {port!r}（需 1-65535 整数）")
    db_type = profile["type"]
    if db_type != "mysql":
        raise DbStoreError(f"profile '{name}' type 暂仅支持 mysql，收到: {db_type!r}")
    bind = profile.get("bind")
    if bind is not None and not isinstance(bind, dict):
        raise DbStoreError(f"profile '{name}' bind 必须为对象")

    with _db_file_lock():
        conns = load_connections()
        entry = {k: profile[k] for k in _REQUIRED_FIELDS}
        if bind:
            entry["bind"] = bind
        conns[name] = entry
        _save_connections(conns)
    return entry


def remove_connection(name: str) -> bool:
    """删除 profile，返回是否实际删除"""
    with _db_file_lock():
        conns = load_connections()
        if name not in conns:
            return False
        del conns[name]
        _save_connections(conns)
        return True


def find_by_bind(project: str, env: str) -> list:
    """按 (project, env) 反查 profile，返回 [(name, profile), ...]"""
    matches = []
    for name, profile in load_connections().items():
        bind = profile.get("bind") or {}
        if bind.get("project") == project and bind.get("env") == env:
            matches.append((name, profile))
    return matches


def resolve_password(profile: dict) -> str:
    """解析 profile 密码："env:VAR" 读环境变量（缺失报明确错误），明文原样返回"""
    raw = profile.get("password", "")
    if raw.startswith("env:"):
        var = raw[4:]
        value = os.environ.get(var)
        if not value:
            raise DbStoreError(
                f"密码环境变量 '{var}' 未设置（profile 使用 env:{var} 引用）"
            )
        return value
    return raw


def is_prod_env(profile: dict) -> bool:
    """判断 profile 绑定的环境是否为生产类（prod/online/publish*）"""
    env = (profile.get("bind") or {}).get("env", "") or ""
    env = env.strip().lower()
    if env in _PROD_ENVS:
        return True
    return any(env.startswith(p) for p in _PROD_ENV_PREFIXES)


def _save_connections(conns: dict) -> None:
    """原子保存 db.json 并强制 0600 权限"""
    atomic_write_json(DB_FILE, {"connections": conns}, chmod_0600=True)


@contextmanager
def _db_file_lock():
    """为 db.json 读改写提供跨进程排他锁"""
    with file_lock(DB_FILE.with_suffix(".lock")):
        yield
