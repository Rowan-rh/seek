"""统一配置管理 — ~/.seek/config/seek.json

把散落在各处的 seek 配置收敛到一个文件统一管理：
- sls 凭据（原 ~/.seek/credentials.json）
- 集成 host（原 expert.json / roar.json）
- trace 拓扑文件（原 trace.json）
- 全局选项（原 SEEK_QUIET_WARNINGS 环境变量）

读取优先级（各集成统一）：环境变量 > seek.json > 各自旧文件 > 默认值。
旧文件继续兼容，seek.json 中未设置的项自动回退。

写入使用文件锁 + 原子替换（与 projects.json 相同模式）。
"""

import json
import os
from contextlib import contextmanager
from typing import Optional

from seek_cli.paths import seek_path
from seek_cli.utils import atomic_write_json, file_lock

SETTINGS_FILE = seek_path("config", "seek.json")

# 允许的配置键 schema: key -> {help, secret}
# secret=True 的值在 show 输出中脱敏
KEY_SCHEMA = {
    "sls.access_key_id": {"help": "SLS AccessKey ID", "secret": True},
    "sls.access_key_secret": {"help": "SLS AccessKey Secret", "secret": True},
    "sls.security_token": {"help": "SLS STS Token(可选)", "secret": True},
    "hosts.expert": {"help": "qt-expert 服务地址(默认 http://pre-qt-expert.aliyun-inc.com)", "secret": False},
    "hosts.roar": {"help": "roar 服务地址(默认 http://roar.alibaba-inc.com)", "secret": False},
    "trace.topologyFile": {"help": "服务拓扑文件路径", "secret": False},
    "options.quiet_warnings": {"help": "抑制 HTTP 明文等安全警告(true/false)", "secret": False},
    "options.perf_log": {"help": "记录命令与集成耗时到 ~/.seek/logs/perf.jsonl(true/false, 默认true)", "secret": False},
}


def load_settings() -> dict:
    """加载统一配置文件，不存在或损坏时返回空 dict"""
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def get_setting(dotted_key: str):
    """按点路径读取配置值，如 get_setting('hosts.roar')；未设置返回 None"""
    node = load_settings()
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if node != "" else None


def set_setting(dotted_key: str, value) -> dict:
    """按点路径写入配置（锁 + 原子替换），返回写入后的完整配置"""
    if dotted_key not in KEY_SCHEMA:
        raise KeyError(
            f"未知配置键: {dotted_key}。可用键: {', '.join(KEY_SCHEMA)}")

    # 布尔型归一化（读写共用同一规则，避免手编 "false" 被 bool() 判真）。
    # 约定：options.* 命名空间仅放布尔开关；未来出现非布尔选项时需改为带类型的
    # KEY_SCHEMA 声明，而不是再扩大这里的前缀匹配。
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
    """删除配置键，返回是否实际删除"""
    with _settings_lock():
        cfg = load_settings()
        node = cfg
        parts = dotted_key.split(".")
        for part in parts[:-1]:
            if not isinstance(node.get(part), dict):
                return False
            node = node[part]
        if parts[-1] in node:
            del node[parts[-1]]
            _save_settings(cfg)
            return True
        return False


def mask_secret(value, keep: int = 4) -> str:
    """脱敏展示：保留前 keep 位，其余打码"""
    if value is None or value == "":
        return ""
    s = str(value)
    if len(s) <= keep:
        return "***"
    return s[:keep] + "*" * min(len(s) - keep, 8)


def as_bool(v) -> bool:
    """布尔归一化：字符串按字面解析（"false"/"0"/"no" 为 False），避免 bool("false")==True"""
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def quiet_warnings() -> bool:
    """是否抑制安全警告：环境变量 SEEK_QUIET_WARNINGS=1 或 seek.json options.quiet_warnings"""
    if os.environ.get("SEEK_QUIET_WARNINGS") == "1":
        return True
    return as_bool(get_setting("options.quiet_warnings"))


def _save_settings(cfg: dict) -> None:
    """原子保存 seek.json"""
    atomic_write_json(SETTINGS_FILE, cfg)


@contextmanager
def _settings_lock():
    """为 seek.json 读改写提供跨进程排他锁"""
    with file_lock(SETTINGS_FILE.with_suffix(".lock")):
        yield
