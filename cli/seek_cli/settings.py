"""seek 核心运行配置。

核心只维护与 Provider 无关的选项。Provider 的认证和连接配置由各自插件
管理，避免核心包携带任何厂商环境假设。
"""

import os
from contextlib import contextmanager

from seek_cli.paths import seek_path
from seek_cli.utils import atomic_write_json, file_lock


SETTINGS_FILE = seek_path("config", "seek.json")
KEY_SCHEMA = {
    "options.quiet_warnings": {"help": "抑制非致命安全警告(true/false)", "secret": False},
    "options.perf_log": {"help": "记录命令耗时到 ~/.seek/logs/perf.jsonl(true/false，默认 true)", "secret": False},
}


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        import json
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def get_setting(dotted_key: str):
    node = load_settings()
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if node != "" else None


def set_setting(dotted_key: str, value) -> dict:
    if dotted_key not in KEY_SCHEMA:
        raise KeyError(f"未知配置键: {dotted_key}。可用键: {', '.join(KEY_SCHEMA)}")
    if dotted_key.startswith("options."):
        value = as_bool(value)
    with _settings_lock():
        cfg = load_settings()
        node = cfg
        parts = dotted_key.split(".")
        for part in parts[:-1]:
            if not isinstance(node.get(part), dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value
        _save_settings(cfg)
    return cfg


def unset_setting(dotted_key: str) -> bool:
    if dotted_key not in KEY_SCHEMA:
        raise KeyError(f"未知配置键: {dotted_key}。可用键: {', '.join(KEY_SCHEMA)}")
    with _settings_lock():
        cfg = load_settings()
        node = cfg
        parts = dotted_key.split(".")
        for part in parts[:-1]:
            if not isinstance(node.get(part), dict):
                return False
            node = node[part]
        if parts[-1] not in node:
            return False
        del node[parts[-1]]
        _save_settings(cfg)
        return True


def mask_secret(value, keep: int = 4) -> str:
    if value is None or value == "":
        return ""
    value = str(value)
    if len(value) <= keep:
        return "***"
    return value[:keep] + "*" * min(len(value) - keep, 8)


def as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def quiet_warnings() -> bool:
    if os.environ.get("SEEK_QUIET_WARNINGS") == "1":
        return True
    return as_bool(get_setting("options.quiet_warnings"))


def _save_settings(cfg: dict) -> None:
    atomic_write_json(SETTINGS_FILE, cfg)


@contextmanager
def _settings_lock():
    with file_lock(SETTINGS_FILE.with_suffix(".lock")):
        yield
