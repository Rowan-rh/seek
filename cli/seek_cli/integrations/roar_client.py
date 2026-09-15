"""roar 通知中心客户端 — 通知触达查询 (noti-query)

调用 roar.alibaba-inc.com 的 /noticenter/noti-query.action 接口，
按下游任务 queryId（如 ali-ivr-xxx）查询通知投递状态。

⚠️ 该接口仅能查询近 7 天的数据，超期查询会返回空/无记录。
⚠️ 默认走 HTTP 明文（阿里内网域名），首次调用会打印一次性安全警告；
   设 SEEK_QUIET_WARNINGS=1 可抑制。host 可通过环境变量 ROAR_HOST
   或 ~/.seek/config/roar.json 覆盖。
"""

import json
import os
import requests
import sys

from seek_cli.paths import seek_path

_CONFIG_FILE = seek_path("config", "roar.json")
DEFAULT_HOST = "http://roar.alibaba-inc.com"
_warned_http = False  # 模块级：每个进程只警告一次明文传输


def get_host() -> str:
    """获取 roar 服务地址"""
    env_host = os.environ.get("ROAR_HOST")
    if env_host:
        return env_host
    # 统一配置 ~/.seek/config/seek.json（seek config set hosts.roar）
    from seek_cli import settings
    unified_host = settings.get_setting("hosts.roar")
    if unified_host:
        return unified_host
    # 旧配置文件（兼容）
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if cfg.get("host"):
                    return cfg["host"]
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_HOST


# 兼容旧调用方。
_get_host = get_host


def query_delivery(query_id: str, timeout: int = 30) -> dict:
    """按 queryId 查询通知触达状态

    Args:
        query_id: 下游任务 ID（如 ali-ivr-21d7aff3-...）
        timeout: 请求超时秒数

    Returns:
        接口返回的原始 JSON dict（结构由 roar 决定，调用方容错解析）

    Raises:
        RuntimeError: HTTP 非 200 或响应非 JSON
    """
    global _warned_http
    host = get_host()
    url = f"{host}/noticenter/noti-query.action"
    from seek_cli import settings
    if (url.lower().startswith("http://") and not _warned_http
            and not settings.quiet_warnings()):
        print(
            f"[seek] ⚠️ roar noti-query 走 HTTP 明文: {host}。"
            f"可在 ~/.seek/config/roar.json 设置 \"host\": \"https://...\"",
            file=sys.stderr,
        )
        _warned_http = True

    resp = requests.get(url, params={"queryId": query_id}, timeout=timeout,
                        headers={"Accept": "*/*"})
    if resp.status_code != 200:
        raise RuntimeError(
            f"noti-query returned HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        return resp.json()
    except json.JSONDecodeError:
        raise RuntimeError(
            f"noti-query 响应非 JSON（queryId 可能无效或已超 7 天）: {resp.text[:200]}")

# 兼容别名
_DEFAULT_HOST = DEFAULT_HOST
