"""SLS 日志查询封装 — 基于 aliyun-log Python SDK

认证方式（按优先级）:
1. 环境变量: ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET
2. 统一配置: ~/.seek/config/seek.json（seek config set sls.access_key_id ...）
3. ~/.seek/credentials.json
4. ~/.alibabacloud/config.json (阿里云 CLI 配置)

查询支持:
- 关键词查询 (GetLogs)
- SQL 查询 (GetLogs with SQL)
- 时间范围: 支持 "15m", "1h", "1d" 等简写或 unix timestamp
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from seek_cli.config import get_all_sls_configs, resolve_env
from seek_cli.paths import seek_path
from seek_cli.perf_log import perf_span

try:
    from aliyun.log import LogClient, GetLogsRequest
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


_CREDENTIALS_FILE = seek_path("credentials.json")
# 阿里云 CLI 配置文件（两个可能的路径都查）
_ALIYUN_CONFIGS = [
    Path.home() / ".aliyun" / "config.json",       # aliyun CLI v3
    Path.home() / ".alibabacloud" / "config.json",  # aliyun CLI v2
]


def _get_credentials() -> dict:
    """获取 SLS 认证信息"""
    # 1. 环境变量
    ak = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID")
    sk = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
    token = os.environ.get("ALIBABA_CLOUD_SECURITY_TOKEN")
    if ak and sk:
        return {"access_key_id": ak, "access_key_secret": sk,
                "security_token": token}

    # 2. 统一配置 ~/.seek/config/seek.json（见 seek config set sls.access_key_id）
    from seek_cli import settings
    s_ak = settings.get_setting("sls.access_key_id")
    s_sk = settings.get_setting("sls.access_key_secret")
    if s_ak and s_sk:
        return {"access_key_id": s_ak, "access_key_secret": s_sk,
                "security_token": settings.get_setting("sls.security_token")}

    # 3. seek credentials 文件
    if _CREDENTIALS_FILE.exists():
        with open(_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
            creds = json.load(f)
        if creds.get("access_key_id") and creds.get("access_key_secret"):
            return creds

    # 4. 阿里云 CLI 配置（检查多个可能的路径）
    for cfg_path in _ALIYUN_CONFIGS:
        if not cfg_path.exists():
            continue
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        # 查找当前 profile
        profiles = cfg.get("profiles", [])
        current = cfg.get("current", "")
        for p in profiles:
            if p.get("name") == current or (not current and p == profiles[0]):
                mode = p.get("mode", "")
                if mode in ("AK", "StsToken") and p.get("access_key_id"):
                    return {
                        "access_key_id": p.get("access_key_id"),
                        "access_key_secret": p.get("access_key_secret"),
                        "security_token": p.get("sts_token"),
                    }

    raise RuntimeError(
        "No SLS credentials found. Configure one of:\n"
        "  1. Environment variables: ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET\n"
        "  2. Unified config: seek config set sls.access_key_id / sls.access_key_secret\n"
        f"  3. Credentials file: {_CREDENTIALS_FILE}\n"
        f"  4. Aliyun CLI config: {_ALIYUN_CONFIGS[0]} or {_ALIYUN_CONFIGS[1]}"
    )


# LogClient 缓存：按 endpoint 缓存实例，避免每次查询都重建连接。
# 凭据通过 _get_credentials() 在初始化时一次性获取并绑定到实例。
# 注意：缓存绑定了凭据，AK/SK 轮换后必须调用 invalidate_log_client_cache()。
_log_client_cache: dict = {}


def get_log_client(endpoint: str):
    """获取（或创建）endpoint 对应的 LogClient 实例

    Args:
        endpoint: SLS endpoint（如 cn-hangzhou.log.aliyuncs.com）

    Returns:
        LogClient 实例
    """
    if endpoint in _log_client_cache:
        return _log_client_cache[endpoint]
    creds = _get_credentials()
    client = LogClient(
        endpoint,
        creds["access_key_id"],
        creds["access_key_secret"],
        securityToken=creds.get("security_token"),
    )
    _log_client_cache[endpoint] = client
    return client


def invalidate_log_client_cache() -> int:
    """清空 LogClient 缓存，强制下次重建（凭据变更后调用）

    Returns:
        被清理的缓存条目数
    """
    global _log_client_cache
    count = len(_log_client_cache)
    _log_client_cache = {}
    return count


def _parse_datetime_token(token: str) -> int:
    """解析单个人类可读时间 token 为 unix timestamp

    Args:
        token: "YYYY-MM-DD HH:MM:SS" 或 "YYYY-MM-DD" 格式的时间字符串

    Returns:
        本地时区对应的 unix timestamp

    Raises:
        ValueError: 格式不合法
    """
    from datetime import datetime
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return int(time.mktime(datetime.strptime(token, fmt).timetuple()))
        except ValueError:
            continue
    raise ValueError(
        f"invalid datetime '{token}'; use 'YYYY-MM-DD HH:MM:SS' or 'YYYY-MM-DD'"
    )


def parse_time_range(time_range: str) -> tuple:
    """解析时间范围字符串为 (from, to) unix timestamp

    支持:
    - "15m" / "1h" / "2d" — 最近 N 分钟/小时/天
    - "1700000000,1700001000" — unix timestamp 范围
    - "2026-08-03 00:00:00,2026-08-10 00:00:00" — 人类可读时间范围
      （也接受 "YYYY-MM-DD,YYYY-MM-DD" 纯日期）
    """
    if not time_range:
        time_range = "15m"

    # 简写格式: Nx (m/h/d)
    m = re.match(r"^(\d+)([mhd])$", time_range)
    if m:
        num = int(m.group(1))
        unit = m.group(2)
        now = int(time.time())
        if unit == "m":
            return (now - num * 60, now)
        elif unit == "h":
            return (now - num * 3600, now)
        elif unit == "d":
            return (now - num * 86400, now)

    # 范围格式: unix timestamp 或人类可读时间，逗号分隔
    if "," in time_range:
        parts = [p.strip() for p in time_range.split(",")]
        if len(parts) != 2 or not all(parts):
            raise ValueError(
                f"invalid time_range '{time_range}'; range must contain exactly two non-empty bounds")
        bounds = []
        for p in parts:
            if re.match(r"^\d+$", p):
                bounds.append(int(p))
            else:
                bounds.append(_parse_datetime_token(p))
        if bounds[0] > bounds[1]:
            raise ValueError("time range start must be earlier than or equal to end")
        return (bounds[0], bounds[1])

    raise ValueError(
        f"invalid time_range '{time_range}'; use '15m', '1h', '2d', "
        "'from,to' (unix timestamp), or 'YYYY-MM-DD HH:MM:SS,YYYY-MM-DD HH:MM:SS'"
    )


def get_index_summary(endpoint: str, project: str, logstore: str) -> dict:
    """通过 GetIndex 探测 logstore 索引形态（全文索引/字段索引）

    Args:
        endpoint: SLS endpoint
        project: SLS project 名
        logstore: SLS logstore 名

    Returns:
        {"exists": bool|None, "fullText": bool|None, "indexedFields": [...],
         "error": str|None}；exists=None 表示无法判定（SDK/凭据/接口异常）
    """
    summary = {"exists": None, "fullText": None, "indexedFields": [], "error": None}
    if not SDK_AVAILABLE:
        summary["error"] = "aliyun-log-python-sdk not installed"
        return summary
    try:
        client = get_log_client(endpoint)
        resp = client.get_index_config(project, logstore)
        index = resp.get_index_config()
        raw = index.to_json() if hasattr(index, "to_json") else {}
        summary["exists"] = True
        summary["fullText"] = bool(raw.get("line")) or getattr(index, "line_config", None) is not None
        keys = raw.get("keys") or {}
        if isinstance(keys, dict):
            summary["indexedFields"] = sorted(keys.keys())
        return summary
    except Exception as e:  # LogException 等 — 探测失败不应阻断查询
        msg = str(e)
        if "IndexConfigNotExist" in msg:
            summary["exists"] = False
            summary["fullText"] = False
        else:
            summary["error"] = msg[:200]
        return summary


def _empty_result_index_check(endpoint: str, project: str, logstore: str,
                              query: str, index_hint: str = "") -> tuple:
    """关键词查询返回空结果时探测索引形态，防止把"查不到"误判为"没发生"

    Args:
        endpoint: SLS endpoint
        project: SLS project 名
        logstore: SLS logstore 名
        query: 本次查询语句
        index_hint: 项目配置中预置的索引异常说明（config.indexHint），命中时直接使用

    Returns:
        (warnings 列表, indexCheck dict|None)
    """
    # 仅针对纯关键词查询；SQL 分析（含 |）与通配 * 不受索引形态影响
    query = query.strip()
    if not query or "|" in query or query == "*":
        return [], None
    if index_hint:
        return [f"0 条结果且该 logstore 已预置索引提示: {index_hint}"], None
    summary = get_index_summary(endpoint, project, logstore)
    warnings = []
    if summary["exists"] is False:
        warnings.append(
            f"logstore '{logstore}' 未建任何索引（GetIndex: IndexConfigNotExist），"
            "关键词查询恒返 0 条；请改用 SQL 全扫描 "
            "\"* | select ... where message like '%关键词%'\"，或先建索引再查"
        )
    elif summary["exists"] and summary["fullText"] is False:
        fields = ", ".join(summary["indexedFields"][:20]) or "无"
        warnings.append(
            f"logstore '{logstore}' 无全文索引（已有索引字段仅: {fields}），"
            "裸关键词全文搜索会静默返 0 条，不能据此判断'任务未执行/无数据'；"
            "请改用索引字段查询（如 level: ERROR）或 SQL 全扫描 "
            "\"* | select ... where message like '%关键词%'\""
        )
    elif summary["exists"] and summary["fullText"] is True:
        warnings.append(
            f"logstore '{logstore}' 索引形态正常，0 条结果可能是关键词分词不匹配"
            "（中文长词、驼峰类名如 MetricSyncTask 常不被分词命中）；"
            "下'未执行/无数据'结论前请用 SQL 全扫描交叉验证: "
            "\"* | select count(*) where message like '%关键词%'\""
        )
    elif summary["error"]:
        warnings.append(
            f"索引形态探测失败（{summary['error']}），0 条结果不能作为'无数据'证据"
        )
    return warnings, summary


def query_logs(endpoint: str, project: str, logstore: str,
               query: str, time_range: str = "15m",
               max_results: int = 100, offset: int = 0,
               index_hint: str = "") -> dict:
    """执行 SLS 日志查询

    Args:
        endpoint: SLS endpoint (如 cn-hangzhou.log.aliyuncs.com)
        project: SLS project 名
        logstore: SLS logstore 名
        query: 查询语句（关键词或 SQL）
        time_range: 时间范围（如 "15m", "1h", "2d" 或人类可读时间范围）
        max_results: 最大返回条数
        offset: 分页偏移
        index_hint: 项目配置预置的索引异常说明；关键词查询返空时直接作为警告

    Returns:
        查询结果 dict: {logs: [...], count: N, query: ..., timeRange: ...}；
        关键词查询返空且索引形态异常时附 warnings/indexCheck
    """
    if not SDK_AVAILABLE:
        raise RuntimeError(
            "aliyun-log-python-sdk not installed. Run: pip install aliyun-log-python-sdk"
        )

    client = get_log_client(endpoint)

    from_t, to_t = parse_time_range(time_range)

    req = GetLogsRequest(
        project=project,
        logstore=logstore,
        fromTime=from_t,
        toTime=to_t,
        query=query,
        line=max_results,
        offset=offset,
    )

    # perf 观测（L2 集成级）：单 logstore 一次 SDK 查询一条记录
    with perf_span(f"sls {project}/{logstore}", "sls_query",
                   {"endpoint": endpoint, "project": project,
                    "logstore": logstore, "query": query}) as span:
        resp = client.get_logs(req)
        logs = [log_item.get_contents() for log_item in resp.get_logs()]
        span["count"] = len(logs)

    result = {
        "logs": logs,
        "count": len(logs),
        "query": query,
        "logstore": logstore,
        "project": project,
        "endpoint": endpoint,
        "timeRange": {
            "from": from_t,
            "to": to_t,
            "human": time_range,
        },
    }

    # 空结果的关键词查询最易误判：探测索引形态并给出显式警告
    if not logs:
        warns, index_check = _empty_result_index_check(
            endpoint, project, logstore, query, index_hint
        )
        if warns:
            result["warnings"] = warns
        if index_check is not None:
            result["indexCheck"] = index_check
    return result


def query_by_config(project_config: dict, env: str, query: str,
                    time_range: str = "15m", max_results: int = 100) -> dict:
    """通过项目配置查询日志（便捷方法，支持同环境多 logstore 跨 region 合并查询）

    Args:
        project_config: 项目配置 dict（来自 config.get_project）
        env: 环境名 (daily/pre/prod)
        query: 查询语句
        time_range: 时间范围
        max_results: 最大返回（应用于每个 logstore）

    Returns:
        合并查询结果: {logs, count, byLogstore: [...], hint, ...}
    """
    envs = project_config.get("environments", {})
    resolved_env = resolve_env(project_config, env)
    env_cfg = envs.get(resolved_env)
    if not env_cfg:
        raise ValueError(
            f"environment '{env}' not configured for project; "
            f"available: {list(envs.keys())}"
        )

    # 直接从 env_cfg 提取全部启用的 SLS platform（注意：不能调 get_sls_config，
    # 它接受项目名 str，传 dict 进去会触发 unhashable type: 'dict'）
    sls_configs = get_all_sls_configs(project_config, env)
    if not sls_configs:
        raise ValueError(f"no SLS platform configured for env '{env}'")

    # 使用 queryDefaults 中的默认值
    defaults = env_cfg.get("queryDefaults", {})
    max_results = max_results or defaults.get("maxResults", 100)
    time_range = time_range or defaults.get("timeRange", "15m")

    # 逐个 logstore 查询并合并（单个 logstore 失败不阻断其它 logstore）
    merged_logs = []
    by_logstore = []
    errors = []
    merged_warnings = []
    first_meta = None
    for entry in sls_configs:
        cfg = entry["config"]
        try:
            result = query_logs(
                endpoint=cfg["endpoint"],
                project=cfg["project"],
                logstore=cfg["logstore"],
                query=query,
                time_range=time_range,
                max_results=max_results,
                index_hint=cfg.get("indexHint", ""),
            )
        except Exception as e:  # noqa: BLE001 — 跨 logstore 容错，逐个记录
            errors.append(f"{cfg['project']}/{cfg['logstore']}: {e}")
            by_logstore.append({
                "name": entry["name"],
                "project": cfg["project"],
                "logstore": cfg["logstore"],
                "endpoint": cfg["endpoint"],
                "count": 0,
                "limit": max_results,
                "truncated": False,
                "error": str(e),
            })
            continue
        if first_meta is None:
            first_meta = result
        # 逐源警告带上来源前缀后上抛，避免被消费方当成全局结论
        for w in result.get("warnings", []):
            merged_warnings.append(f"{cfg['project']}/{cfg['logstore']}: {w}")
        # 每条日志附 _source_logstore 便于区分来源 region
        for log in result["logs"]:
            log["_source_logstore"] = cfg["logstore"]
        merged_logs.extend(result["logs"])
        store_entry = {
            "name": entry["name"],
            "project": cfg["project"],
            "logstore": cfg["logstore"],
            "endpoint": cfg["endpoint"],
            "count": result["count"],
            "limit": max_results,
            "truncated": result["count"] >= max_results,
        }
        if result.get("indexCheck") is not None:
            store_entry["indexCheck"] = result["indexCheck"]
        by_logstore.append(store_entry)

    if first_meta is None:
        raise RuntimeError(
            "all configured logstores failed: " + "; ".join(errors)
        )

    merged = dict(first_meta)
    merged["logs"] = merged_logs
    merged["count"] = len(merged_logs)
    merged["byLogstore"] = by_logstore
    merged["truncatedLogstores"] = [
        {
            "name": item["name"],
            "project": item["project"],
            "logstore": item["logstore"],
            "count": item["count"],
            "limit": item["limit"],
        }
        for item in by_logstore if item.get("truncated")
    ]
    merged["truncated"] = bool(merged["truncatedLogstores"])
    # 顶层来源字段只反映第一个成功 logstore，会误导消费方；以 byLogstore 为准
    for k in ("logstore", "project", "endpoint"):
        merged.pop(k, None)
    # 逐源聚合的警告替换首个 logstore 的局部警告
    merged.pop("warnings", None)
    merged.pop("indexCheck", None)
    if merged_warnings:
        merged["warnings"] = merged_warnings
    if errors:
        merged["errors"] = errors

    # 空结果 + 多配置场景：提示跨 region 排查可能性
    if merged["count"] == 0:
        merged["hint"] = (
            "该环境所有已配置 logstore 均无结果。注意：应用日志可能在未配置的其它 region，"
            "禁止据此下'未接入'结论；先用 seek sls config 核对全部配置，"
            "并用 seek doctor 实测各 project/logstore 是否真实存在。"
        )
    return merged


# 兼容别名：存量调用方（doctor/测试）仍引用下划线名，公共化后逐步迁移
_SDK_AVAILABLE = SDK_AVAILABLE
_get_log_client = get_log_client
_parse_time_range = parse_time_range
