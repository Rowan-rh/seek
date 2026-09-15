"""错误日志 — 自动记录 CLI 调用过程中的报错

日志文件: ~/.seek/logs/errors.jsonl (每行一个 JSON)
每条记录: {timestamp, command, args, error_code, error_message, context}
"""

import json
import sys
from collections import deque
from contextlib import contextmanager
from datetime import datetime

from seek_cli.paths import seek_path
from seek_cli.utils import atomic_write_text, file_lock

_LOG_DIR = seek_path("logs")
_LOG_FILE = _LOG_DIR / "errors.jsonl"

# 敏感键统一打码规则（args 与 context 共用）
_SENSITIVE_KEYS = {
    "ACCESS_KEY_ID", "ACCESS_KEY_SECRET", "PASSWORD", "TOKEN",
    "SECURITY_TOKEN", "SECRET", "API_KEY", "AUTHORIZATION",
}
_CONTEXT_VALUE_LIMIT = 2000
_CONTEXT_MAX_DEPTH = 8
_CONTEXT_MAX_NODES = 1000
_CONTEXT_MAX_BYTES = 64 * 1024
_CONTEXT_TRUNCATED = "[truncated]"


def _is_sensitive_key(key) -> bool:
    normalized = "".join(ch for ch in str(key).upper() if ch.isalnum())
    return (normalized in {"ACCESSKEYID", "ACCESSKEYSECRET", "PASSWORD", "TOKEN",
                           "SECURITYTOKEN", "SECRET", "APIKEY", "AUTHORIZATION"}
            or normalized.endswith("TOKEN") or normalized.endswith("SECRET"))


@contextmanager
def _log_lock():
    """Serialize error log append/clear operations across CLI processes."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    with file_lock(_LOG_FILE.with_suffix(".lock")):
        yield


def log_error(command: str, error_code: str, error_message: str,
              args: dict = None, context: dict = None) -> None:
    """记录一条错误日志

    Args:
        command: 出错的命令或插件动作
        error_code: 稳定的错误码
        error_message: 错误消息
        args: 相关参数
        context: 额外上下文
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "command": command,
        "error_code": error_code,
        "error_message": str(error_message)[:500],
    }
    if args:
        safe_args = {}
        for k, v in args.items():
            if _is_sensitive_key(k):
                safe_args[k] = "***"
            else:
                safe_args[k] = str(v)[:200] if v is not None else None
        entry["args"] = safe_args
    if context:
        entry["context"] = _sanitize_context(context)

    try:
        with _log_lock():
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        # 诊断日志不可写时不能覆盖原始命令结果，特别是 Harness 存储检查失败路径。
        print(f"[seek] 错误日志写入失败(忽略): {exc}", file=sys.stderr)
        return


def read_errors(limit: int = 50, command: str = None) -> list:
    """读取错误日志

    Args:
        limit: 最多返回条数
        command: 按命令过滤（可选）

    Returns:
        错误记录列表（最新在前）
    """
    if not _LOG_FILE.exists():
        return []

    # 反向读取：使用 deque(maxlen) 仅在内存中保留匹配的 limit 条记录，
    # 避免全量加载整个 JSONL 后再切片（错误日志可能很大）。
    buf = deque(maxlen=limit)
    with open(_LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if command and command not in entry.get("command", ""):
                continue
            buf.append(entry)

    # deque 顺序为正序（最早在前），反转得到最新在前
    return list(reversed(buf))


def _sanitize_context(context):
    """Recursively redact context with depth, node, and byte budgets."""
    budget = {"depth": 0, "nodes": 0, "bytes": 0}
    return _sanitize_context_value(context, budget, 0)


def _sanitize_context_value(value, budget, depth):
    if depth > _CONTEXT_MAX_DEPTH or budget["nodes"] >= _CONTEXT_MAX_NODES:
        return _CONTEXT_TRUNCATED
    budget["nodes"] += 1
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                safe = "***"
            else:
                safe = _sanitize_context_value(item, budget, depth + 1)
            if not _reserve_context_bytes(key, safe, budget):
                result[_CONTEXT_TRUNCATED] = _CONTEXT_TRUNCATED
                break
            result[key] = safe
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for item in value:
            safe = _sanitize_context_value(item, budget, depth + 1)
            if not _reserve_context_bytes(None, safe, budget):
                result.append(_CONTEXT_TRUNCATED)
                break
            result.append(safe)
        return result
    safe = _truncate_context_value(value)
    _reserve_context_bytes(None, safe, budget)
    return safe


def _reserve_context_bytes(key, value, budget):
    try:
        payload = json.dumps({"k": key, "v": value}, ensure_ascii=False, default=str)
        size = len(payload.encode("utf-8"))
    except (TypeError, ValueError):
        size = len(str(value).encode("utf-8"))
    if budget["bytes"] + size > _CONTEXT_MAX_BYTES:
        return False
    budget["bytes"] += size
    return True


def _truncate_context_value(value):
    """长值截断：字符串直接截，其余 JSON 序列化后截（不可序列化降级 str）。"""
    if value is None:
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return value[:_CONTEXT_VALUE_LIMIT]
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value)
    return text[:_CONTEXT_VALUE_LIMIT]


def clear_errors() -> int:
    """清空错误日志

    Returns:
        清空的条数
    """
    with _log_lock():
        if not _LOG_FILE.exists():
            return 0
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            count = sum(1 for line in f if line.strip())
        atomic_write_text(_LOG_FILE, "")
        return count
