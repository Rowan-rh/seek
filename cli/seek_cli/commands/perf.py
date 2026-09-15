"""perf 耗时观测命令 — 聚合分析 ~/.seek/logs/perf.jsonl

seek perf report: 按时间窗聚合命令级/IO 级耗时，输出 IO 占比与优化方向 hint
seek perf clear:  清空耗时日志（与 seek errors clear 对称）
"""

import math

from seek_cli import perf_log
from seek_cli.output import success, error


def _percentile(sorted_values: list, pct: float) -> int:
    """nearest-rank 分位数：n 个样本取排序后第 ceil(pct*n) 位；样本不足时退化为最大值"""
    if not sorted_values:
        return 0
    rank = max(1, math.ceil(pct * len(sorted_values)))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def _group_entry(key: dict, durations: list, error_count: int) -> dict:
    """构造一个分组的统计条目（durations 会被原地排序）。"""
    durations.sort()
    total = sum(durations)
    entry = dict(key)
    entry.update({
        "count": len(durations),
        "errors": error_count,
        "totalMs": total,
        "avgMs": round(total / len(durations)) if durations else 0,
        "p50Ms": _percentile(durations, 0.50),
        "p95Ms": _percentile(durations, 0.95),
        "maxMs": durations[-1] if durations else 0,
    })
    return entry


def _build_hint(totals: dict, has_command_records: bool) -> str:
    """按 IO 占比输出优化方向提示（占比为嵌套区间的粗略近似，仅用于方向判断）。"""
    boundary = ("注意：IO span 嵌套于 command 区间内，占比为粗略近似"
                "（并行 IO 会低估、重叠区间会高估），仅用于方向判断。")
    if not has_command_records:
        return ("窗口内无 command 记录：检查 options.perf_log 是否开启"
                "(seek config get options.perf_log)、时间窗是否过窄"
                "(--time 7d 可扩大)。")
    share = totals["ioSharePct"]
    if share >= 60:
        direction = (f"集成 IO 占命令耗时 {share}%（高）——优先考虑 IO 并行"
                     "（跨 logstore 并行查询）与 DMS MCP server 常驻复用")
    elif share <= 25:
        direction = (f"集成 IO 占命令耗时 {share}%（低）——耗时主要在 LLM/编排轮次，"
                     "优先命令批量化（单次调用承载更多查询）")
    else:
        direction = (f"集成 IO 占命令耗时 {share}%（中等）——IO 与编排开销均衡，"
                     "结合最热命令的 p95 与最热 IO 目标判断")
    return direction + "。" + boundary


def cmd_perf_report(args) -> dict:
    """聚合分析耗时日志：命令级/IO 级分组、IO 占比与优化方向 hint"""
    time_range = getattr(args, "time", "24h") or "24h"
    keyword = getattr(args, "keyword", "") or ""
    session = getattr(args, "session", "") or ""
    try:
        records, skipped = perf_log.read_perf_records(
            time_range=time_range, keyword=keyword, session=session)
    except ValueError as e:
        return error(f"invalid --time: {e}", code="BAD_ARGUMENT")

    from seek_cli.integrations import sls_client
    from_t, to_t = sls_client.parse_time_range(time_range)

    command_groups = {}   # command 名 -> {"durations": [], "errors": n}
    io_groups = {}        # (span, command) -> 同上
    session_groups = {}   # session_id -> {"commandCount", "commandMs", "ioMs"}
    for rec in records:
        span = str(rec.get("span", ""))
        name = str(rec.get("command", ""))
        try:
            duration = int(rec.get("duration_ms", 0) or 0)
        except (TypeError, ValueError):
            duration = 0
        is_error = rec.get("status") == "error"
        if span == "command":
            group = command_groups.setdefault(name, {"durations": [], "errors": 0})
        else:
            group = io_groups.setdefault((span, name), {"durations": [], "errors": 0})
        group["durations"].append(duration)
        group["errors"] += 1 if is_error else 0
        sid = rec.get("session_id")
        if sid:
            sess = session_groups.setdefault(
                sid, {"commandCount": 0, "commandMs": 0, "ioMs": 0})
            if span == "command":
                sess["commandCount"] += 1
                sess["commandMs"] += duration
            else:
                sess["ioMs"] += duration

    commands = sorted(
        (_group_entry({"command": name}, g["durations"], g["errors"])
         for name, g in command_groups.items()),
        key=lambda e: e["totalMs"], reverse=True)
    io_spans = sorted(
        (_group_entry({"span": span, "label": label}, g["durations"], g["errors"])
         for (span, label), g in io_groups.items()),
        key=lambda e: e["totalMs"], reverse=True)

    command_ms = sum(e["totalMs"] for e in commands)
    io_ms = sum(e["totalMs"] for e in io_spans)
    totals = {
        "commandCount": sum(e["count"] for e in commands),
        "commandMs": command_ms,
        "ioCount": sum(e["count"] for e in io_spans),
        "ioMs": io_ms,
        "ioSharePct": round(io_ms * 100 / command_ms) if command_ms else 0,
        "errorCommands": sum(e["errors"] for e in commands),
        "errorIoCalls": sum(e["errors"] for e in io_spans),
    }
    hint = _build_hint(totals, bool(command_groups))

    data = {
        "window": {"from": from_t, "to": to_t, "human": time_range},
        "filters": {"keyword": keyword or None, "session": session or None},
        "totalRecords": len(records),
        "skippedCorrupt": skipped,
        "totals": totals,
        "commands": commands,
        "ioSpans": io_spans,
        "hint": hint,
    }
    if session_groups:
        data["sessions"] = sorted(
            ({"session_id": sid, **vals} for sid, vals in session_groups.items()),
            key=lambda s: s["commandMs"], reverse=True)

    if command_groups:
        message = (f"perf 报告: 窗口内 {len(records)} 条记录，"
                   f"IO 占比 {totals['ioSharePct']}%"
                   + (f"，{len(session_groups)} 个会话" if session_groups else ""))
    else:
        message = "perf 报告: 窗口内无 command 记录"
    return success(data, message=message)


def cmd_perf_clear(args) -> dict:
    """清空耗时日志"""
    cleared = perf_log.clear_perf_log()
    return success({"cleared": cleared, "file": str(perf_log._LOG_FILE)},
                   message=f"性能耗时日志已清空: {cleared} 条记录")
