"""数据库查询命令 — 双 backend：DMS MCP Server（生产/受管实例）与本地直连（日常/预发）

目标寻址优先级：--conn <profile> > --project+--env（bind 反查）> 位置参数 database_id（DMS）。
"""

import atexit
import re

from seek_cli.integrations import dms_client, db_store, db_local
from seek_cli.output import success, error
from seek_cli.settings import mask_secret

# 本地直连结果行数限制
_DEFAULT_MAX_ROWS = 500
_HARD_MAX_ROWS = 5000


_FORBIDDEN_SQL_RE = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|MERGE|REPLACE|UPSERT|DROP|ALTER|TRUNCATE|CREATE|"
    r"CALL|EXEC(?:UTE)?|GRANT|REVOKE|COMMIT|ROLLBACK|SAVEPOINT|SET|USE|"
    r"INTO\s+(?:OUTFILE|DUMPFILE)|FOR\s+UPDATE|FOR\s+SHARE|"
    r"LOCK\s+IN\s+SHARE\s+MODE)\b",
    re.IGNORECASE,
)


def _strip_sql_comments_and_literals(sql: str) -> str:
    """移除 SQL 注释和字符串字面量，供安全关键字检查使用。"""
    result = []
    index = 0
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if char in ("'", '"'):
            quote = char
            result.append("''")
            index += 1
            while index < len(sql):
                if sql[index] == "\\":
                    index += 2
                elif sql[index] == quote:
                    if index + 1 < len(sql) and sql[index + 1] == quote:
                        index += 2
                    else:
                        index += 1
                        break
                else:
                    index += 1
        elif char == "-" and next_char == "-":
            index = sql.find("\n", index)
            if index < 0:
                break
            result.append(" ")
        elif char == "#":
            index = sql.find("\n", index)
            if index < 0:
                break
            result.append(" ")
        elif char == "/" and next_char == "*":
            end = sql.find("*/", index + 2)
            if end < 0:
                return ""
            if index + 2 < len(sql) and sql[index + 2] == "!":
                result.append(" EXECUTABLE_COMMENT ")
            else:
                result.append(" ")
            index = end + 2
        else:
            result.append(char)
            index += 1
    return "".join(result)


def _validate_read_only_sql(sql: str) -> str:
    """校验 SQL 为单条无副作用的只读查询。

    Returns:
        空字符串表示合法；否则返回拒绝原因。
    """
    normalized = _strip_sql_comments_and_literals(sql).strip()
    if not normalized:
        return "SQL 不能为空"
    if "EXECUTABLE_COMMENT" in normalized:
        return "不允许使用可执行 SQL 注释"
    if ";" in normalized.rstrip(";").strip() or normalized.count(";") > 1:
        return "只允许单条 SQL 查询，不支持多语句"
    normalized = normalized.rstrip(";").strip()
    if not re.match(r"^(?:SELECT|WITH|EXPLAIN)\b", normalized, re.IGNORECASE):
        return "仅允许 SELECT、WITH 或 EXPLAIN 只读查询"
    if _FORBIDDEN_SQL_RE.search(normalized):
        return "只读查询中不允许写入、DDL、事务控制、文件导出或 FOR UPDATE"
    return ""


# ── 本地直连 backend：寻址分发与安全约束 ──────────────────────────


def _resolve_local_profile(args):
    """解析本地直连目标，返回 (name, profile) 或 None（走 DMS 路径）

    优先级：--conn > --project+--env（bind 反查）。
    与位置参数 database 同时提供时抛 ValueError（参数互斥）。
    """
    conn_name = getattr(args, "conn", None)
    project = getattr(args, "project", None)
    env = getattr(args, "env", None)
    database = getattr(args, "database", None)
    if conn_name:
        if database:
            raise ValueError("--conn 与位置参数 database(DMS) 不能同时提供")
        profile = db_store.get_connection(conn_name)
        if profile is None:
            available = ", ".join(sorted(db_store.load_connections())) or "无"
            raise db_store.DbStoreError(
                f"连接 profile '{conn_name}' 不存在（现有: {available}）")
        return conn_name, profile
    if project:
        if database:
            raise ValueError("--project/--env 与位置参数 database(DMS) 不能同时提供")
        if not env:
            raise ValueError("--project 模式需同时提供 --env")
        matches = db_store.find_by_bind(project, env)
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise db_store.DbStoreError(
                f"无 profile 绑定到 project={project} env={env}，"
                "可用 seek db conn add --project/--env 创建，或 --conn 显式指定")
        names = ", ".join(n for n, _ in matches)
        raise db_store.DbStoreError(
            f"project={project} env={env} 命中多个 profile: {names}，请用 --conn 显式指定")
    return None


def _check_prod_guard(name: str, profile: dict, args) -> str:
    """生产环境熔断：bind.env 为生产类时须显式 --i-know-this-is-prod，否则返回拒绝原因"""
    if db_store.is_prod_env(profile) and not getattr(args, "i_know_this_is_prod", False):
        return (
            f"profile '{name}' 绑定生产类环境 "
            f"({(profile.get('bind') or {}).get('env')})，本地直连默认拒绝；"
            "确需直连请加 --i-know-this-is-prod（生产优先走 DMS: seek db query <database_id>）")
    return ""


def _clamp_max_rows(value) -> int:
    """行数上限 clamp 到 [1, 5000]"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_ROWS
    return max(1, min(n, _HARD_MAX_ROWS))


def _run_local(name: str, profile: dict, action) -> dict:
    """打开本地连接执行 action(client)，统一异常转换为 error 结构"""
    client = db_local.open_client(name, profile)
    try:
        return action(client)
    except RuntimeError as e:
        msg = str(e)
        code = "DB_DRIVER_MISSING" if "PyMySQL 未安装" in msg else "DB_CONNECT_ERROR"
        return error(msg, code=code, data={"conn": name})
    except Exception as e:
        return error(f"本地直连查询失败: {e}", code="DB_ERROR", data={"conn": name})
    finally:
        client.close()


# ── conn 子命令（连接 profile 管理）──────────────────────────────


def cmd_db_conn_add(args) -> dict:
    """添加或覆盖本地连接 profile"""
    profile = {
        "type": args.type,
        "host": args.host,
        "port": args.port,
        "database": args.database,
        "user": args.user,
        "password": args.password,
    }
    if args.project or args.env:
        profile["bind"] = {"project": args.project or "", "env": args.env or ""}
    try:
        db_store.add_connection(args.name, profile)
    except db_store.DbStoreError as e:
        return error(str(e), code="DB_STORE_ERROR")
    return success({"name": args.name, "saved": True,
                    "file": str(db_store.DB_FILE)},
                   message=f"连接 profile '{args.name}' 已保存")


def cmd_db_conn_list(args) -> dict:
    """列出全部 profile（密码脱敏）"""
    try:
        conns = db_store.load_connections()
    except db_store.DbStoreError as e:
        return error(str(e), code="DB_STORE_ERROR")
    items = []
    for name, profile in conns.items():
        item = dict(profile)
        item["name"] = name
        item["password"] = mask_secret(profile.get("password", ""))
        items.append(item)
    return success({"connections": items, "count": len(items),
                    "file": str(db_store.DB_FILE)},
                   message=f"本地连接 profile: {len(items)} 个")


def cmd_db_conn_test(args) -> dict:
    """连通性测试（SELECT 1）"""
    try:
        profile = db_store.get_connection(args.name)
    except db_store.DbStoreError as e:
        return error(str(e), code="DB_STORE_ERROR")
    if profile is None:
        return error(f"连接 profile '{args.name}' 不存在",
                     code="DB_STORE_ERROR",
                     data={"available": sorted(db_store.load_connections())})
    return _run_local(args.name, profile, lambda c: success(
        c.test(), message=f"连通性正常: {args.name}"))


def cmd_db_conn_remove(args) -> dict:
    """删除 profile"""
    try:
        removed = db_store.remove_connection(args.name)
    except db_store.DbStoreError as e:
        return error(str(e), code="DB_STORE_ERROR")
    if not removed:
        return error(f"连接 profile '{args.name}' 不存在", code="DB_STORE_ERROR")
    return success({"name": args.name, "removed": True},
                   message=f"连接 profile '{args.name}' 已删除")


def cmd_db_tools(args) -> dict:
    """列出 DMS MCP 可用工具"""
    try:
        tools = dms_client.list_dms_tools()
        tool_list = [
            {"name": t.get("name", ""), "description": t.get("description", "")[:80]}
            for t in tools
        ]
        return success({"tools": tool_list, "count": len(tool_list)},
                        message=f"DMS MCP: {len(tool_list)} 个工具")
    except RuntimeError as e:
        return error(str(e), code="DMS_ERROR")


def cmd_db_search(args) -> dict:
    """搜索数据库"""
    try:
        result = dms_client.call_dms("searchDatabase", {
            "schema_name": args.keyword,
        })
        return success(result, message=f"搜索数据库: {args.keyword}")
    except RuntimeError as e:
        return error(str(e), code="DMS_ERROR")


def cmd_db_tables(args) -> dict:
    """列出数据表（DMS database_id 或本地直连 profile）"""
    try:
        local = _resolve_local_profile(args)
    except (ValueError, db_store.DbStoreError) as e:
        return error(str(e), code="BAD_ARGUMENT")
    if local:
        name, profile = local
        reason = _check_prod_guard(name, profile, args)
        if reason:
            return error(reason, code="PROD_DIRECT_CONNECT_FORBIDDEN", data={"conn": name})
        return _run_local(name, profile, lambda c: success(
            {"backend": "local", "conn": name, "tables": c.list_tables()},
            message=f"数据表: {profile['database']}"))
    if not getattr(args, "database", None):
        return error("缺少目标: 提供 database_id(DMS) 或 --conn/--project+--env(本地直连)",
                     code="BAD_ARGUMENT")
    try:
        result = dms_client.call_dms("listTables", {
            "database_id": args.database,
        })
        return success(result, message=f"数据表: {args.database}")
    except RuntimeError as e:
        return error(str(e), code="DMS_ERROR")


def cmd_db_schema(args) -> dict:
    """获取表结构（DMS database_id 或本地直连 profile）"""
    try:
        local = _resolve_local_profile(args)
    except (ValueError, db_store.DbStoreError) as e:
        return error(str(e), code="BAD_ARGUMENT")
    if local:
        name, profile = local
        # 本地模式位置参数回退：`seek db schema <table> --conn x` 时 argparse 会把
        # 唯一位置参数分给 database，此时把它当作表名使用
        table = args.table or getattr(args, "database", None)
        if not table:
            return error("缺少表名", code="BAD_ARGUMENT")
        reason = _check_prod_guard(name, profile, args)
        if reason:
            return error(reason, code="PROD_DIRECT_CONNECT_FORBIDDEN", data={"conn": name})
        return _run_local(name, profile, lambda c: success(
            {"backend": "local", "conn": name, **c.table_schema(table)},
            message=f"表结构: {profile['database']}.{table}"))
    if not getattr(args, "database", None) or not args.table:
        return error("DMS 模式需提供 database_id 与 table；本地直连用 --conn/--project+--env",
                     code="BAD_ARGUMENT")
    try:
        result = dms_client.call_dms("getTableDetailInfo", {
            "database_id": args.database,
            "table_name": args.table,
        })
        return success(result, message=f"表结构: {args.database}.{args.table}")
    except RuntimeError as e:
        return error(str(e), code="DMS_ERROR")


def cmd_db_query(args) -> dict:
    """执行只读 SQL 查询（DMS database_id 或本地直连 profile）"""
    reason = _validate_read_only_sql(args.sql)
    if reason:
        return error(reason, code="READ_ONLY_SQL_REQUIRED")
    try:
        local = _resolve_local_profile(args)
    except (ValueError, db_store.DbStoreError) as e:
        return error(str(e), code="BAD_ARGUMENT")
    if local:
        name, profile = local
        reason = _check_prod_guard(name, profile, args)
        if reason:
            return error(reason, code="PROD_DIRECT_CONNECT_FORBIDDEN", data={"conn": name})
        max_rows = _clamp_max_rows(getattr(args, "max", _DEFAULT_MAX_ROWS))
        return _run_local(name, profile, lambda c: success(
            {"backend": "local", "conn": name, **c.query(args.sql, max_rows)},
            message="只读 SQL 查询完成(本地直连)"))
    if not getattr(args, "database", None):
        return error("缺少目标: 提供 database_id(DMS) 或 --conn/--project+--env(本地直连)",
                     code="BAD_ARGUMENT")
    try:
        result = dms_client.call_dms("executeScript", {
            "database_id": args.database,
            "script": args.sql,
        })
        return success(result, message="只读 SQL 查询完成")
    except RuntimeError as e:
        msg = str(e)
        hint = None
        # 连接失败类错误：附 fallback 指引（DMS 元数据含 owner，可找人开通权限/代查）
        if any(k in msg for k in ("无法连接", "连接失败", "connect", "Connect", "connection")):
            hint = (
                "数据库实例连接失败时的 fallback：1) seek db search <库名关键词> "
                "重新确认 database_id 和实例归属；2) 返回的 DMS 元数据中含 owner 字段，"
                "可联系 owner 开通权限或协助查询。"
            )
        return error(msg, code="DMS_ERROR",
                     data={"database_id": args.database, "fallback_hint": hint} if hint
                     else {"database_id": args.database})


# 确保进程退出时关闭 DMS MCP 连接
atexit.register(dms_client.close_dms)
