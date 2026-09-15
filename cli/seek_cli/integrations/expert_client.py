"""qt-expert API 客户端 — 查询云网络服务单

调用 qt-expert 的 /xyt/* 系列接口，查询云网络工单/服务单信息。
默认使用预发环境: http://pre-qt-expert.aliyun-inc.com
可通过 ~/.seek/config/expert.json 或环境变量 QT_EXPERT_HOST 覆盖。

⚠️ 安全提示：默认走 HTTP 明文（阿里内网域名）。若配置了 https:// 将自动切换；
   仍然走 http 时会在首次调用时打印安全警告到 stderr。
"""

import json
import os
import requests
import sys
from typing import Optional

from seek_cli.paths import seek_path

_CONFIG_FILE = seek_path("config", "expert.json")
DEFAULT_HOST = "http://pre-qt-expert.aliyun-inc.com"
_warned_http = False  # 模块级：每个进程只警告一次明文传输


def get_host() -> str:
    """获取 qt-expert 服务地址"""
    # 1. 环境变量
    env_host = os.environ.get("QT_EXPERT_HOST")
    if env_host:
        return env_host
    # 2. 统一配置 ~/.seek/config/seek.json（seek config set hosts.expert）
    from seek_cli import settings
    unified_host = settings.get_setting("hosts.expert")
    if unified_host:
        return unified_host
    # 3. 旧配置文件（兼容）
    if _CONFIG_FILE.exists():
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if cfg.get("host"):
                    return cfg["host"]
        except (json.JSONDecodeError, OSError):
            pass
    # 4. 默认预发
    return DEFAULT_HOST


# 兼容旧调用方。
_get_host = get_host


def _call_api(path: str, params: dict = None, timeout: int = 30) -> dict:
    """调用 qt-expert API

    Args:
        path: API 路径 (如 /xyt/queryDiagnoseFlow)
        params: 查询参数

    Returns:
        解析后的 JSON dict (data 字段已解包)
    """
    global _warned_http
    host = get_host()
    url = f"{host}{path}"
    # 安全警告：HTTP 明文传输时打印一次性警告（工号等敏感字段以 query 形式传输）
    # 已知风险且不想刷屏时可设 SEEK_QUIET_WARNINGS=1 或 seek config set options.quiet_warnings true
    from seek_cli import settings
    if (url.lower().startswith("http://") and not _warned_http
            and not settings.quiet_warnings()):
        print(
            f"[seek] ⚠️ qt-expert API 走 HTTP 明文: {host}（敏感参数如 userId 可能被中间人截获）。"
            f"建议在 ~/.seek/config/expert.json 设置 \"host\": \"https://...\"",
            file=sys.stderr,
        )
        _warned_http = True
    resp = requests.get(url, params=params or {}, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"API {path} returned HTTP {resp.status_code}: {resp.text[:200]}")

    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"API {path} error: code={data.get('code')}, msg={data.get('msg', '')}")

    # data 字段可能是 JSON 字符串（qt-expert 的特殊包装），需要二次解析
    inner = data.get("data")
    if isinstance(inner, str):
        try:
            inner = json.loads(inner)
        except json.JSONDecodeError:
            pass
    return inner if inner is not None else {}


# ============================================================
# 服务单查询
# ============================================================

def search_flows(keyword: str = "", flow_type: str = "afterSale",
                 status: str = "", product: str = "",
                 page: int = 1, page_size: int = 20) -> dict:
    """搜索云网络服务单列表

    Args:
        keyword: 关键词（匹配标题）
        flow_type: 服务单类型 (afterSale=售后 / bigCustomer=大客户 / yidong=异动)
        status: 状态过滤
        product: 产品过滤
        page: 页码
        page_size: 每页数量

    Returns:
        {totalCount, dataList: [...]}
    """
    params = {
        "flowType": flow_type,
        "pageNum": page,
        "pageSize": page_size,
    }
    if keyword:
        params["questionTitle"] = keyword
    if status:
        params["status"] = status
    if product:
        params["questionProduct"] = product
    return _call_api("/xyt/queryDiagnoseFlow", params)


def get_flow_detail(flow_id: str, user_id: str = "", dept: str = "") -> dict:
    """获取服务单详情

    Args:
        flow_id: 服务单 ID (FLOW-xxx)
        user_id: 用户工号（权限校验）
        dept: 部门

    Returns:
        服务单详情 dict
    """
    params = {"flowId": flow_id}
    if user_id:
        params["userId"] = user_id
    if dept:
        params["dept"] = dept
    return _call_api("/xyt/getDiagnoseFlowDetail", params)


def get_flow_lifecycle(flow_id: str) -> dict:
    """查询服务单生命周期（处理记录）

    Args:
        flow_id: 服务单 ID

    Returns:
        生命周期记录列表
    """
    return _call_api("/xyt/queryFlowLifeCycle", {"flowId": flow_id})


def search_orders(flow_id: str) -> dict:
    """查询服务单关联的工单

    Args:
        flow_id: 服务单 ID

    Returns:
        关联工单列表
    """
    return _call_api("/xyt/searchOrders", {"flowId": flow_id})


def query_history(title: str, flow_type: str = "afterSale") -> dict:
    """查询历史已完成服务单（按标题关键词）

    Args:
        title: 标题关键词
        flow_type: 服务单类型

    Returns:
        历史服务单列表
    """
    return _call_api("/xyt/queryHistoryDiagFlow", {
        "questionTitle": title,
        "flowType": flow_type,
    })


def query_diag_records(flow_id: str = "", work_id: str = "",
                       cname: str = "") -> dict:
    """查询诊断处理记录

    Args:
        flow_id: 服务单 ID
        work_id: 工号
        cname: 花名

    Returns:
        处理记录列表
    """
    params = {}
    if flow_id:
        params["flowId"] = flow_id
    if work_id:
        params["workId"] = work_id
    if cname:
        params["cname"] = cname
    return _call_api("/xyt/queryDiagRecords", params)


def analyze_flow(flow_id: str, user_id: str = "", dept: str = "") -> dict:
    """AI 聚合查询：一次返回详情+关联工单+生命周期+相似历史

    Args:
        flow_id: 服务单 ID
        user_id: 用户工号

    Returns:
        {
            "detail": {...},
            "orders": [...],
            "lifecycle": [...],
            "similar_history": [...],
            "summary": {...}
        }
    """
    # 1. 详情
    detail = get_flow_detail(flow_id, user_id, dept)

    # 2. 关联工单
    orders = search_orders(flow_id)

    # 3. 生命周期
    lifecycle = get_flow_lifecycle(flow_id)

    # 4. 相似历史（用标题前 20 字作为关键词）
    title = detail.get("questionTitle", "") if isinstance(detail, dict) else ""
    similar = []
    if title:
        keyword = title[:20]
        history = query_history(keyword)
        if isinstance(history, list):
            # 排除当前工单
            similar = [h for h in history if h.get("flowId") != flow_id][:10]
        elif isinstance(history, dict):
            items = history.get("dataList", history.get("data", []))
            similar = [h for h in items if h.get("flowId") != flow_id][:10]

    # 5. 摘要
    summary = {
        "flowId": flow_id,
        "title": title,
        "status": detail.get("statusDesc", "") if isinstance(detail, dict) else "",
        "dutyPerson": detail.get("dutyPerson", "") if isinstance(detail, dict) else "",
        "creator": detail.get("creatorCname", "") if isinstance(detail, dict) else "",
        "product": detail.get("questionProductDesc", "") if isinstance(detail, dict) else "",
        "questionType": detail.get("questionTypeDesc", "") if isinstance(detail, dict) else "",
        "conclusion": detail.get("conclusion", "") if isinstance(detail, dict) else "",
        "orderCount": len(orders) if isinstance(orders, list) else 0,
        "lifecycleCount": len(lifecycle) if isinstance(lifecycle, list) else 0,
        "similarCount": len(similar),
    }

    return {
        "summary": summary,
        "detail": detail,
        "orders": orders if isinstance(orders, list) else [],
        "lifecycle": lifecycle if isinstance(lifecycle, list) else [],
        "similar_history": similar,
    }

# 兼容别名
_DEFAULT_HOST = DEFAULT_HOST
