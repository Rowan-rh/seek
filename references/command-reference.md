# 命令参考

本页在需要完整命令示例或参数语义时加载。实时命令 schema 以 `seek capabilities` 为准；本页只保留稳定的调用路径和排查顺序，避免与代码维护两套参数表。

## 冷启动发现

```bash
seek init
seek init --verify
seek capabilities
seek version
seek harness check
seek harness evaluate --scenarios harness/scenarios/v1.json
seek doctor --no-live
```

`seek init` 检查 A1 CLI、DMS MCP 与 SLS AK/SK，并给出配置文档和下一步；默认不联网，`--verify` 才验证 A1 登录态和 DMS MCP。`harness check` 在不访问网络的情况下检查隔离存储、内置资源、版本和可选依赖；`harness evaluate` 默认回放脱敏场景并检查协议、轨迹和报告，指定 `--agent-command '<runner>'` 时实际调用外部 Agent；`capabilities` 返回命令、子命令、参数和输出契约。发现文档与 CLI 行为不一致时，先以它和实际 `--help` 为准，再修正文档。

## 标准排查协议

```bash
seek chain list
seek chain start <name> --project <project> --problem "..." \
  [--context '{"flow_id":"FLOW-xxx"}']
# 首步输入缺键时 start 报 MISSING_CONTEXT 且不建会话；已建会话可补注入：
seek chain provide <session> --inputs '{"flow_id":"FLOW-xxx"}'
seek chain step <session>
seek chain validate <session> --step <N>
# 按当前步骤指引执行查询
seek chain complete <session> --summary "..." --outputs '{...}' --evidence '{...}' [--token-usage '{...}']
# 重复 step / validate / 执行 / complete
seek chain context <session>
seek chain usage <session>  # token 仅统计，不参与评分
# 链路 completed 后生成报告文件名与模板头部（CLI 不落盘）
seek chain report <session> --slug "batch-560d6f3c-objectlist-empty"
```

条件步骤的 `when` 不满足时由引擎自动记录到 `skipped_steps` 并注入声明的 `skipOutputs`；不要手工执行已跳过步骤，也不要将 skipped 写成 NO_DATA。

每个步骤都要先读取当前步骤指引并验证约束。`outputs` 必须是对象，并包含当前步骤声明的全部字段；没有结果或不适用时显式提交 `""`、`[]` 或 `{}`。链路完成后才生成报告：`chain report` 对 completed 会话返回带产出日期前缀的 `filename`（`seek-report-YYYY-MM-DD-{slug}.md`）、已填充 session_id/链路/起止时间/问题描述的 `header_markdown` 和模板路径；slug 为语义段（场景-业务ID片段-现象，小写 kebab-case，CLI 自动拼前缀禁止自带日期/前缀/后缀），CLI 不写文件，落盘由调用方用返回的 filename 完成。`chain start` 会前置校验首步外部输入（各链路所需键名见 `chain list` 的 `firstStepInputs`），缺键时报错（`MISSING_CONTEXT`）且不创建会话；会话已建后补注入用 `chain provide <session> --inputs '{...}'`。

## 项目与部署

```bash
seek project list
seek project show <project>
seek deploy branch <project>
seek deploy changes <project>
seek deploy env <project> --env daily|pre|prod
```

项目目录名和 Aone 应用名可能不同，以 `seek project show` 返回的 `a1AppName` 为准。

## SLS 与 trace

```bash
seek sls config <project> --env <env>
seek sls logs <project> --env <env> --level ERROR --time 1h --max 100
seek sls query <project> --env <env> --query '<query>' --time 1h --max 100
seek trace call-chain <project>
seek trace query <project> --env <env> --trace-id <trace-id> --time 1h
```

多 logstore 环境要检查 `byLogstore`、`truncatedLogstores` 和 `errors`，不能只看顶层 `count`。详细证据边界见 [`evidence-and-boundaries.md`](evidence-and-boundaries.md)。

**环境别名**：项目可配置 `envAliases` 把口语环境名映射到真实环境（如应急响应类项目预置 `daily → yanlian`），`--env daily` 会自动命中 `yanlian`。别名生效时结果带 `resolvedEnv` 字段与 warning，不会静默换环境；`sls config <project>` 全量输出含 `env_aliases`，`--env` 未命中报错的 data 也会附上。

## 工单与通知

```bash
seek ticket search --keyword "..."
seek ticket detail FLOW-xxx
seek ticket analyze FLOW-xxx
seek notify query <queryId>
```

工单链路需要用户提供 flow ID 时，用 `chain start ... --context` 注入；漏注时用 `chain provide` 补注入而非重建会话。通知触达查询受近 7 天留存限制。通知场景的取证顺序见 [`investigation-patterns.md`](investigation-patterns.md)。

## 钉钉

```bash
seek dingtalk groups <关键词>                  # 搜索群聊，取 cid
seek dingtalk messages --group <cid> --time "YYYY-MM-DD HH:MM:SS" [--limit N]
seek dingtalk search <关键词> [--group <cid>] [--sender-ids ...] [--at-me] \
  [--time-from "YYYY-MM-DD HH:MM:SS"] [--time-to "..."] [--limit N]
seek dingtalk unread                          # 未读会话列表
seek dingtalk contact <关键词>                 # 搜索联系人
seek dingtalk members --group <cid>           # 群成员
seek dingtalk doc-read <url>                  # 读取钉钉文档
seek dingtalk send --group <cid> --text "..." [--title "..."]
```

`messages` 与 `send` 的会话目标三选一：`--group`（群聊）/ `--user` / `--open-dingtalk-id`（单聊）。`messages` 与 `search` 的时间参数是**起点语义**（从该时间点往现在拉），不是「最近 N 条」；返 0 条的处置与截图 fallback 见 [`investigation-patterns.md`](investigation-patterns.md) 的「钉钉消息时间窗口语义」。`send` 会产生对外可见消息，执行前必须确认接收目标与文案。

## 数据库

双 backend 路由：**日常/预发优先本地直连（--conn），生产/受管实例走 DMS（database_id）**。

```bash
# 本地直连（日常/预发）：profile 管理
seek db conn add <name> --type mysql --host H --port 3306 --database D \
  --user U --password 'env:VAR' --project <project> --env daily
seek db conn list | test <name> | remove <name>

# 本地直连查询（--conn 或 --project+--env 按 bind 反查）
seek db query --conn <name> --sql "SELECT ..."
seek db query --project <project> --env daily --sql "SELECT ..."
seek db tables --conn <name>
seek db schema --conn <name> <table>

# DMS 路径（生产/受管实例，行为不变）
seek db search "关键词"
seek db query <database_id> --sql "SELECT ..."
```

两条路径均仅允许只读 SQL（SELECT/WITH/EXPLAIN）。绑定生产类环境的 profile 直连需显式 `--i-know-this-is-prod`；本地直连结果默认 500 行截断（`--max` 上限 5000），输出含 `backend`/`truncated` 字段供证据标注。

## 配置与诊断

```bash
seek config show
seek config path
seek project list
seek sls config <project>
seek doctor
seek doctor --no-live
```

**性能耗时日志**：每次命令与集成 IO 自动写 `~/.seek/logs/perf.jsonl`（字段 `timestamp`/`command`/`span`/`status`/`duration_ms`；环境变量 `SEEK_SESSION_ID` 存在时附带 `session_id`）。`span=command` 为单命令端到端耗时，`sls_query`/`a1_subprocess`/`dms_call` 为集成 IO 耗时。步骤耗时归因：session 时间窗内 `span=command` 的 `duration_ms` 总和与步骤端到端耗时的差值 ≈ LLM+编排开销。`seek config set options.perf_log false` 关闭。

**聚合分析**：`seek perf report [--time 24h] [--keyword <substr>] [--session <id>]` 按时间窗（与 SLS `--time` 同语法）聚合命令级/IO 级耗时（count/errors/p50/p95/max），输出 `totals.ioSharePct` 归因占比与优化方向 hint（IO span 嵌套于 command 区间，占比为粗略近似）；`seek perf clear` 清空日志并返回条数。

出现认证、依赖、环境或返回结构问题时，按症状读取 [`cli/TROUBLESHOOTING.md`](../cli/TROUBLESHOOTING.md)。

## 输出契约

默认输出 JSON：

```json
{"status":"ok","data":{},"message":"..."}
```

错误响应使用稳定的 `status=error`、`error.code`、`error.message` 字段。需要人工阅读时，可在命令中加入 `--format text`，但 agent 处理默认使用 JSON。

**管道契约**：stdout 恒为可解析 JSON、退出码非零即错。即便是参数解析失败（非法选项/缺参），也会向 stdout 输出 `code=ARGPARSE_ERROR` 的 JSON（usage 走 stderr）并返回退出码 2，下游 `json.load(sys.stdin)` 不会因空 stdout 崩溃。条数上限参数在 `sls query/logs`、`trace query`、`db query` 上 `--max` 与 `--limit` 等价，可任意混用。
