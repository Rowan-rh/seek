"""钉钉命令 — 群聊搜索/消息查询/消息发送/通讯录/文档"""

from seek_cli.integrations import dingtalk_client
from seek_cli.output import success, error


def _extract_result(data, *keys, default=None):
    """从 dws 返回中提取结果，兼容多种结构

    dws 返回结构不统一：
    - {"result": {"groups": [...]}}  → result 是 dict
    - {"result": [...]}             → result 是 list
    - {"result": {"messages": [...]}}
    """
    result = data.get("result", data) if isinstance(data, dict) else data
    if isinstance(result, list):
        # 列表直接返回（default 在列表场景下无意义，保持向后兼容）
        return result
    if isinstance(result, dict):
        for k in keys:
            if k in result:
                return result[k]
    return default if default is not None else result


# ============================================================
# 群聊搜索
# ============================================================

def cmd_dingtalk_groups(args) -> dict:
    """搜索群聊"""
    try:
        result = dingtalk_client.search_groups(args.query)
        groups = _extract_result(result, "groups", default=[])
        return success({
            "query": args.query,
            "groups": [
                {
                    "title": g.get("title", ""),
                    "openConversationId": g.get("openConversationId", ""),
                    "memberCount": g.get("memberCount", 0),
                    "groupType": g.get("groupType", ""),
                    "createAt": g.get("createAt", ""),
                }
                for g in groups
            ],
            "total": len(groups),
        }, message=f"搜索到 {len(groups)} 个群")
    except RuntimeError as e:
        return error(str(e), code="DWS_ERROR")


# ============================================================
# 消息查询
# ============================================================

def cmd_dingtalk_messages(args) -> dict:
    """拉取会话消息（群聊/单聊）"""
    try:
        result = dingtalk_client.list_messages(
            group=args.group or "",
            user=args.user or "",
            open_dingtalk_id=args.open_dingtalk_id or "",
            time_str=args.time,
            direction=args.direction or "newer",
            limit=args.limit or 50,
        )
        msgs = _extract_result(result, "messages", default=[])
        raw = result.get("result", result) if isinstance(result, dict) else {}
        has_more = raw.get("hasMore", False) if isinstance(raw, dict) else False
        return success({
            "messages": msgs,
            "count": len(msgs),
            "hasMore": has_more,
        }, message=f"拉取到 {len(msgs)} 条消息")
    except RuntimeError as e:
        return error(str(e), code="DWS_ERROR")


def cmd_dingtalk_search_messages(args) -> dict:
    """多维度搜索消息"""
    try:
        result = dingtalk_client.search_messages(
            keyword=args.query,
            group=args.group or "",
            sender_ids=args.sender_ids or "",
            time_from=args.time_from or "",
            time_to=args.time_to or "",
            at_me=args.at_me,
            limit=args.limit or 50,
        )
        msgs = _extract_result(result, "messages", default=[])
        return success({
            "query": args.query,
            "messages": msgs,
            "count": len(msgs),
        }, message=f"搜索到 {len(msgs)} 条消息")
    except RuntimeError as e:
        return error(str(e), code="DWS_ERROR")


def cmd_dingtalk_unread(args) -> dict:
    """获取未读会话列表"""
    try:
        result = dingtalk_client.list_unread_conversations()
        convs = result.get("result", {}).get("conversations", [])
        return success({
            "conversations": convs,
            "count": len(convs),
        }, message=f"{len(convs)} 个未读会话")
    except RuntimeError as e:
        return error(str(e), code="DWS_ERROR")


# ============================================================
# 消息发送
# ============================================================

def cmd_dingtalk_send(args) -> dict:
    """发送消息（群聊/单聊）"""
    try:
        result = dingtalk_client.send_message(
            text=args.text,
            group=args.group or "",
            user=args.user or "",
            open_dingtalk_id=args.open_dingtalk_id or "",
            title=args.title or "",
        )
        return success(result.get("result", result),
                        message="消息已发送")
    except RuntimeError as e:
        return error(str(e), code="DWS_ERROR")


# ============================================================
# 通讯录/群成员
# ============================================================

def cmd_dingtalk_contact(args) -> dict:
    """搜索联系人"""
    try:
        result = dingtalk_client.search_contacts(args.query)
        users = _extract_result(result, "users", default=[])
        return success({
            "query": args.query,
            "users": users,
            "count": len(users),
        }, message=f"找到 {len(users)} 个联系人")
    except RuntimeError as e:
        return error(str(e), code="DWS_ERROR")


def cmd_dingtalk_members(args) -> dict:
    """查看群成员列表"""
    try:
        result = dingtalk_client.list_group_members(args.group)
        members = _extract_result(result, "members", default=[])
        return success({
            "group": args.group,
            "members": members,
            "count": len(members),
        }, message=f"群成员: {len(members)} 人")
    except RuntimeError as e:
        return error(str(e), code="DWS_ERROR")


# ============================================================
# 钉钉文档
# ============================================================

def cmd_dingtalk_doc_read(args) -> dict:
    """读取钉钉文档"""
    try:
        result = dingtalk_client.read_doc(args.url)
        return success(result.get("result", result),
                        message="文档读取完成")
    except RuntimeError as e:
        return error(str(e), code="DWS_ERROR")
