"""seek doctor — 配置体检命令

校验所有项目配置的 SLS 条目：
1. 结构完整性（endpoint/project/logstore 必填）
2. 实测存在性（用 aliyun-log SDK 检查 project 下 logstore 是否真实存在）
3. 活性检查（可选，--liveness-window）：窗口内日志条数为 0 标记 stale，
   提前暴露"配置/文档还在指向、但实际已停写"的失效 logstore

背景：projects.json 是人工维护的，条目可能指向不存在的 project/logstore
（如 logstore 错挂在其它 region 的 project 下），也可能指向结构存在但
早已停写的 logstore（如 SLS appender 被下线）。跑一次 doctor 可提前发现。
"""

from seek_cli import config
from seek_cli.output import success, error


def _live_check(endpoint: str, project: str, logstore: str) -> dict:
    """实测 SLS project/logstore 是否存在

    Returns:
        {"status": "ok"|"not_found"|"error"|"skipped", "detail": str}
    """
    try:
        from seek_cli.integrations import sls_client
        if not sls_client.SDK_AVAILABLE:
            return {"status": "skipped", "detail": "aliyun-log-python-sdk 未安装"}
        client = sls_client.get_log_client(endpoint)
    except RuntimeError as e:
        return {"status": "skipped",
                "detail": f"无凭据/SDK不可用: {e}（可用 seek config set sls.access_key_id ... 配置凭据）"}

    try:
        from aliyun.log import ListLogstoresRequest
        resp = client.list_logstores(ListLogstoresRequest(project=project))
        stores = resp.get_logstores()
        if logstore in stores:
            return {"status": "ok", "detail": f"logstore 存在于 {project}"}
        return {
            "status": "not_found",
            "detail": f"project '{project}' 存在但无 logstore '{logstore}'"
                      f"（现有: {', '.join(stores[:10]) or '空'}...）— 检查是否错挂 region",
        }
    except Exception as e:  # LogException 等
        msg = str(e)
        if "ProjectNotExist" in msg:
            return {"status": "not_found", "detail": f"project '{project}' 不存在于 {endpoint}"}
        return {"status": "error", "detail": msg[:200]}


def _liveness_check(endpoint: str, project: str, logstore: str, window: str) -> dict:
    """统计窗口内日志条数，判定 logstore 是否仍在写入

    Args:
        endpoint: SLS endpoint
        project: SLS project 名
        logstore: SLS logstore 名
        window: 时间窗口（如 "30d"、"24h"）

    Returns:
        {"status": "active"|"stale"|"skipped"|"error", "count": int|None, "detail": str}
    """
    try:
        from seek_cli.integrations import sls_client
        if not sls_client.SDK_AVAILABLE:
            return {"status": "skipped", "count": None,
                    "detail": "aliyun-log-python-sdk 未安装，跳过活性检查"}
        client = sls_client.get_log_client(endpoint)
        from_t, to_t = sls_client.parse_time_range(window)
    except RuntimeError as e:
        return {"status": "skipped", "count": None,
                "detail": f"无凭据/SDK不可用: {e}（可用 seek config set sls.access_key_id ... 配置凭据）"}

    try:
        from aliyun.log import GetHistogramsRequest
        req = GetHistogramsRequest(project, logstore, fromTime=from_t, toTime=to_t)
        resp = client.get_histograms(req)
        count = resp.get_total_count()
        if count == 0:
            return {"status": "stale", "count": 0,
                    "detail": f"近 {window} 内 0 条日志 — logstore 已失效(stale)，"
                              "检查应用 appender 是否停写或已切换到其它 logstore"}
        return {"status": "active", "count": count,
                "detail": f"近 {window} 内 {count} 条日志"}
    except Exception as e:  # LogException 等
        return {"status": "error", "count": None, "detail": str(e)[:200]}


def _db_conn_checks(live: bool) -> list:
    """校验本地直连 profile（~/.seek/config/db.json）

    结构校验始终执行；连通性测试仅在 live 时执行。
    连通失败记 warn、驱动缺失记 skipped，均不计入 issues/skipped 计数，
    避免 db 直连（日常环境可选能力）阻断整体体检。
    """
    from seek_cli.integrations import db_store
    checks = []
    try:
        conns = db_store.load_connections()
    except db_store.DbStoreError as e:
        checks.append({"section": "db", "name": "-", "status": "invalid",
                       "detail": f"db.json 结构非法: {e}"})
        return checks
    if not conns:
        checks.append({"section": "db", "name": "-", "status": "info",
                       "detail": "未配置本地直连 profile（seek db conn add 可创建）"})
        return checks
    for name, profile in conns.items():
        entry = {"section": "db", "name": name,
                 "target": f"{profile.get('host')}:{profile.get('port')}/{profile.get('database')}"}
        missing = [k for k in ("type", "host", "port", "database", "user", "password")
                   if not profile.get(k)]
        if missing:
            entry.update(status="invalid", detail=f"缺少必填字段: {missing}")
            checks.append(entry)
            continue
        if not live:
            entry.update(status="structure_ok", detail="结构完整（未实测连通性）")
            checks.append(entry)
            continue
        from seek_cli.integrations import db_local
        client = db_local.open_client(name, profile)
        try:
            client.test()
            entry.update(status="ok", detail="连通性正常")
        except RuntimeError as e:
            msg = str(e)
            if "PyMySQL 未安装" in msg:
                entry.update(status="skipped", detail=msg)
            else:
                entry.update(status="warn", detail=f"连通性失败: {msg[:200]}")
        except Exception as e:
            entry.update(status="warn", detail=f"连通性失败: {str(e)[:200]}")
        finally:
            client.close()
        checks.append(entry)
    return checks


def cmd_doctor(args) -> dict:
    """体检所有项目配置"""
    live = not getattr(args, "no_live", False)
    liveness_window = (getattr(args, "liveness_window", "") or "").strip()
    if liveness_window:
        from seek_cli.integrations import sls_client
        try:
            sls_client.parse_time_range(liveness_window)
        except ValueError as e:
            return error(f"invalid --liveness-window: {e}", code="BAD_ARGUMENT")
        if not live:
            return error("--liveness-window requires live checks (remove --no-live)",
                         code="BAD_ARGUMENT")
    checks = []
    issues = 0
    skipped = 0

    for proj in config.list_projects():
        name = proj["name"]
        full = config.get_project(name)
        envs = full.get("environments", {})
        if not envs:
            checks.append({
                "project": name, "env": "-", "name": "-",
                "status": "info", "detail": "未配置任何环境（无 SLS 集成）",
            })
            continue
        for env_name, env_cfg in envs.items():
            platforms = env_cfg.get("platforms", [])
            sls_plats = [p for p in platforms if p.get("type") == "sls"]
            if not sls_plats:
                checks.append({
                    "project": name, "env": env_name, "name": "-",
                    "status": "warn", "detail": "该环境无 SLS platform 配置",
                })
                issues += 1
                continue
            for plat in sls_plats:
                if not plat.get("enabled", True):
                    continue
                cfg = plat.get("config", {})
                entry = {
                    "project": name,
                    "env": env_name,
                    "name": plat.get("name", ""),
                    "endpoint": cfg.get("endpoint", ""),
                    "sls_project": cfg.get("project", ""),
                    "logstore": cfg.get("logstore", ""),
                }
                # 1. 结构校验
                missing = [k for k in ("endpoint", "project", "logstore") if not cfg.get(k)]
                if missing:
                    entry["status"] = "invalid"
                    entry["detail"] = f"缺少必填字段: {missing}"
                    issues += 1
                    checks.append(entry)
                    continue
                # 2. 实测存在性
                if live:
                    result = _live_check(cfg["endpoint"], cfg["project"], cfg["logstore"])
                    entry["status"] = result["status"]
                    entry["detail"] = result["detail"]
                    if result["status"] in ("not_found", "error"):
                        issues += 1
                    elif result["status"] == "skipped":
                        skipped += 1
                    # 3. 活性检查（仅对存在性通过的 logstore）
                    elif liveness_window and result["status"] == "ok":
                        lv = _liveness_check(cfg["endpoint"], cfg["project"],
                                             cfg["logstore"], liveness_window)
                        entry["liveness"] = {"window": liveness_window,
                                             "status": lv["status"], "count": lv["count"]}
                        if lv["status"] == "stale":
                            entry["status"] = "stale"
                            entry["detail"] += f"；{lv['detail']}"
                            issues += 1
                        elif lv["status"] in ("skipped", "error"):
                            entry["liveness"]["detail"] = lv["detail"]
                            skipped += 1
                else:
                    entry["status"] = "structure_ok"
                    entry["detail"] = "结构完整（未实测，去掉 --no-live 可实测）"
                checks.append(entry)

    # 本地直连 profile 检查（失败仅 warn，不计入 issues，不阻断整体体检）
    db_checks = _db_conn_checks(live)
    checks.extend(db_checks)

    ok = issues == 0 and skipped == 0
    data = {
        "checks": checks,
        "total": len(checks),
        "issues": issues,
        "skipped": skipped,
        "live": live,
        "livenessWindow": liveness_window or None,
    }
    if ok:
        return success(data, message=f"配置体检通过: {len(checks)} 项检查无异常")
    if issues:
        return error(
            f"配置体检发现 {issues} 个问题，详见 data.checks",
            code="DOCTOR_ISSUES", data=data,
        )
    return error(
        f"配置体检未完成: {skipped} 项 live 检查被跳过，详见 data.checks",
        code="DOCTOR_INCOMPLETE", data=data,
    )
