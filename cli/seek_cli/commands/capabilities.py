"""能力发现命令 — 输出所有可用命令的 JSON schema，供 agent 动态发现"""

from seek_cli import __version__
from seek_cli.output import success, error
from seek_cli import chain as chain_engine


def cmd_capabilities(args) -> dict:
    """输出 CLI 所有命令的能力描述（JSON schema 格式）

    Agent 调用此命令可以一次性了解所有可用命令、参数和集成能力。
    """
    capabilities = {
        "name": "seek",
        "version": __version__,
        "description": "AI agent 排查编排 CLI",
        "output_format": "json (default) | text (--format text)",
        "response_structure": {
            "success": {"status": "ok", "data": "...", "message": "..."},
            "error": {"status": "error", "error": {"code": "...", "message": "..."}, "data": None},
        },
        "commands": {
            "capabilities": {
                "description": "输出所有命令的能力清单(JSON schema)",
                "subcommands": [],
                "args": [{"name": "--format", "choices": ["json", "text"], "default": "json"}],
            },
            "plugin": {
                "description": "插件与 Provider 管理 — 发现内置和第三方 seek.plugins 插件",
                "subcommands": [
                    {"name": "list", "description": "列出已发现的插件和 Provider", "args": []},
                    {"name": "show", "description": "查看插件元数据和本地健康检查", "args": [
                        {"name": "name", "required": True, "help": "插件 ID，例如 alibaba"},
                    ]},
                ],
            },
            "project": {
                "description": "项目管理 — 列出/查看/添加项目配置",
                "subcommands": [
                    {"name": "list", "description": "列出所有已配置项目", "args": []},
                    {"name": "show", "description": "查看项目详情", "args": [{"name": "name", "required": True, "help": "项目名"}]},
                    {"name": "add", "description": "添加或更新项目配置", "args": [
                        {"name": "name", "required": True, "help": "项目名"},
                        {"name": "--desc", "help": "项目描述"},
                        {"name": "--repo", "help": "本地代码仓库路径"},
                        {"name": "--a1-app", "help": "Aone 平台应用名"},
                        {"name": "--sls-daily", "help": "日常 SLS: endpoint/project/logstore"},
                        {"name": "--sls-pre", "help": "预发 SLS: endpoint/project/logstore"},
                        {"name": "--sls-prod", "help": "生产 SLS: endpoint/project/logstore"},
                    ]},
                ],
            },
            "deploy": {
                "description": "部署信息查询 (A1 CLI 集成) — 查询 Aone 部署分支/变更单/部署单",
                "subcommands": [
                    {"name": "branch", "description": "查询应用部署信息(应用元信息+各pipeline最近实例的发布分支/commit)", "args": [{"name": "project", "required": True}]},
                    {"name": "info", "description": "查询 Aone 应用详情", "args": [{"name": "project", "required": True}]},
                    {"name": "orders", "description": "查询部署单列表", "args": [{"name": "project", "required": True}]},
                    {"name": "order", "description": "查询单个部署单详情", "args": [{"name": "order_id", "required": True}]},
                    {"name": "changes", "description": "查询变更单列表", "args": [{"name": "project", "required": True}]},
                    {"name": "env", "description": "查询指定环境部署信息(pipeline+分支+变更)，环境关键词同义词自动扩展，未命中时 hint 给出全部 pipeline 名", "args": [
                        {"name": "project", "required": True},
                        {"name": "--env", "default": "日常", "help": "环境关键词: 日常/预发/正式，或别名 daily/pre/prod/生产/online 等"},
                    ]},
                ],
            },
            "sls": {
                "description": "SLS 日志查询 (aliyun-log SDK) — 关键词/SQL 查询",
                "subcommands": [
                    {"name": "query", "description": "执行 SLS 查询（项目配置或裸目标直查）；关键词查询返空时自动探测索引形态并输出 warnings/indexCheck", "args": [
                        {"name": "project", "help": "项目配置名；直查时省略"},
                        {"name": "--env", "help": "项目配置环境；配置模式必填"},
                        {"name": "--endpoint", "help": "SLS endpoint；直查模式必填"},
                        {"name": "--sls-project", "help": "SLS project；直查模式必填"},
                        {"name": "--logstore", "help": "SLS logstore；直查模式必填"},
                        {"name": "--query", "help": "查询语句；与 --query-file 二选一"},
                        {"name": "--query-file", "help": "从文件读取查询语句('-' 表示 stdin)，规避中文/引号嵌套的 shell 转义"},
                        {"name": "--time", "default": "15m", "help": "15m/1h/1d、from,to 时间戳或 'YYYY-MM-DD HH:MM:SS,YYYY-MM-DD HH:MM:SS'"},
                        {"name": "--max", "type": "int", "default": 100, "help": "1-1000"},
                        {"name": "--sort", "choices": ["asc", "desc"], "help": "按日志时间排序"},
                    ]},

                    {"name": "logs", "description": "快捷日志查询(自动构造查询)", "args": [
                        {"name": "project", "required": True},
                        {"name": "--env", "required": True},
                        {"name": "--level", "help": "ERROR/WARN/INFO"},
                        {"name": "--keyword", "help": "关键词"},
                        {"name": "--trace-id", "help": "traceId"},
                        {"name": "--time", "default": "15m"},
                        {"name": "--max", "type": "int", "default": 100, "help": "每个查询目标 1-1000"},
                    ]},
                    {"name": "config", "description": "查看 SLS 配置", "args": [
                        {"name": "project", "required": True},
                        {"name": "--env", "help": "指定环境"},
                    ]},
                ],
            },
            "trace": {
                "description": "调用链路查询 — 服务间调用关系和 trace",
                "subcommands": [
                    {"name": "call-chain", "description": "查看调用链路文档", "args": [{"name": "project", "required": True}]},
                    {"name": "query", "description": "通过 traceId 查询 trace", "args": [
                        {"name": "project", "required": True},
                        {"name": "--env", "required": True},
                        {"name": "--trace-id", "required": True},
                        {"name": "--time", "default": "1h"},
                        {"name": "--max", "type": "int", "default": 50},
                    ]},
                    {"name": "topology", "description": "查看服务拓扑关系", "args": []},
                ],
            },
            "chain": {
                "description": "排查链路编排 — 条件路由、结构化证据、会话上下文与 token 统计",
                "subcommands": [
                    {"name": "list", "description": "列出排查链路", "args": []},
                    {"name": "show", "description": "查看链路详情", "args": [{"name": "name", "required": True}]},
                    {"name": "start", "description": "开始排查会话", "args": [
                        {"name": "name", "required": True, "help": "链路名"},
                        {"name": "--project", "help": "目标项目"},
                        {"name": "--problem", "help": "问题描述"},
                        {"name": "--context", "help": "初始上下文 JSON 对象"},
                    ]},
                    {"name": "provide", "description": "向已建会话补注入首步输入", "args": [
                        {"name": "session", "required": True},
                        {"name": "--inputs", "required": True, "help": "补注入输入(JSON对象)"},
                    ]},
                    {"name": "status", "description": "查看会话状态", "args": [{"name": "session", "required": True}]},
                    {"name": "step", "description": "查看当前步骤", "args": [{"name": "session", "required": True}]},
                    {"name": "complete", "description": "完成当前步骤,推进下一步", "args": [
                        {"name": "session", "required": True},
                        {"name": "--summary", "help": "步骤摘要"},
                        {"name": "--outputs", "help": "步骤输出(JSON)"},
                        {"name": "--evidence", "help": "结构化证据(JSON: status/sources/boundary/reason)"},
                        {"name": "--token-usage", "help": "token 使用量(JSON，仅统计不参与评分)"},
                    ]},
                    {"name": "validate", "description": "验证步骤约束(防跳步)", "args": [
                        {"name": "session", "required": True},
                        {"name": "--step", "type": "int", "required": True},
                    ]},
                    {"name": "amend", "description": "回填更正已完成步骤", "args": [
                        {"name": "session", "required": True},
                        {"name": "--step", "type": "int", "required": True},
                        {"name": "--summary", "help": "更正说明"},
                        {"name": "--outputs", "help": "更正输出(JSON)"},
                        {"name": "--evidence", "help": "更正后的结构化证据(JSON)"},
                    ]},
                    {"name": "context", "description": "获取累积上下文", "args": [{"name": "session", "required": True}]},
                    {"name": "report", "description": "生成报告落盘文件名与模板头部(completed 会话；CLI 不写文件，落盘由调用方完成)", "args": [
                        {"name": "session", "required": True},
                        {"name": "--slug", "required": True, "help": "文件名语义段 场景-业务ID片段-现象(如 batch-560d6f3c-objectlist-empty)，CLI 自动拼 seek-report-<产出日期>- 前缀"},
                    ]},
                    {"name": "usage", "description": "汇总会话 token 使用量(仅统计，不参与评分)", "args": [{"name": "session", "required": True}]},
                    {"name": "sessions", "description": "列出最近的排查会话", "args": [{"name": "--limit", "type": "int", "default": 20}]},
                ],
            },
            "dingtalk": {
                "description": "钉钉集成 (dws CLI) — 聊天/文档/通讯录",
                "subcommands": [
                    {"name": "groups", "description": "搜索群聊", "args": [{"name": "query", "required": True}]},
                    {"name": "messages", "description": "拉取会话消息(群聊/单聊)", "args": [
                        {"name": "--group", "help": "群 openConversationId"},
                        {"name": "--user", "help": "单聊 userId"},
                        {"name": "--open-dingtalk-id", "help": "单聊 openDingTalkId"},
                        {"name": "--time", "required": True, "help": "yyyy-MM-dd HH:mm:ss"},
                        {"name": "--direction", "default": "newer"},
                        {"name": "--limit", "type": "int", "default": 50},
                    ]},
                    {"name": "search", "description": "多维度搜索消息", "args": [
                        {"name": "query", "required": True},
                        {"name": "--group", "help": "指定会话"},
                        {"name": "--sender-ids", "help": "发送者 openDingTalkId"},
                        {"name": "--time-from", "help": "开始时间"},
                        {"name": "--time-to", "help": "结束时间"},
                        {"name": "--at-me", "help": "只搜@我的"},
                        {"name": "--limit", "type": "int", "default": 50},
                    ]},
                    {"name": "unread", "description": "获取未读会话列表", "args": []},
                    {"name": "send", "description": "发送消息(群聊/单聊)", "args": [
                        {"name": "--group", "help": "群 openConversationId"},
                        {"name": "--user", "help": "单聊 userId"},
                        {"name": "--open-dingtalk-id", "help": "单聊 openDingTalkId"},
                        {"name": "--text", "required": True},
                        {"name": "--title", "help": "消息标题"},
                    ]},
                    {"name": "contact", "description": "搜索联系人", "args": [{"name": "query", "required": True}]},
                    {"name": "members", "description": "查看群成员", "args": [{"name": "--group", "required": True}]},
                    {"name": "doc-read", "description": "读取钉钉文档", "args": [{"name": "url", "required": True}]},
                ],
            },
            "ticket": {
                "description": "云网络工单查询 (qt-expert API) — 服务单/历史/分析",
                "subcommands": [
                    {"name": "search", "description": "搜索云网络服务单", "args": [
                        {"name": "--keyword", "help": "标题关键词"},
                        {"name": "--flow-type", "default": "afterSale"},
                        {"name": "--status", "help": "状态过滤"},
                        {"name": "--product", "help": "产品过滤"},
                        {"name": "--page", "type": "int", "default": 1},
                        {"name": "--page-size", "type": "int", "default": 20},
                    ]},
                    {"name": "detail", "description": "获取服务单详情", "args": [
                        {"name": "flow_id", "required": True, "help": "FLOW-xxx"},
                        {"name": "--user-id", "help": "工号(权限)"},
                        {"name": "--dept", "help": "部门"},
                    ]},
                    {"name": "orders", "description": "查询关联工单", "args": [{"name": "flow_id", "required": True}]},
                    {"name": "lifecycle", "description": "查询生命周期(处理记录)", "args": [{"name": "flow_id", "required": True}]},
                    {"name": "history", "description": "查询历史相似工单", "args": [{"name": "title", "required": True}]},
                    {"name": "analyze", "description": "AI聚合查询: 详情+关联工单+生命周期+相似历史", "args": [
                        {"name": "flow_id", "required": True},
                        {"name": "--user-id", "help": "工号"},
                        {"name": "--dept", "help": "部门"},
                    ]},
                ],
            },
            "notify": {
                "description": "通知触达查询 (roar noti-query, 仅近7天) — deliveryState 自动解读",
                "subcommands": [
                    {"name": "query", "description": "按下游任务 ID 查询通知投递状态(deliveryState/运营商回执码中文解读, receiver 脱敏)", "args": [
                        {"name": "query_id", "required": True, "help": "下游任务 ID (如 ali-ivr-xxx)"},
                    ]},
                ],
            },
            "db": {
                "description": "数据库只读查询 — 双 backend: DMS MCP(生产/受管实例, database_id 寻址) 与本地直连(日常/预发, --conn/--project+--env 寻址)；日常环境优先本地直连，生产走 DMS",
                "subcommands": [
                    {"name": "tools", "description": "列出 DMS 可用工具", "args": []},
                    {"name": "search", "description": "搜索数据库(DMS)", "args": [{"name": "keyword", "required": True}]},
                    {"name": "tables", "description": "列出数据表(DMS 或本地直连)", "args": [
                        {"name": "database", "help": "DMS 数据库 ID；本地直连时省略"},
                        {"name": "--conn", "help": "本地直连 profile 名"},
                        {"name": "--project", "help": "项目名，配合 --env 按 bind 反查 profile"},
                        {"name": "--env", "help": "环境名"},
                        {"name": "--i-know-this-is-prod", "help": "生产类环境 profile 直连显式确认"},
                    ]},
                    {"name": "schema", "description": "获取表结构(DMS 或本地直连)", "args": [
                        {"name": "database", "help": "DMS 数据库 ID；本地直连时省略，单个位置参数视为表名"},
                        {"name": "table", "help": "表名"},
                        {"name": "--conn", "help": "本地直连 profile 名"},
                        {"name": "--project", "help": "项目名"},
                        {"name": "--env", "help": "环境名"},
                        {"name": "--i-know-this-is-prod", "help": "生产类环境直连显式确认"},
                    ]},
                    {"name": "query", "description": "执行只读 SQL（仅 SELECT/WITH/EXPLAIN）；本地直连输出含 backend/conn/columns/rows/rowCount/truncated", "args": [
                        {"name": "database", "help": "DMS 数据库 ID；本地直连时省略"},
                        {"name": "--sql", "required": True, "help": "仅 SELECT/WITH/EXPLAIN"},
                        {"name": "--conn", "help": "本地直连 profile 名(优先级最高)"},
                        {"name": "--project", "help": "项目名，配合 --env 按 bind 反查 profile"},
                        {"name": "--env", "help": "环境名"},
                        {"name": "--max", "type": "int", "default": 500, "help": "本地直连行数上限 1-5000"},
                        {"name": "--i-know-this-is-prod", "help": "生产类环境直连显式确认"},
                    ]},
                    {"name": "conn", "description": "本地连接 profile 管理，子命令: add(添加,参数 name/--type/--host/--port/--database/--user/--password[--project][--env], 密码推荐 env:VAR 引用) / list(列出,密码脱敏) / test <name>(连通性测试) / remove <name>(删除)；存储于 ${SEEK_HOME:-~/.seek}/config/db.json(0600)", "args": []},
                ],
            },
            "skill": {
                "description": "Skill 安装/更新/状态/卸载 — 符号链接到 Qoder skills 目录",
                "subcommands": [
                    {"name": "install", "description": "安装 skill(符号链接)", "args": [{"name": "--dir", "help": "自定义目录"}]},
                    {"name": "update", "description": "从源码更新已安装的 skill", "args": [{"name": "--dir", "help": "自定义目录"}]},
                    {"name": "status", "description": "检查安装状态", "args": [{"name": "--dir", "help": "自定义目录"}]},
                    {"name": "uninstall", "description": "卸载 skill", "args": [{"name": "--dir", "help": "自定义目录"}]},
                ],
            },
            "version": {
                "description": "版本与变更记录 — 输出当前版本号和 CHANGELOG",
                "subcommands": [],
            },
            "init": {
                "description": "首次接入向导 — 检查 A1 CLI、DMS MCP 与 SLS AK/SK，输出配置文档和验证动作",
                "args": [
                    {"name": "--verify", "type": "bool", "default": False,
                     "help": "显式验证 A1 登录态和 DMS MCP 工具发现"},
                ],
            },
            "doctor": {
                "description": "配置体检 — 校验所有 SLS 配置的结构与真实存在性，可选活性检查(窗口内 0 条标记 stale)",
                "subcommands": [],
                "args": [
                    {"name": "--no-live", "help": "只做结构校验，不调 SLS API 实测"},
                    {"name": "--liveness-window", "help": "活性检查窗口(如 30d/7d/24h)，窗口内 0 条日志标记 stale"},
                ],
            },
            "harness": {
                "description": "Agent Harness — 离线就绪检查及协议、轨迹、报告三层场景评测",
                "subcommands": [
                    {"name": "check", "description": "运行全部离线就绪检查", "args": []},
                    {"name": "evaluate", "description": "运行 Agent 场景 replay 或真实 runner", "args": [
                        {"name": "--scenarios", "required": True},
                        {"name": "--agent-command"},
                        {"name": "--timeout"},
                        {"name": "--scenario"},
                    ]},
                ],
            },
            "config": {
                "description": "统一配置管理 — ${SEEK_HOME:-~/.seek}/config/seek.json (环境变量 > seek.json > 旧文件 > 默认值)",
                "subcommands": [
                    {"name": "show", "description": "聚合展示全部配置项生效值与来源(secret脱敏)", "args": []},
                    {"name": "get", "description": "读取配置项", "args": [{"name": "key", "required": True}]},
                    {"name": "set", "description": "写入配置项", "args": [
                        {"name": "key", "required": True},
                        {"name": "value", "required": True},
                    ]},
                    {"name": "unset", "description": "删除配置项", "args": [{"name": "key", "required": True}]},
                    {"name": "path", "description": "输出配置目录与文件状态", "args": []},
                ],
            },
            "errors": {
                "description": "错误日志查看/清理 — 记录在 ${SEEK_HOME:-~/.seek}/logs/errors.jsonl",
                "subcommands": [
                    {"name": "list", "description": "查看错误日志", "args": [
                        {"name": "--limit", "type": "int", "default": 20},
                        {"name": "--command", "help": "按命令过滤"},
                    ]},
                    {"name": "clear", "description": "清空错误日志", "args": []},
                ],
            },
            "perf": {
                "description": "性能耗时观测 — perf.jsonl 聚合分析与清理(命令级/IO 级耗时、IO 占比归因)",
                "subcommands": [
                    {"name": "report", "description": "聚合分析耗时日志: 命令与 IO 分组(count/errors/p50/p95/max)、ioSharePct 归因占比、会话归属与优化方向 hint", "args": [
                        {"name": "--time", "default": "24h", "help": "时间窗: 24h/7d、from,to 或人类可读区间"},
                        {"name": "--keyword", "help": "记录 command 字段子串过滤(大小写不敏感)"},
                        {"name": "--session", "help": "session_id 精确过滤"},
                    ]},
                    {"name": "clear", "description": "清空耗时日志(返回清除条数)", "args": []},
                ],
            },
        },
        "chains": [],
        "plugins": [],
        "data_contracts": {
            "evidence": chain_engine.EVIDENCE_SCHEMA,
            "token_usage": {
                **chain_engine.TOKEN_USAGE_SCHEMA,
                "used_for_scoring": False,
            },
        },
        "integrations": [
            {"name": "A1 CLI", "type": "subprocess", "commands": ["deploy"], "auth": "a1 auth login", "documentation": "https://a1.io.alibaba-inc.com/docs/guide/"},
            {"name": "aliyun-log SDK", "type": "python-sdk", "commands": ["sls", "trace query"], "auth": "~/.aliyun/config.json"},
            {"name": "dws CLI", "type": "subprocess", "commands": ["dingtalk"], "auth": "dws auth (qoderwork built-in)"},
            {"name": "qt-expert API", "type": "http", "commands": ["ticket"], "host": "http://pre-qt-expert.aliyun-inc.com"},
            {"name": "roar noti-query", "type": "http", "commands": ["notify"], "host": "http://roar.alibaba-inc.com"},
            {"name": "DMS MCP", "type": "stdio-jsonrpc", "commands": ["db(DMS路径)"], "auth": "~/.qoderwork/mcp.json", "documentation": "https://alidocs.dingtalk.com/i/nodes/EpGBa2Lm8aZxe5myCZYKkoYkWgN7R35y"},
            {"name": "PyMySQL 本地直连", "type": "python-sdk(optional)", "commands": ["db(--conn路径)"], "auth": "${SEEK_HOME:-~/.seek}/config/db.json + env:VAR 密码", "install": "pip install seek-cli[mysql]"},
        ],
        "config": {
            "projects_file": "config/projects.json (seed) + ${SEEK_HOME:-~/.seek}/config/projects.json (user override)",
            "chains_file": "chains/default.json",
            "sessions_dir": "${SEEK_HOME:-~/.seek}/sessions/",
            "expert_host_env": "QT_EXPERT_HOST (default: http://pre-qt-expert.aliyun-inc.com)",
            "roar_host_env": "ROAR_HOST (default: http://roar.alibaba-inc.com)",
            "seek_home": "SEEK_HOME 环境变量可覆盖，默认 ~/.seek",
            "unified_settings": "${SEEK_HOME:-~/.seek}/config/seek.json (seek config show/set 统一管理)",
            "db_connections": "${SEEK_HOME:-~/.seek}/config/db.json (本地直连 profile, seek db conn 管理, 0600)",
        },
    }
    try:
        capabilities["chains"] = chain_engine.list_chains()
    except chain_engine.ChainConfigError as exc:
        return error(str(exc), code="CHAIN_CONFIG_ERROR")
    from seek_cli.plugins import get_registry
    registry = get_registry()
    capabilities["plugins"] = registry.as_dicts()
    capabilities["plugin_load_errors"] = registry.load_errors()
    for plugin in registry.plugins():
        for command_name, command_spec in plugin.command_capabilities().items():
            capabilities["commands"].setdefault(command_name, command_spec)
    return success(capabilities, message="seek CLI 能力清单")


def _get_chains_summary() -> list:
    """获取排查链路摘要。"""
    return chain_engine.list_chains()
