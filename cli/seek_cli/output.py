"""输出格式化 — 默认 JSON（供 agent 解析），可选 text（供人阅读）"""

import json
import sys
from typing import Any, Optional


def success(data: Any, message: str = "") -> dict:
    """构造成功响应"""
    return {"status": "ok", "data": data, "message": message}


def error(message: str, code: str = "ERROR", data: Any = None) -> dict:
    """构造错误响应"""
    return {"status": "error", "error": {"code": code, "message": message}, "data": data}


def print_result(result: dict, fmt: str = "json") -> None:
    """输出结果到 stdout

    Args:
        result: 结构化结果 dict
        fmt: 输出格式 — "json"（默认，供 agent）或 "text"（供人阅读）
    """
    if fmt == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        _print_text(result)


def _print_text(result: dict) -> None:
    """文本格式输出（简化的可读格式）

    注意：error 状态仅打印文本，不在此处 sys.exit。
    退出码由 cli.py:main() 在错误日志记录之后统一控制，
    保证 errors.jsonl 能被正确写入。
    """
    status = result.get("status", "unknown")
    if status == "error":
        err = result.get("error", {})
        print(f"[ERROR] {err.get('code', '')}: {err.get('message', '')}")
        if result.get("data"):
            print(f"  context: {json.dumps(result['data'], ensure_ascii=False, default=str)}")
        return

    data = result.get("data")
    msg = result.get("message", "")
    if msg:
        print(f"# {msg}")

    if data is None:
        return
    if isinstance(data, list):
        for item in data:
            _print_item(item)
            print()
    elif isinstance(data, dict):
        _print_item(data)
    else:
        print(data)


_MAX_PRINT_DEPTH = 8  # 防止深层嵌套数据触发 RecursionError 或无限输出


def _print_item(item: Any, indent: int = 0) -> None:
    """递归打印单个项目

    Args:
        item: 待打印的对象
        indent: 当前缩进级别

    Note:
        通过 _MAX_PRINT_DEPTH 限制递归深度，防止恶意/异常数据导致栈溢出。
    """
    if indent > _MAX_PRINT_DEPTH:
        print(f"{'  ' * indent}...(max depth {_MAX_PRINT_DEPTH} reached)")
        return
    pad = "  " * indent
    if isinstance(item, dict):
        for k, v in item.items():
            if isinstance(v, (dict, list)):
                print(f"{pad}{k}:")
                _print_item(v, indent + 1)
            else:
                print(f"{pad}{k}: {v}")
    elif isinstance(item, list):
        for i, sub in enumerate(item):
            print(f"{pad}[{i}]")
            _print_item(sub, indent + 1)
    else:
        print(f"{pad}{item}")
