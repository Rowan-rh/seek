"""云网络工单查询命令 — 封装 qt-expert API"""

from seek_cli.integrations import expert_client
from seek_cli.output import success, error


def cmd_ticket_search(args) -> dict:
    """搜索云网络服务单列表"""
    try:
        result = expert_client.search_flows(
            keyword=args.keyword or "",
            flow_type=args.flow_type or "afterSale",
            status=args.status or "",
            product=args.product or "",
            page=args.page,
            page_size=args.page_size,
        )
        # 提取关键字段
        items = result.get("dataList", result.get("data", []))
        total = result.get("totalCount", len(items))
        summary_list = [
            {
                "flowId": f.get("flowId", ""),
                "title": f.get("questionTitle", ""),
                "status": f.get("statusDesc", ""),
                "product": f.get("questionProductDesc", ""),
                "dutyPerson": f.get("dutyPerson", ""),
                "creator": f.get("creatorCname", ""),
                "gmtCreated": f.get("gmtCreatedStr", ""),
                "conversationId": f.get("conversationId", ""),
                "costMin": f.get("costMin", ""),
                "level": f.get("level", ""),
            }
            for f in items
        ]
        return success({
            "flows": summary_list,
            "total": total,
            "page": args.page,
            "pageSize": args.page_size,
        }, message=f"搜索到 {total} 个服务单（第 {args.page} 页）")
    except RuntimeError as e:
        return error(str(e), code="EXPERT_API_ERROR")


def cmd_ticket_detail(args) -> dict:
    """获取服务单详情"""
    try:
        detail = expert_client.get_flow_detail(
            args.flow_id,
            user_id=args.user_id or "",
            dept=args.dept or "",
        )
        return success(detail, message=f"服务单: {detail.get('questionTitle', '')[:50]}")
    except RuntimeError as e:
        return error(str(e), code="EXPERT_API_ERROR")


def cmd_ticket_orders(args) -> dict:
    """查询服务单关联的工单"""
    try:
        orders = expert_client.search_orders(args.flow_id)
        if not isinstance(orders, list):
            orders = orders.get("dataList", orders.get("data", [])) if isinstance(orders, dict) else []
        return success({
            "flowId": args.flow_id,
            "orders": orders,
            "count": len(orders),
        }, message=f"关联工单: {len(orders)} 个")
    except RuntimeError as e:
        return error(str(e), code="EXPERT_API_ERROR")


def cmd_ticket_lifecycle(args) -> dict:
    """查询服务单生命周期（处理记录）"""
    try:
        lifecycle = expert_client.get_flow_lifecycle(args.flow_id)
        if not isinstance(lifecycle, list):
            lifecycle = lifecycle.get("dataList", lifecycle.get("data", [])) if isinstance(lifecycle, dict) else []
        return success({
            "flowId": args.flow_id,
            "lifecycle": lifecycle,
            "count": len(lifecycle),
        }, message=f"生命周期记录: {len(lifecycle)} 条")
    except RuntimeError as e:
        return error(str(e), code="EXPERT_API_ERROR")


def cmd_ticket_history(args) -> dict:
    """查询历史相似工单"""
    try:
        result = expert_client.query_history(args.title)
        if isinstance(result, list):
            items = result
        elif isinstance(result, dict):
            items = result.get("dataList", result.get("data", []))
        else:
            items = []
        summary_list = [
            {
                "flowId": h.get("flowId", ""),
                "title": h.get("questionTitle", ""),
                "status": h.get("statusDesc", ""),
                "dutyPerson": h.get("dutyPerson", ""),
                "conclusion": str(h.get("conclusion", ""))[:200],
                "gmtCreated": h.get("gmtCreatedStr", h.get("gmtCreated", "")),
                "product": h.get("questionProductDesc", ""),
            }
            for h in items[:20]
        ]
        return success({
            "query": args.title,
            "history": summary_list,
            "count": len(summary_list),
        }, message=f"相似历史工单: {len(summary_list)} 个")
    except RuntimeError as e:
        return error(str(e), code="EXPERT_API_ERROR")


def cmd_ticket_analyze(args) -> dict:
    """AI 聚合查询：一次返回详情+关联工单+生命周期+相似历史"""
    try:
        result = expert_client.analyze_flow(
            args.flow_id,
            user_id=args.user_id or "",
            dept=args.dept or "",
        )
        s = result.get("summary", {})
        msg = (
            f"服务单 {args.flow_id} 分析:\n"
            f"  标题: {s.get('title', '')[:50]}\n"
            f"  状态: {s.get('status', '')}\n"
            f"  处理人: {s.get('dutyPerson', '')}\n"
            f"  关联工单: {s.get('orderCount', 0)} 个\n"
            f"  生命周期: {s.get('lifecycleCount', 0)} 条\n"
            f"  相似历史: {s.get('similarCount', 0)} 个"
        )
        return success(result, message=msg)
    except RuntimeError as e:
        return error(str(e), code="EXPERT_API_ERROR")
