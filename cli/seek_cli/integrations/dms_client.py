"""DMS MCP 客户端 — 通过 stdio JSON-RPC 调用 DMS MCP Server

DMS MCP Server 配置在 ~/.qoderwork/mcp.json 的 mcpServers["dms-mcp-server"]。
通过 uvx 启动子进程，stdin/stdout JSON-RPC 2.0 通信。

DMS MCP 可用工具:
- getInstance: 根据 host:port 获取实例信息
- searchDatabase: 按 schemaName 搜索数据库
- getDatabase: 获取指定数据库详情
- listTables: 列出数据表
- getTableDetailInfo: 获取表 schema 和索引
- executeScript: 执行 SQL
- listSecurityColumns: 获取安全列
"""

import json
import os
import select
import subprocess
from pathlib import Path
from typing import Optional

from seek_cli import __version__
from seek_cli.perf_log import perf_span

_MCP_CONFIG = Path.home() / ".qoderwork" / "mcp.json"
DMS_MCP_GUIDE_URL = (
    "https://alidocs.dingtalk.com/i/nodes/"
    "EpGBa2Lm8aZxe5myCZYKkoYkWgN7R35y"
)
_PROTOCOL_VERSION = "2024-11-05"
_CLIENT_INFO = {"name": "seek-cli", "version": __version__}
_request_id = 0
# 单次 readline 等待超时（秒）。避免 DMS MCP 子进程无响应时 CLI 永久挂死。
_READLINE_TIMEOUT = 30.0


def _get_dms_config() -> dict:
    """从 mcp.json 读取 DMS MCP server 配置"""
    if not _MCP_CONFIG.exists():
        raise RuntimeError(
            f"mcp.json not found at {_MCP_CONFIG}\n"
            f"Configure DMS MCP server first. Guide: {DMS_MCP_GUIDE_URL}"
        )
    with open(_MCP_CONFIG, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    servers = cfg.get("mcpServers", {})
    dms = servers.get("dms-mcp-server")
    if not dms:
        raise RuntimeError(
            "dms-mcp-server not found in mcp.json\n"
            "Add to ~/.qoderwork/mcp.json:\n"
            '  "dms-mcp-server": {\n'
            '    "command": "uvx",\n'
            '    "args": ["alibabacloud-dms-mcp-server-inner@latest"],\n'
            '    "env": {"ACCESS_KEY_ID": "...", "ACCESS_KEY_SECRET": "..."}\n'
            "  }\n"
            f"Guide: {DMS_MCP_GUIDE_URL}"
        )
    return dms


class DmsMcpClient:
    """DMS MCP stdio 客户端"""

    def __init__(self):
        self._proc = None
        self._initialized = False

    def _start(self):
        """启动 DMS MCP 子进程"""
        if self._proc is not None:
            return
        cfg = _get_dms_config()
        cmd = cfg["command"]
        args = cfg.get("args", [])
        env = os.environ.copy()
        env.update(cfg.get("env", {}))

        self._proc = subprocess.Popen(
            [cmd] + args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            text=True,
            shell=False,
        )

    def _send_request(self, method: str, params: dict = None) -> dict:
        """发送 JSON-RPC 请求并等待响应"""
        global _request_id
        _request_id += 1
        # 防御性自检：proc 已 None 或已终止时清空状态，由 _ensure_initialized 自动重启
        if self._proc is None or self._proc.poll() is not None:
            self._proc = None
            self._initialized = False
            self._ensure_initialized()
        req = {
            "jsonrpc": "2.0",
            "id": _request_id,
            "method": method,
            "params": params or {},
        }
        line = json.dumps(req) + "\n"
        self._proc.stdin.write(line)
        self._proc.stdin.flush()

        # 读取响应（跳过非 JSON 行），使用 select 避免 readline 永久阻塞
        while True:
            ready, _, _ = select.select(
                [self._proc.stdout], [], [], _READLINE_TIMEOUT
            )
            if not ready:
                # 超时：终止子进程、清理引用、抛错
                # 关键：必须把 self._proc 设为 None，否则下次 _send_request 会向
                # 已关闭管道 write() 抛 ValueError
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=2)
                except Exception:
                    pass
                self._proc = None
                self._initialized = False
                raise RuntimeError(
                    f"DMS MCP server response timeout after {_READLINE_TIMEOUT}s"
                )
            resp_line = self._proc.stdout.readline()
            if not resp_line:
                # 子进程关闭了 stdout：清理引用让下次自动重启
                self._proc = None
                self._initialized = False
                raise RuntimeError("DMS MCP server closed connection")
            resp_line = resp_line.strip()
            if not resp_line:
                continue
            try:
                resp = json.loads(resp_line)
                if resp.get("id") == _request_id:
                    break
            except json.JSONDecodeError:
                continue

        if "error" in resp:
            err = resp["error"]
            raise RuntimeError(f"DMS MCP error: {err.get('message', err)}")
        return resp.get("result", {})

    def _ensure_initialized(self):
        """确保 MCP 握手完成"""
        if self._initialized:
            return
        self._start()
        self._send_request("initialize", {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": _CLIENT_INFO,
        })
        # 发送 initialized 通知
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self._proc.stdin.write(json.dumps(notif) + "\n")
        self._proc.stdin.flush()
        self._initialized = True

    def call_tool(self, tool_name: str, arguments: dict = None) -> dict:
        """调用 DMS MCP 工具

        Args:
            tool_name: 工具名（如 executeScript, listTables）
            arguments: 工具参数

        Returns:
            工具返回结果
        """
        # perf 观测（L2 集成级）：含 MCP server 冷启动在内的完整调用耗时。
        # _ensure_initialized 必须在 span 内：首次调用的 uvx 子进程启动 + initialize
        # 握手是冷启动主要构成，漏计会把秒级耗时误归因到进程开销。
        sql = arguments.get("sql", "") if isinstance(arguments, dict) else ""
        with perf_span(f"dms {tool_name}", "dms_call",
                       {"tool": tool_name, "sql": sql if isinstance(sql, str) else ""}):
            self._ensure_initialized()
            result = self._send_request("tools/call", {
                "name": tool_name,
                "arguments": arguments or {},
            })
        # MCP 工具返回 {"content": [{"type": "text", "text": "..."}]}
        contents = result.get("content", [])
        if not contents:
            return {}
        text = contents[0].get("text", "")
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return {"raw_text": text}

    def list_tools(self) -> list:
        """列出 DMS MCP 可用的工具"""
        with perf_span("dms tools/list", "dms_call", {"tool": "tools/list"}):
            self._ensure_initialized()
            result = self._send_request("tools/list", {})
        return result.get("tools", [])

    def close(self) -> None:
        """关闭 MCP 子进程

        子进程可能已经退出或管道已断开，所有操作均吞异常，
        避免 atexit 注册在解释器退出时产生噪音日志。
        """
        if self._proc is None:
            return
        proc = self._proc
        self._proc = None
        self._initialized = False
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


# 模块级单例
_client = None


def _get_client() -> DmsMcpClient:
    global _client
    if _client is None:
        _client = DmsMcpClient()
    return _client


def call_dms(tool_name: str, arguments: dict = None) -> dict:
    """便捷方法：调用 DMS MCP 工具"""
    client = _get_client()
    return client.call_tool(tool_name, arguments)


def list_dms_tools() -> list:
    """便捷方法：列出 DMS MCP 工具"""
    return _get_client().list_tools()


def close_dms() -> None:
    """关闭 DMS MCP 连接"""
    global _client
    if _client:
        _client.close()
        _client = None
