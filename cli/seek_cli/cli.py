#!/usr/bin/env python3
"""seek CLI 主入口 — AI agent 排查编排工具

所有命令默认输出 JSON（供 agent 解析），加 --format text 可切换人可读格式。

用法:
    seek project list
    seek project show <name>
    seek project add <name> [--desc ...] [--repo ...] [--a1-app ...] \
        [--sls-daily endpoint/project/logstore] [--sls-pre ...] [--sls-prod ...]

    seek deploy branch <project>
    seek deploy info <project>
    seek deploy orders <project>
    seek deploy order <order_id>
    seek deploy changes <project>

    seek sls query <project> --env <env> --query <sql> [--time 15m] [--max 100]
    seek sls query <project> --env <env> --query-file q.sql [--time "2026-08-03 00:00:00,2026-08-10 00:00:00"]
    seek sls logs <project> --env <env> [--level ERROR] [--keyword xxx] [--trace-id xxx]
    seek sls config <project> [--env <env>]

    seek trace call-chain <project>
    seek trace query <project> --env <env> --trace-id <id> [--time 1h]
    seek trace topology

    seek chain list
    seek chain show <name>
    seek chain start <name> [--project <project>] [--problem <description>] [--context '{"flow_id":"FLOW-xxx"}']
    seek chain provide <session> --inputs '{"flow_id":"FLOW-xxx"}'   # 补注入首步输入
    seek chain status <session>
    seek chain step <session>
    seek chain complete <session> [--summary ...] [--outputs '{"key":"val"}']
    seek chain validate <session> --step <N>
    seek chain amend <session> --step <N> [--summary ...] [--outputs '{...}']
    seek chain context <session>
    seek chain report <session> --slug "batch-560d6f3c-objectlist-empty"  # 生成报告文件名与头部(不落盘)
    seek chain sessions [--limit 20]

    seek dingtalk groups <query>
    seek dingtalk messages --group <id> --time "yyyy-MM-dd HH:mm:ss" [--direction newer] [--limit 50]
    seek dingtalk messages --user <userId> --time "..."
    seek dingtalk search <query> [--group <id>] [--sender-ids <ids>] [--at-me]
    seek dingtalk unread
    seek dingtalk send --group <id> --text "..." [--title "..."]
    seek dingtalk send --user <userId> --text "..."
    seek dingtalk contact <query>
    seek dingtalk members --group <id>
    seek dingtalk doc-read <url>

    seek ticket search [--keyword xxx] [--status open] [--product QT] [--page 1]
    seek ticket detail <flowId> [--user-id ...] [--dept ...]
    seek ticket orders <flowId>
    seek ticket lifecycle <flowId>
    seek ticket history <title>
    seek ticket analyze <flowId> [--user-id ...] [--dept ...]

    seek notify query <queryId>    # 通知触达查询(roar noti-query, 仅近7天)

    seek db query <database_id> --sql "..."             # DMS 路径(生产/受管实例)
    seek db query --conn <profile> --sql "..."          # 本地直连(日常/预发)
    seek db query --project <p> --env daily --sql "..." # 按 bind 反查 profile 直连
    seek db conn add <name> --type mysql --host H --port 3306 --database D \
        --user U --password 'env:VAR' [--project <p> --env daily]
    seek db conn list | test <name> | remove <name>

    seek config show               # 配置总览(生效值+来源, secret脱敏)
    seek config get <key>          # 读取配置项(如 hosts.roar)
    seek config set <key> <value>  # 写入 ${SEEK_HOME:-~/.seek}/config/seek.json
    seek config unset <key>        # 删除配置项
    seek config path               # 配置目录与文件状态
"""

import argparse
import sys
import time
import warnings

# 抑制 urllib3 在 LibreSSL 环境下的无害警告
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")

from seek_cli.output import print_result, success, error
from seek_cli.commands import project, deploy, sls, trace, chain, dingtalk, ticket, capabilities, db, skill, version_cmd, doctor, notify, config_cmd, perf, harness, init_cmd
from seek_cli import error_log
from seek_cli import perf_log
from seek_cli import config
from seek_cli import __version__
from seek_cli.paths import seek_path


def _add_global_args(p: argparse.ArgumentParser, root: bool = False) -> None:
    """添加全局参数，子 parser 不覆盖父 parser 已解析的值。"""
    p.add_argument("--format", choices=["json", "text"],
                   default="json" if root else argparse.SUPPRESS,
                   help="输出格式: json(默认,供agent) | text(供人阅读)")


class _JsonArgumentParser(argparse.ArgumentParser):
    """参数解析失败时：usage 走 stderr，JSON 错误走 stdout，退出码非零。

    保证管道编排下 stdout 恒为可解析 JSON（解析错误也不例外），
    下游 json.load 不会因 argparse 把错误打到 stderr 而 EOF。
    """

    def error(self, message):
        self.print_usage(sys.stderr)
        result = error(f"argument error: {message}", code="ARGPARSE_ERROR",
                       data={"hint": "run with --help to see valid arguments"})
        print_result(result, fmt="json")
        sys.exit(2)


def _build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器"""
    parser = _JsonArgumentParser(
        prog="seek",
        description="AI agent 排查编排 CLI — 查询部署信息/SLS日志/调用链路, 编排排查流程",
    )
    _add_global_args(parser, root=True)
    sub = parser.add_subparsers(dest="command", help="子命令", required=True)

    # ── capabilities (能力发现) ──
    cap = sub.add_parser("capabilities", help="输出所有命令的能力清单(JSON schema)")
    _add_global_args(cap)
    cap.set_defaults(func=capabilities.cmd_capabilities)

    # ── version (版本) ──
    ver = sub.add_parser("version", help="输出版本和变更记录")
    _add_global_args(ver)
    ver.set_defaults(func=version_cmd.cmd_version)

    # ── init (首次接入向导) ──
    init_parser = sub.add_parser("init", help="初始化向导: 检查并引导配置 A1/DMS MCP/SLS")
    init_parser.add_argument("--verify", action="store_true",
                             help="显式验证 A1 登录态和 DMS MCP 工具发现")
    _add_global_args(init_parser)
    init_parser.set_defaults(func=init_cmd.cmd_init)

    # ── doctor (配置体检) ──
    doc = sub.add_parser("doctor", help="配置体检: 校验所有 SLS 配置的结构与真实存在性")
    doc.add_argument("--no-live", dest="no_live", action="store_true",
                     help="只做结构校验，不调 SLS API 实测")
    doc.add_argument("--liveness-window", dest="liveness_window", default="",
                     help="logstore 活性检查窗口(如 30d/7d/24h)：窗口内 0 条日志标记 stale(失效)")
    _add_global_args(doc)
    doc.set_defaults(func=doctor.cmd_doctor)

    # ── harness (Agent Harness 离线就绪检查) ──
    harness_cmd = sub.add_parser("harness", help="Agent Harness 离线就绪检查")
    harness_sub = harness_cmd.add_subparsers(dest="subcommand", required=True)
    _add_global_args(harness_cmd)

    harness_check = harness_sub.add_parser("check", help="检查存储、资源、版本和外部依赖，不访问网络")
    _add_global_args(harness_check)
    harness_check.set_defaults(func=harness.cmd_harness_check)

    harness_eval = harness_sub.add_parser("evaluate", help="运行协议、轨迹和报告三层 Agent 场景评测")
    harness_eval.add_argument("--scenarios", required=True, help="版本化场景 JSON 文件")
    harness_eval.add_argument("--agent-command", dest="agent_command",
                              help="真实 Agent runner 命令；省略时使用 replay")
    harness_eval.add_argument("--timeout", type=int, default=120, help="每个 live 场景的超时秒数")
    harness_eval.add_argument("--scenario", action="append", dest="scenario_ids",
                              help="仅运行指定场景，可重复")
    _add_global_args(harness_eval)
    harness_eval.set_defaults(func=harness.cmd_harness_evaluate)

    # ── config (统一配置管理) ──
    cfg = sub.add_parser("config", help="统一配置管理 (${SEEK_HOME:-~/.seek}/config/seek.json)")
    cfg_sub = cfg.add_subparsers(dest="subcommand", required=True)
    _add_global_args(cfg)

    cfg_show = cfg_sub.add_parser("show", help="聚合展示全部配置项的生效值与来源(secret脱敏)")
    _add_global_args(cfg_show)
    cfg_show.set_defaults(func=config_cmd.cmd_config_show)

    cfg_get = cfg_sub.add_parser("get", help="读取单个配置项")
    cfg_get.add_argument("key", help="配置键(如 hosts.roar / sls.access_key_id)")
    _add_global_args(cfg_get)
    cfg_get.set_defaults(func=config_cmd.cmd_config_get)

    cfg_set = cfg_sub.add_parser("set", help="写入配置项到 seek.json")
    cfg_set.add_argument("key", help="配置键")
    cfg_set.add_argument("value", help="配置值")
    _add_global_args(cfg_set)
    cfg_set.set_defaults(func=config_cmd.cmd_config_set)

    cfg_unset = cfg_sub.add_parser("unset", help="删除配置项(回退到环境变量/旧文件/默认值)")
    cfg_unset.add_argument("key", help="配置键")
    _add_global_args(cfg_unset)
    cfg_unset.set_defaults(func=config_cmd.cmd_config_unset)

    cfg_path = cfg_sub.add_parser("path", help="输出配置目录与各文件存在状态")
    _add_global_args(cfg_path)
    cfg_path.set_defaults(func=config_cmd.cmd_config_path)

    # ── project ──
    p = sub.add_parser("project", help="项目管理")
    p_sub = p.add_subparsers(dest="subcommand", required=True)
    _add_global_args(p)

    p_list = p_sub.add_parser("list", help="列出所有项目")
    _add_global_args(p_list)
    p_list.set_defaults(func=project.cmd_project_list)

    p_show = p_sub.add_parser("show", help="查看项目详情")
    p_show.add_argument("name", help="项目名")
    _add_global_args(p_show)
    p_show.set_defaults(func=project.cmd_project_show)

    p_add = p_sub.add_parser("add", help="添加或更新项目配置")
    p_add.add_argument("name", help="项目名")
    p_add.add_argument("--desc", help="项目描述")
    p_add.add_argument("--repo", help="本地代码仓库路径")
    p_add.add_argument("--a1-app", help="Aone 平台应用名")
    p_add.add_argument("--sls-daily", help="日常环境 SLS: endpoint/project/logstore")
    p_add.add_argument("--sls-pre", help="预发环境 SLS: endpoint/project/logstore")
    p_add.add_argument("--sls-prod", help="生产环境 SLS: endpoint/project/logstore")
    _add_global_args(p_add)
    p_add.set_defaults(func=project.cmd_project_add)

    # ── deploy ──
    d = sub.add_parser("deploy", help="部署信息查询 (A1 CLI 集成)")
    d_sub = d.add_subparsers(dest="subcommand", required=True)
    _add_global_args(d)

    d_branch = d_sub.add_parser("branch", help="查询当前部署分支")
    d_branch.add_argument("project", help="项目名")
    _add_global_args(d_branch)
    d_branch.set_defaults(func=deploy.cmd_deploy_branch)

    d_info = d_sub.add_parser("info", help="查询应用详情")
    d_info.add_argument("project", help="项目名")
    _add_global_args(d_info)
    d_info.set_defaults(func=deploy.cmd_deploy_info)

    d_orders = d_sub.add_parser("orders", help="查询部署单列表")
    d_orders.add_argument("project", help="项目名")
    _add_global_args(d_orders)
    d_orders.set_defaults(func=deploy.cmd_deploy_orders)

    d_order = d_sub.add_parser("order", help="查询单个部署单详情")
    d_order.add_argument("order_id", help="部署单 ID")
    _add_global_args(d_order)
    d_order.set_defaults(func=deploy.cmd_deploy_order)

    d_changes = d_sub.add_parser("changes", help="查询变更单列表")
    d_changes.add_argument("project", help="项目名")
    _add_global_args(d_changes)
    d_changes.set_defaults(func=deploy.cmd_deploy_changes)

    d_env = d_sub.add_parser("env", help="查询指定环境的部署信息(pipeline+分支+变更)")
    d_env.add_argument("project", help="项目名")
    d_env.add_argument("--env", default="日常",
                       help="环境关键词: 日常/预发/正式，或别名 daily/pre/prod/生产/online 等 (默认: 日常)")
    _add_global_args(d_env)
    d_env.set_defaults(func=deploy.cmd_deploy_env)

    # ── sls ──
    s = sub.add_parser("sls", help="SLS 日志查询")
    s_sub = s.add_subparsers(dest="subcommand", required=True)
    _add_global_args(s)

    s_query = s_sub.add_parser("query", help="执行 SLS 查询（项目配置或裸目标直查）")
    s_query.add_argument("project", nargs="?", help="项目名；直查时省略")
    s_query.add_argument("--env", help="环境: daily/pre/prod；项目配置模式必填")
    s_query.add_argument("--endpoint", help="SLS endpoint；与 --sls-project/--logstore 一起启用直查")
    s_query.add_argument("--sls-project", dest="sls_project", help="SLS project；直查模式必填")
    s_query.add_argument("--logstore", help="SLS logstore；直查模式必填")
    s_query.add_argument("--query", help="SLS 查询语句(SQL或关键词)；与 --query-file 二选一")
    s_query.add_argument("--query-file", dest="query_file",
                         help="从文件读取查询语句('-' 表示 stdin)，规避中文/引号嵌套的 shell 转义")
    s_query.add_argument("--time", default="15m",
                         help="时间范围: 15m/1h/1d、from,to 时间戳或 'YYYY-MM-DD HH:MM:SS,YYYY-MM-DD HH:MM:SS'")
    s_query.add_argument("--max", "--limit", dest="max", type=int, default=100,
                         help="每个查询目标最大返回条数: 1-1000 (--limit 为别名)")
    s_query.add_argument("--sort", choices=["asc", "desc"], help="按日志时间排序")
    _add_global_args(s_query)
    s_query.set_defaults(func=sls.cmd_sls_query)

    s_logs = s_sub.add_parser("logs", help="快捷日志查询")
    s_logs.add_argument("project", help="项目名")
    s_logs.add_argument("--env", required=True, help="环境: daily/pre/prod")
    s_logs.add_argument("--level", help="日志级别: ERROR/WARN/INFO")
    s_logs.add_argument("--keyword", help="关键词")
    s_logs.add_argument("--trace-id", help="traceId")
    s_logs.add_argument("--time", default="15m", help="时间范围")
    s_logs.add_argument("--max", "--limit", dest="max", type=int, default=100,
                        help="每个查询目标最大返回条数: 1-1000 (--limit 为别名)")
    _add_global_args(s_logs)
    s_logs.set_defaults(func=sls.cmd_sls_logs)

    s_cfg = s_sub.add_parser("config", help="查看 SLS 配置")
    s_cfg.add_argument("project", help="项目名")
    s_cfg.add_argument("--env", help="指定环境")
    _add_global_args(s_cfg)
    s_cfg.set_defaults(func=sls.cmd_sls_config)

    # ── trace ──
    t = sub.add_parser("trace", help="调用链路查询")
    t_sub = t.add_subparsers(dest="subcommand", required=True)
    _add_global_args(t)

    t_chain = t_sub.add_parser("call-chain", help="查看调用链路文档")
    t_chain.add_argument("project", help="项目名")
    _add_global_args(t_chain)
    t_chain.set_defaults(func=trace.cmd_trace_call_chain)

    t_query = t_sub.add_parser("query", help="通过 traceId 查询 trace")
    t_query.add_argument("project", help="项目名")
    t_query.add_argument("--env", required=True, help="环境")
    t_query.add_argument("--trace-id", required=True, help="traceId")
    t_query.add_argument("--time", default="1h", help="时间范围")
    t_query.add_argument("--max", "--limit", dest="max", type=int, default=50,
                         help="最大返回 (--limit 为别名)")
    _add_global_args(t_query)
    t_query.set_defaults(func=trace.cmd_trace_query)

    t_topo = t_sub.add_parser("topology", help="查看服务拓扑关系")
    _add_global_args(t_topo)
    t_topo.set_defaults(func=trace.cmd_trace_topology)

    # ── chain ──
    c = sub.add_parser("chain", help="排查链路管理")
    c_sub = c.add_subparsers(dest="subcommand", required=True)
    _add_global_args(c)

    c_list = c_sub.add_parser("list", help="列出排查链路")
    _add_global_args(c_list)
    c_list.set_defaults(func=chain.cmd_chain_list)

    c_show = c_sub.add_parser("show", help="查看链路详情")
    c_show.add_argument("name", help="链路名")
    _add_global_args(c_show)
    c_show.set_defaults(func=chain.cmd_chain_show)

    c_start = c_sub.add_parser("start", help="开始排查会话")
    c_start.add_argument("name", help="链路名")
    c_start.add_argument("--project", help="目标项目")
    c_start.add_argument("--problem", help="问题描述")
    c_start.add_argument("--context", help='初始上下文(JSON对象): 用户调用时已知的输入, 如 \'{"flow_id":"FLOW-xxx"}\'')
    _add_global_args(c_start)
    c_start.set_defaults(func=chain.cmd_chain_start)

    c_provide = c_sub.add_parser("provide", help="向已建会话补注入首步输入(平铺merge进context)")
    c_provide.add_argument("session", help="会话 ID")
    c_provide.add_argument("--inputs", required=True,
                           help='补注入的输入(JSON对象), 如 \'{"flow_id":"FLOW-xxx"}\'')
    _add_global_args(c_provide)
    c_provide.set_defaults(func=chain.cmd_chain_provide)

    c_status = c_sub.add_parser("status", help="查看会话状态")
    c_status.add_argument("session", help="会话 ID")
    _add_global_args(c_status)
    c_status.set_defaults(func=chain.cmd_chain_status)

    c_step = c_sub.add_parser("step", help="查看当前步骤")
    c_step.add_argument("session", help="会话 ID")
    _add_global_args(c_step)
    c_step.set_defaults(func=chain.cmd_chain_step)

    c_complete = c_sub.add_parser("complete", help="完成当前步骤")
    c_complete.add_argument("session", help="会话 ID")
    c_complete.add_argument("--summary", help="步骤执行摘要")
    c_complete.add_argument("--outputs", help="步骤输出(JSON字符串)")
    c_complete.add_argument("--evidence", help="结构化证据(JSON对象: status/sources/boundary/reason)")
    c_complete.add_argument("--token-usage", dest="token_usage",
                            help="本步骤 token 使用量(JSON对象，仅统计不参与评分)")
    _add_global_args(c_complete)
    c_complete.set_defaults(func=chain.cmd_chain_complete)

    c_validate = c_sub.add_parser("validate", help="验证步骤约束")
    c_validate.add_argument("session", help="会话 ID")
    c_validate.add_argument("--step", type=int, required=True, help="目标步骤号")
    _add_global_args(c_validate)
    c_validate.set_defaults(func=chain.cmd_chain_validate)

    c_amend = c_sub.add_parser("amend", help="回填更正已完成步骤(追加correction不覆盖)")
    c_amend.add_argument("session", help="会话 ID")
    c_amend.add_argument("--step", type=int, required=True, help="要更正的步骤号")
    c_amend.add_argument("--summary", help="更正说明(何时/因何/更正了什么)")
    c_amend.add_argument("--outputs", help="更正后的输出(JSON字符串, merge进该步骤上下文)")
    c_amend.add_argument("--evidence", help="更正后的结构化证据(JSON对象)")
    _add_global_args(c_amend)
    c_amend.set_defaults(func=chain.cmd_chain_amend)

    c_ctx = c_sub.add_parser("context", help="获取排查上下文")
    c_ctx.add_argument("session", help="会话 ID")
    _add_global_args(c_ctx)
    c_ctx.set_defaults(func=chain.cmd_chain_context)

    c_report = c_sub.add_parser("report", help="生成报告文件名与模板头部(completed 会话, 不落盘)")
    c_report.add_argument("session", help="会话 ID")
    c_report.add_argument("--slug", required=True,
                          help="文件名语义段: 场景-业务ID片段-现象(如 batch-560d6f3c-objectlist-empty)；"
                               "CLI 自动拼接 seek-report-<产出日期>- 前缀与 .md 后缀")
    _add_global_args(c_report)
    c_report.set_defaults(func=chain.cmd_chain_report)

    c_usage = c_sub.add_parser("usage", help="汇总会话 token 使用量(仅统计，不参与评分)")
    c_usage.add_argument("session", help="会话 ID")
    _add_global_args(c_usage)
    c_usage.set_defaults(func=chain.cmd_chain_usage)

    c_sessions = c_sub.add_parser("sessions", help="列出最近的排查会话")
    c_sessions.add_argument("--limit", type=int, default=20, help="返回数量")
    _add_global_args(c_sessions)
    c_sessions.set_defaults(func=chain.cmd_chain_sessions)

    # ── dingtalk ──
    dt = sub.add_parser("dingtalk", help="钉钉集成 (dws CLI): 聊天/文档/通讯录")
    dt_sub = dt.add_subparsers(dest="subcommand", required=True)
    _add_global_args(dt)

    # 群聊搜索
    dt_groups = dt_sub.add_parser("groups", help="搜索群聊")
    dt_groups.add_argument("query", help="群名关键词")
    _add_global_args(dt_groups)
    dt_groups.set_defaults(func=dingtalk.cmd_dingtalk_groups)

    # 拉取会话消息
    dt_msgs = dt_sub.add_parser("messages", help="拉取会话消息(群聊/单聊)")
    dt_msgs.add_argument("--group", help="群聊 openConversationId")
    dt_msgs.add_argument("--user", help="单聊用户 userId")
    dt_msgs.add_argument("--open-dingtalk-id", dest="open_dingtalk_id", help="单聊用户 openDingTalkId")
    dt_msgs.add_argument("--time", required=True, help='开始时间: "yyyy-MM-dd HH:mm:ss"')
    dt_msgs.add_argument("--direction", default="newer", help="newer=往现在拉 / older=往以前拉")
    dt_msgs.add_argument("--limit", type=int, default=50, help="返回数量")
    _add_global_args(dt_msgs)
    dt_msgs.set_defaults(func=dingtalk.cmd_dingtalk_messages)

    # 搜索消息
    dt_search = dt_sub.add_parser("search", help="多维度搜索消息")
    dt_search.add_argument("query", help="搜索关键词")
    dt_search.add_argument("--group", help="指定会话 openConversationId")
    dt_search.add_argument("--sender-ids", dest="sender_ids", help="发送者 openDingTalkId 列表")
    dt_search.add_argument("--time-from", dest="time_from", help="开始时间")
    dt_search.add_argument("--time-to", dest="time_to", help="结束时间")
    dt_search.add_argument("--at-me", dest="at_me", action="store_true", help="只搜@我的消息")
    dt_search.add_argument("--limit", type=int, default=50, help="返回数量")
    _add_global_args(dt_search)
    dt_search.set_defaults(func=dingtalk.cmd_dingtalk_search_messages)

    # 未读会话
    dt_unread = dt_sub.add_parser("unread", help="获取未读会话列表")
    _add_global_args(dt_unread)
    dt_unread.set_defaults(func=dingtalk.cmd_dingtalk_unread)

    # 发送消息
    dt_send = dt_sub.add_parser("send", help="发送消息(群聊/单聊)")
    dt_send.add_argument("--group", help="群聊 openConversationId")
    dt_send.add_argument("--user", help="单聊用户 userId")
    dt_send.add_argument("--open-dingtalk-id", dest="open_dingtalk_id", help="单聊用户 openDingTalkId")
    dt_send.add_argument("--text", required=True, help="消息内容")
    dt_send.add_argument("--title", help="消息标题")
    _add_global_args(dt_send)
    dt_send.set_defaults(func=dingtalk.cmd_dingtalk_send)

    # 搜索联系人
    dt_contact = dt_sub.add_parser("contact", help="搜索联系人")
    dt_contact.add_argument("query", help="姓名/花名关键词")
    _add_global_args(dt_contact)
    dt_contact.set_defaults(func=dingtalk.cmd_dingtalk_contact)

    # 群成员
    dt_members = dt_sub.add_parser("members", help="查看群成员列表")
    dt_members.add_argument("--group", required=True, help="群 openConversationId")
    _add_global_args(dt_members)
    dt_members.set_defaults(func=dingtalk.cmd_dingtalk_members)

    # 读取钉钉文档
    dt_doc = dt_sub.add_parser("doc-read", help="读取钉钉文档")
    dt_doc.add_argument("url", help="钉钉文档链接")
    _add_global_args(dt_doc)
    dt_doc.set_defaults(func=dingtalk.cmd_dingtalk_doc_read)

    # ── ticket (云网络工单) ──
    tk = sub.add_parser("ticket", help="云网络工单查询 (qt-expert API)")
    tk_sub = tk.add_subparsers(dest="subcommand", required=True)
    _add_global_args(tk)

    # 搜索服务单
    tk_search = tk_sub.add_parser("search", help="搜索云网络服务单")
    tk_search.add_argument("--keyword", help="标题关键词")
    tk_search.add_argument("--flow-type", dest="flow_type", default="afterSale", help="类型: afterSale/bigCustomer/yidong")
    tk_search.add_argument("--status", help="状态过滤")
    tk_search.add_argument("--product", help="产品过滤")
    tk_search.add_argument("--page", type=int, default=1, help="页码")
    tk_search.add_argument("--page-size", dest="page_size", type=int, default=20, help="每页数量")
    _add_global_args(tk_search)
    tk_search.set_defaults(func=ticket.cmd_ticket_search)

    # 服务单详情
    tk_detail = tk_sub.add_parser("detail", help="获取服务单详情")
    tk_detail.add_argument("flow_id", help="服务单 ID (FLOW-xxx)")
    tk_detail.add_argument("--user-id", dest="user_id", help="用户工号(权限校验)")
    tk_detail.add_argument("--dept", help="部门")
    _add_global_args(tk_detail)
    tk_detail.set_defaults(func=ticket.cmd_ticket_detail)

    # 关联工单
    tk_orders = tk_sub.add_parser("orders", help="查询服务单关联的工单")
    tk_orders.add_argument("flow_id", help="服务单 ID")
    _add_global_args(tk_orders)
    tk_orders.set_defaults(func=ticket.cmd_ticket_orders)

    # 生命周期
    tk_lifecycle = tk_sub.add_parser("lifecycle", help="查询服务单生命周期(处理记录)")
    tk_lifecycle.add_argument("flow_id", help="服务单 ID")
    _add_global_args(tk_lifecycle)
    tk_lifecycle.set_defaults(func=ticket.cmd_ticket_lifecycle)

    # 历史相似工单
    tk_history = tk_sub.add_parser("history", help="查询历史相似工单")
    tk_history.add_argument("title", help="标题关键词")
    _add_global_args(tk_history)
    tk_history.set_defaults(func=ticket.cmd_ticket_history)

    # AI 聚合分析
    tk_analyze = tk_sub.add_parser("analyze", help="AI聚合查询: 详情+关联工单+生命周期+相似历史")
    tk_analyze.add_argument("flow_id", help="服务单 ID")
    tk_analyze.add_argument("--user-id", dest="user_id", help="用户工号")
    tk_analyze.add_argument("--dept", help="部门")
    _add_global_args(tk_analyze)
    tk_analyze.set_defaults(func=ticket.cmd_ticket_analyze)

    # ── notify (通知触达查询, roar noti-query) ──
    nf = sub.add_parser("notify", help="通知触达查询 (roar noti-query, 仅近7天)")
    nf_sub = nf.add_subparsers(dest="subcommand", required=True)
    _add_global_args(nf)

    nf_query = nf_sub.add_parser("query", help="按 queryId 查询通知投递状态(deliveryState 自动解读)")
    nf_query.add_argument("query_id", help="下游任务 ID (如 ali-ivr-21d7aff3-...)")
    _add_global_args(nf_query)
    nf_query.set_defaults(func=notify.cmd_notify_query)

    # ── db (数据库查询, DMS MCP + 本地直连) ──
    db_cmd = sub.add_parser("db", help="数据库查询 (DMS MCP Server / 本地直连)")
    db_sub = db_cmd.add_subparsers(dest="subcommand", required=True)
    _add_global_args(db_cmd)

    # 列出 DMS 工具
    db_tools = db_sub.add_parser("tools", help="列出 DMS MCP 可用工具")
    _add_global_args(db_tools)
    db_tools.set_defaults(func=db.cmd_db_tools)

    # 搜索数据库
    db_search = db_sub.add_parser("search", help="搜索数据库(DMS)")
    db_search.add_argument("keyword", help="数据库名关键词")
    _add_global_args(db_search)
    db_search.set_defaults(func=db.cmd_db_search)

    # 本地直连目标参数（query/tables/schema 共用）
    def _add_local_target_args(p):
        p.add_argument("--conn", help="本地直连 profile 名(见 seek db conn list)")
        p.add_argument("--project", help="项目名，与 --env 一起按 bind 反查 profile")
        p.add_argument("--env", help="环境名，配合 --project 反查 profile")
        p.add_argument("--i-know-this-is-prod", dest="i_know_this_is_prod",
                       action="store_true",
                       help="绑定生产类环境的 profile 直连需显式确认")

    # 列出数据表
    db_tables = db_sub.add_parser("tables", help="列出数据表(DMS 或本地直连)")
    db_tables.add_argument("database", nargs="?", help="DMS 数据库 ID；本地直连时省略")
    _add_local_target_args(db_tables)
    _add_global_args(db_tables)
    db_tables.set_defaults(func=db.cmd_db_tables)

    # 获取表结构
    db_schema = db_sub.add_parser("schema", help="获取表结构(DMS 或本地直连)")
    db_schema.add_argument("database", nargs="?", help="DMS 数据库 ID；本地直连时省略")
    db_schema.add_argument("table", help="表名")
    _add_local_target_args(db_schema)
    _add_global_args(db_schema)
    db_schema.set_defaults(func=db.cmd_db_schema)

    # 执行只读 SQL
    db_query = db_sub.add_parser("query", help="执行只读 SQL 查询(DMS 或本地直连)")
    db_query.add_argument("database", nargs="?", help="DMS 数据库 ID；本地直连时省略")
    db_query.add_argument("--sql", required=True, help="只读 SQL（仅 SELECT/WITH/EXPLAIN）")
    db_query.add_argument("--max", "--limit", dest="max", type=int, default=500,
                          help="本地直连结果行数上限 1-5000(默认 500, --limit 为别名)")
    _add_local_target_args(db_query)
    _add_global_args(db_query)
    db_query.set_defaults(func=db.cmd_db_query)

    # 本地连接 profile 管理
    db_conn = db_sub.add_parser("conn", help="本地直连 profile 管理(${SEEK_HOME:-~/.seek}/config/db.json)")
    db_conn_sub = db_conn.add_subparsers(dest="conn_subcommand", required=True)
    _add_global_args(db_conn)

    db_conn_add = db_conn_sub.add_parser("add", help="添加/覆盖连接 profile")
    db_conn_add.add_argument("name", help="profile 名(如 qt-stability-daily)")
    db_conn_add.add_argument("--type", default="mysql", choices=["mysql"],
                             help="数据库类型(一期仅 mysql)")
    db_conn_add.add_argument("--host", required=True, help="数据库主机")
    db_conn_add.add_argument("--port", type=int, default=3306, help="端口(默认 3306)")
    db_conn_add.add_argument("--database", required=True, help="库名")
    db_conn_add.add_argument("--user", required=True, help="用户名")
    db_conn_add.add_argument("--password", required=True,
                             help="密码；推荐 env:VAR 引用环境变量，或明文(文件 0600)")
    db_conn_add.add_argument("--project", help="绑定项目名(供 --project+--env 反查)")
    db_conn_add.add_argument("--env", help="绑定环境名(如 daily)")
    _add_global_args(db_conn_add)
    db_conn_add.set_defaults(func=db.cmd_db_conn_add)

    db_conn_list = db_conn_sub.add_parser("list", help="列出 profile(密码脱敏)")
    _add_global_args(db_conn_list)
    db_conn_list.set_defaults(func=db.cmd_db_conn_list)

    db_conn_test = db_conn_sub.add_parser("test", help="连通性测试(SELECT 1)")
    db_conn_test.add_argument("name", help="profile 名")
    _add_global_args(db_conn_test)
    db_conn_test.set_defaults(func=db.cmd_db_conn_test)

    db_conn_remove = db_conn_sub.add_parser("remove", help="删除 profile")
    db_conn_remove.add_argument("name", help="profile 名")
    _add_global_args(db_conn_remove)
    db_conn_remove.set_defaults(func=db.cmd_db_conn_remove)

    # ── errors (错误日志查看) ──
    err_cmd = sub.add_parser("errors", help="查看/清理 CLI 错误日志")
    err_sub = err_cmd.add_subparsers(dest="subcommand", required=True)
    _add_global_args(err_cmd)

    err_list = err_sub.add_parser("list", help="查看最近的错误日志")
    err_list.add_argument("--limit", type=int, default=20, help="返回条数")
    err_list.add_argument("--command", help="按命令过滤(如 deploy)")
    _add_global_args(err_list)
    def _list_errors(args):
        errors = error_log.read_errors(limit=args.limit, command=args.command)
        return success({"errors": errors, "count": len(errors)}, message="错误日志")

    err_list.set_defaults(func=_list_errors)

    err_clear = err_sub.add_parser("clear", help="清空错误日志")
    _add_global_args(err_clear)
    err_clear.set_defaults(func=lambda a: success({"cleared": error_log.clear_errors()},
                                                   message="错误日志已清空"))

    # ── perf (性能耗时观测) ──
    perf_cmd = sub.add_parser("perf", help="性能耗时观测 (${SEEK_HOME:-~/.seek}/logs/perf.jsonl)")
    perf_sub = perf_cmd.add_subparsers(dest="subcommand", required=True)
    _add_global_args(perf_cmd)

    perf_report = perf_sub.add_parser(
        "report", help="聚合分析耗时日志: 命令/IO 分组耗时、IO 占比与优化方向 hint")
    perf_report.add_argument("--time", default="24h",
                             help="时间窗: 24h/7d、from,to 时间戳或 'YYYY-MM-DD HH:MM:SS,YYYY-MM-DD HH:MM:SS' (默认 24h)")
    perf_report.add_argument("--keyword", help="按记录 command 字段子串过滤(大小写不敏感，命中命令名与 IO 动作描述)")
    perf_report.add_argument("--session", help="按 session_id 精确过滤(chain 会话归属)")
    _add_global_args(perf_report)
    perf_report.set_defaults(func=perf.cmd_perf_report)

    perf_clear = perf_sub.add_parser("clear", help="清空耗时日志")
    _add_global_args(perf_clear)
    perf_clear.set_defaults(func=perf.cmd_perf_clear)

    # ── skill (Skill 管理) ──
    sk = sub.add_parser("skill", help="Skill 安装/状态/卸载")
    sk_sub = sk.add_subparsers(dest="subcommand", required=True)
    _add_global_args(sk)

    sk_install = sk_sub.add_parser("install", help="安装 skill 到 Qoder skills 目录(符号链接)")
    sk_install.add_argument("--dir", help="自定义 skills 目录(默认 ~/.qoder/skills 与 ~/.qoderwork/skills)")
    _add_global_args(sk_install)
    sk_install.set_defaults(func=skill.cmd_skill_install)

    sk_update = sk_sub.add_parser("update", help="从源码更新 skill 到所有已安装目录")
    sk_update.add_argument("--dir", help="自定义 skills 目录")
    _add_global_args(sk_update)
    sk_update.set_defaults(func=skill.cmd_skill_update)

    sk_status = sk_sub.add_parser("status", help="检查 skill 安装状态")
    sk_status.add_argument("--dir", help="自定义 skills 目录")
    _add_global_args(sk_status)
    sk_status.set_defaults(func=skill.cmd_skill_status)

    sk_uninstall = sk_sub.add_parser("uninstall", help="卸载 skill(删除符号链接)")
    sk_uninstall.add_argument("--dir", help="自定义 skills 目录")
    _add_global_args(sk_uninstall)
    sk_uninstall.set_defaults(func=skill.cmd_skill_uninstall)

    return parser


def main():
    """CLI 主入口"""
    parser = _build_parser()
    args = parser.parse_args()

    fmt = getattr(args, "format", "json")
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        sys.exit(1)

    # 参数解析成功后才记录版本变化；--help 等纯帮助路径不产生持久化副作用。
    _check_version_change()

    # 构造命令名用于错误日志
    cmd_name = args.command
    if hasattr(args, "subcommand") and args.subcommand:
        cmd_name = f"{args.command} {args.subcommand}"

    should_exit_error = False
    # perf 观测（L1 命令级）：计时区间只覆盖命令函数本身，不含参数解析与结果打印。
    # 停表在 func 返回/抛出瞬间（内层 finally），print_result 与 error_log 写盘不计时。
    perf_start = time.perf_counter()
    perf_status = "error"  # 异常路径下走 error；正常路径在下方覆盖
    try:
        try:
            result = func(args)
            perf_status = "success" if not (
                isinstance(result, dict) and result.get("status") == "error"
            ) else "error"
        finally:
            perf_log.log_perf(cmd_name, "command",
                              (time.perf_counter() - perf_start) * 1000, perf_status)
        print_result(result, fmt=fmt)
        # 如果返回了 error，自动记录到错误日志
        if isinstance(result, dict) and result.get("status") == "error":
            err = result.get("error", {})
            error_log.log_error(
                command=cmd_name,
                error_code=err.get("code", "UNKNOWN"),
                error_message=err.get("message", ""),
                context=result.get("data"),
            )
            should_exit_error = True
    except SystemExit:
        # argparse / print_help 等主动退出，向上传递
        raise
    except config.ProjectConfigError as e:
        result = error(str(e), code="CONFIG_ERROR")
        print_result(result, fmt=fmt)
        error_log.log_error(
            command=cmd_name,
            error_code="CONFIG_ERROR",
            error_message=str(e),
        )
        sys.exit(1)
    except Exception as e:
        result = error(f"unexpected error: {e}", code="INTERNAL_ERROR")
        print_result(result, fmt=fmt)
        error_log.log_error(
            command=cmd_name,
            error_code="INTERNAL_ERROR",
            error_message=str(e),
        )
        sys.exit(1)

    # 业务错误退出放在 try 块外，避免与 except SystemExit 互相干扰
    if should_exit_error:
        sys.exit(1)


def _check_version_change():
    """检测版本变更；状态文件不可写时降级提示，不阻断原命令。"""
    from seek_cli import CHANGELOG

    version_file = seek_path("version")
    try:
        version_file.parent.mkdir(parents=True, exist_ok=True)
        last_version = version_file.read_text().strip() if version_file.exists() else None

        if last_version == __version__:
            return

        if last_version is None:
            print(f"[seek] v{__version__} — 首次安装", file=sys.stderr)
        else:
            print(f"[seek] 版本更新: {last_version} → {__version__}", file=sys.stderr)
            all_versions = list(CHANGELOG.keys())
            new_versions = (all_versions[:all_versions.index(last_version)]
                            if last_version in all_versions else all_versions)
            for version in new_versions:
                print(f"  {version}:", file=sys.stderr)
                for change in CHANGELOG.get(version, []):
                    print(f"    - {change}", file=sys.stderr)

        version_file.write_text(__version__, encoding="utf-8")
    except OSError as exc:
        print(f"[seek] 版本标记不可写(忽略): {version_file}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
