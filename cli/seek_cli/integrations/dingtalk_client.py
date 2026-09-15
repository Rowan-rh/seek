"""钉钉集成 — 通过 dws CLI 封装聊天/文档/通讯录等操作

dws CLI 位于 ~/.qoderwork/bin/dws，支持 --format json 输出。
本模块通过 subprocess 调用 dws 命令，解析 JSON 结果。
"""

import json
import subprocess
import shutil
from pathlib import Path

# dws CLI 路径
_DWS_PATH = shutil.which("dws") or str(Path.home() / ".qoderwork" / "bin" / "dws")


def _check_dws() -> str:
    """检查 dws CLI 是否可用"""
    if not _DWS_PATH or not Path(_DWS_PATH).exists():
        raise RuntimeError(
            "dws CLI not found. Expected at ~/.qoderwork/bin/dws\n"
            "Install: see ~/.qoderwork/skills/dws/SKILL.md"
        )
    return _DWS_PATH


def _redact_arg(value: str) -> str:
    """Keep command failures useful without logging message bodies or secrets."""
    text = str(value)
    return text if len(text) <= 80 else text[:77] + "..."


def _run_dws(args: list, timeout: int = 60) -> dict:
    """执行 dws 命令并返回解析后的 JSON

    Args:
        args: dws 子命令参数列表

    Returns:
        解析后的 JSON dict
    """
    _check_dws()
    cmd = [_DWS_PATH] + args + ["--format", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, shell=False)
    if result.returncode != 0:
        safe_cmd = " ".join(_redact_arg(item) for item in cmd)
        raise RuntimeError(f"dws command failed: {safe_cmd}\nstderr: {_redact_arg(result.stderr)}")
    try:
        data = json.loads(result.stdout)
        # dws 错误响应结构: {"error": {...}}
        if isinstance(data, dict) and "error" in data and data.get("error"):
            err = data["error"]
            raise RuntimeError(
                f"dws error [{err.get('code', '?')}]: {err.get('message', '')}"
            )
        return data
    except json.JSONDecodeError:
        return {"raw_output": result.stdout.strip()}


# ============================================================
# 群聊搜索
# ============================================================

def search_groups(keyword: str) -> dict:
    """搜索群聊

    Args:
        keyword: 群名关键词

    Returns:
        匹配的群聊列表
    """
    return _run_dws(["chat", "search", "--query", keyword])


# ============================================================
# 消息查询
# ============================================================

def list_messages(group: str = "", user: str = "", open_dingtalk_id: str = "",
                 time_str: str = "", direction: str = "newer",
                 limit: int = 50) -> dict:
    """拉取会话消息内容

    Args:
        group: 群聊 openConversationId
        user: 单聊用户 userId
        open_dingtalk_id: 单聊用户 openDingTalkId
        time_str: 开始时间 "yyyy-MM-dd HH:mm:ss"
        direction: newer=从给定时间往现在拉, older=往以前拉
        limit: 返回数量

    Returns:
        消息列表
    """
    args = ["chat", "message", "list"]
    if group:
        args += ["--group", group]
    elif user:
        args += ["--user", user]
    elif open_dingtalk_id:
        args += ["--open-dingtalk-id", open_dingtalk_id]
    else:
        raise ValueError("must specify --group, --user, or --open-dingtalk-id")
    if time_str:
        args += ["--time", time_str]
    if direction:
        args += ["--direction", direction]
    if limit:
        args += ["--limit", str(limit)]
    return _run_dws(args)


def search_messages(keyword: str, group: str = "", sender_ids: str = "",
                    time_from: str = "", time_to: str = "",
                    at_me: bool = False, limit: int = 50) -> dict:
    """多维度搜索消息

    Args:
        keyword: 搜索关键词
        group: 指定会话 openConversationId
        sender_ids: 发送者 openDingTalkId 列表（逗号分隔）
        time_from: 开始时间
        time_to: 结束时间
        at_me: 是否只搜 @我 的消息
        limit: 返回数量

    Returns:
        匹配的消息列表
    """
    args = ["chat", "message", "search"]
    if keyword:
        args += ["--query", keyword]
    if group:
        args += ["--conversation-ids", group]
    if sender_ids:
        args += ["--sender-ids", sender_ids]
    if time_from:
        args += ["--start-time", time_from]
    if time_to:
        args += ["--end-time", time_to]
    if at_me:
        args += ["--at-me"]
    if limit:
        args += ["--limit", str(limit)]
    return _run_dws(args)


def list_messages_by_time(time_from: str = "", time_to: str = "",
                          limit: int = 50) -> dict:
    """拉取指定时间范围内当前用户的所有会话消息

    Args:
        time_from: 开始时间
        time_to: 结束时间
        limit: 返回数量

    Returns:
        消息列表
    """
    args = ["chat", "message", "list-by-time"]
    if time_from:
        args += ["--start-time", time_from]
    if time_to:
        args += ["--end-time", time_to]
    if limit:
        args += ["--limit", str(limit)]
    return _run_dws(args)


def list_unread_conversations() -> dict:
    """获取未读会话列表"""
    return _run_dws(["chat", "message", "list-unread-conversations"])


# ============================================================
# 消息发送
# ============================================================

def send_message(text: str, group: str = "", user: str = "",
                open_dingtalk_id: str = "", title: str = "") -> dict:
    """发送消息（群聊或单聊）

    Args:
        text: 消息内容
        group: 群聊 openConversationId
        user: 单聊用户 userId
        open_dingtalk_id: 单聊用户 openDingTalkId
        title: 消息标题（可选）

    Returns:
        发送结果
    """
    args = ["chat", "message", "send", "--text", text]
    if group:
        args += ["--group", group]
    elif user:
        args += ["--user", user]
    elif open_dingtalk_id:
        args += ["--open-dingtalk-id", open_dingtalk_id]
    else:
        raise ValueError("must specify --group, --user, or --open-dingtalk-id")
    if title:
        args += ["--title", title]
    return _run_dws(args)


# ============================================================
# 通讯录
# ============================================================

def search_contacts(query: str) -> dict:
    """搜索联系人

    Args:
        query: 姓名/花名关键词

    Returns:
        匹配的用户列表
    """
    return _run_dws(["contact", "user", "search", "--query", query])


def list_group_members(group_id: str) -> dict:
    """查看群成员列表

    Args:
        group_id: 群 openConversationId

    Returns:
        成员列表
    """
    return _run_dws(["chat", "group", "members", "--id", group_id])


# ============================================================
# 钉钉文档（通过 dws 的 doc 服务）
# ============================================================

def read_doc(url: str) -> dict:
    """读取钉钉文档内容（Markdown 格式）

    Args:
        url: 钉钉文档链接

    Returns:
        文档内容
    """
    return _run_dws(["doc", "read", "--url", url])
