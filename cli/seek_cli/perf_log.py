"""性能日志 — 记录 CLI 命令与集成 IO 的耗时，供排查会话慢点归因

日志文件: ~/.seek/logs/perf.jsonl (每行一个 JSON)
每条记录: {timestamp, command, span, status, duration_ms, session_id?, detail}
- span: command(命令级) | sls_query | a1_subprocess | dms_call(集成 IO 级)
- session_id: 环境变量 SEEK_SESSION_ID 存在时附带，用于把命令耗时归属到 chain 会话步骤

开关: seek config set options.perf_log false 可关闭（未设置默认开启）。
写盘失败静默吞掉，绝不影响命令执行；stdout 契约零变化。
"""

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime

from seek_cli.paths import seek_path
from seek_cli.utils import atomic_write_text, file_lock

_LOG_DIR = seek_path("logs")
_LOG_FILE = _LOG_DIR / "perf.jsonl"

# 敏感键打码、长文本截断（与 error_log 约定一致）
_SENSITIVE_KEYS = {"ACCESS_KEY_ID", "ACCESS_KEY_SECRET", "PASSWORD", "TOKEN"}
_TRUNCATE_KEYS = {"query", "cmd", "sql"}
_TRUNCATE_LIMIT = 200


def enabled() -> bool:
    """perf 日志开关：统一配置 options.perf_log（未设置默认开启）"""
    try:
        from seek_cli import settings
        value = settings.get_setting("options.perf_log")
        return True if value is None else settings.as_bool(value)
    except Exception:
        return True


@contextmanager
def _log_lock():
    """Serialize perf log appends across CLI processes."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    with file_lock(_LOG_FILE.with_suffix(".lock")):
        yield


def _sanitize_detail(detail: dict) -> dict:
    """detail 脱敏：敏感键打码，query/cmd/sql 截断到 200 字符"""
    safe = {}
    for k, v in (detail or {}).items():
        if k.upper() in _SENSITIVE_KEYS:
            safe[k] = "***"
        elif k in _TRUNCATE_KEYS and isinstance(v, str) and len(v) > _TRUNCATE_LIMIT:
            safe[k] = v[:_TRUNCATE_LIMIT]
        else:
            safe[k] = v
    return safe


def log_perf(command: str, span: str, duration_ms, status: str = "success",
             detail: dict = None) -> None:
    """记录一条耗时日志；任何失败静默吞掉，绝不影响命令执行。

    Args:
        command: 命令名（如 "sls query"）或集成动作描述（如 "sls p/l"）
        span: 层级标识 command | sls_query | a1_subprocess | dms_call
        duration_ms: 耗时毫秒（time.perf_counter 单调钟差值）
        status: success | error
        detail: 可选明细（自动脱敏与截断）
    """
    try:
        if not enabled():
            return
        entry = {
            "timestamp": datetime.now().isoformat(),
            "command": command,
            "span": span,
            "status": status,
            "duration_ms": int(duration_ms),
        }
        session_id = os.environ.get("SEEK_SESSION_ID")
        if session_id:
            entry["session_id"] = session_id
        if detail:
            entry["detail"] = _sanitize_detail(detail)
        with _log_lock():
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                # default=str：detail 含不可序列化值（如 datetime）时降级为字符串
                # 而不是整条记录被 except 吞掉丢失
                f.write(json.dumps(entry, ensure_ascii=False,
                                   default=str) + "\n")
    except Exception:
        pass


@contextmanager
def perf_span(command: str, span: str, detail: dict = None):
    """计时上下文：yield 一个 detail dict（可中途补充字段），退出时写一条记录。

    正常退出记 status=success；异常记 status=error 后原样上抛。
    """
    detail = dict(detail or {})
    start = time.perf_counter()
    try:
        yield detail
    except Exception:
        log_perf(command, span, (time.perf_counter() - start) * 1000,
                 "error", detail)
        raise
    else:
        log_perf(command, span, (time.perf_counter() - start) * 1000,
                 "success", detail)


def read_perf_records(time_range: str = "24h", keyword: str = "",
                      session: str = "") -> tuple:
    """读取窗口内符合条件的 perf 记录。

    Args:
        time_range: 时间窗（与 SLS --time 同语法：24h/7d、from,to、人类可读区间）
        keyword: 记录 command 字段的子串过滤（大小写不敏感，空为不过滤；
            同时作用于 command 名与 IO 动作描述）
        session: session_id 精确匹配（空为不过滤）

    Returns:
        (records, skipped)：records 按文件顺序（旧→新）；
        skipped 为损坏行（JSON 非法或 timestamp 不可解析）计数。

    Raises:
        ValueError: time_range 语法非法。
    """
    from seek_cli.plugins import get_provider
    sls_client = get_provider("alibaba").service("sls")

    from_t, to_t = sls_client.parse_time_range(time_range)
    keyword_kw = (keyword or "").strip().lower()
    session_kw = (session or "").strip()
    records = []
    skipped = 0
    if not _LOG_FILE.exists():
        return records, skipped
    with open(_LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                ts = datetime.fromisoformat(entry["timestamp"]).timestamp()
            except (json.JSONDecodeError, KeyError, ValueError, TypeError):
                skipped += 1
                continue
            if ts < from_t or ts > to_t:
                continue
            if keyword_kw and keyword_kw not in str(entry.get("command", "")).lower():
                continue
            if session_kw and entry.get("session_id") != session_kw:
                continue
            records.append(entry)
    return records, skipped


def clear_perf_log() -> int:
    """清空 perf 日志（原子替换），返回清除的记录条数；文件不存在返回 0。"""
    with _log_lock():
        if not _LOG_FILE.exists():
            return 0
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            count = sum(1 for line in f if line.strip())
        atomic_write_text(_LOG_FILE, "")
        return count
