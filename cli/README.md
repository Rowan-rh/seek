# seek CLI 工具

## 设计目标

本 CLI 工具**不是给人用的**，而是给 AI agent 调用的。核心设计原则：

1. **结构化输出** — 默认 JSON，agent 可直接解析；stdout 恒为可解析 JSON（参数解析失败也输出 `ARGPARSE_ERROR` JSON，usage 走 stderr），退出码非零即错
2. **流程编排约束** — 通过排查链路引擎约束 agent 按步骤执行
3. **集成能力** — 封装 A1 CLI、aliyun-log SDK、dws CLI、qt-expert API
4. **零交互** — 所有参数通过命令行传入，不等待用户输入
5. **插件化** — 厂商和平台集成通过 Provider 插件发现，不侵入 Chain 核心
6. **自发现** — `seek capabilities` 一条命令输出全部能力清单

## 安装

```bash
cd cli
pip install -e .
```

基础安装不绑定具体云厂商；需要现有 Alibaba SLS 适配器时安装
`pip install -e '.[alibaba]'`，需要本地 MySQL 直连时安装 `.[mysql]`。

安装后可用 `seek` 或 `python -m seek_cli` 调用。

## 测试

### 全量测试

```bash
cd cli
python3 -m unittest discover -s tests -v
```

### PR 机械检查

仓库脚本 `run_checks.sh` 使用临时 `SEEK_HOME` 执行全量单测、Harness 离线黑盒评测、OpenSpec 校验和裸 except 检查：

```bash
cd cli
bash run_checks.sh
```

> 说明：当前仓库未配置 pre-commit 或平台 CI，因此采用仓库内脚本作为 PR 最小机械执行入口；外部 CI 配置需单独授权。脚本不会读写真实 `~/.seek`。

## 文档职责

- `seek capabilities` 是命令、参数和响应 schema 的实时权威来源。
- 根目录 [`SKILL.md`](../SKILL.md) 是 Agent 冷启动入口，定义显式触发规则、排查协议和硬约束。
- 根目录 [`references/`](../references/) 按需提供证据边界、调查模式和稳定命令示例。
- 本文是 CLI 的人类可读静态参考；错误症状和依赖故障见本文旁的 [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)。
- 机器执行链路以 [`chains/default.json`](chains/default.json) 和 `seek chain step` 返回为准。

不要把场景知识、历史案例或完整排查经验继续追加到 `SKILL.md`；新增内容应按场景进入 `references/`，并在入口文档增加索引。

## 命令总览

| 命令组 | 说明 | 集成 |
|--------|------|------|
| `capabilities` | 输出所有命令能力清单(JSON schema) | 内置 |
| `plugin` | 插件与 Provider 列表、元数据和本地健康检查 | 内置 + entry points |
| `init` | 检查并引导配置 A1 CLI、DMS MCP、SLS AK/SK | 内置 |
| `harness` | Agent Harness 离线就绪检查 | 内置 |
| `project` | 项目配置管理 | 内置 JSON |
| `deploy` | 部署信息查询 | A1 CLI |
| `sls` | SLS 日志查询 | aliyun-log SDK |
| `trace` | 调用链路查询 | 本地文档 + SLS |
| `chain` | 排查链路编排 | 内置引擎 |
| `dingtalk` | 钉钉聊天/文档/通讯录 | dws CLI |
| `ticket` | 云网络工单查询 | qt-expert API |
| `notify` | 通知触达查询(仅近7天) | roar noti-query |
| `db` | 只读 SQL 查询（双 backend） | DMS MCP（生产/受管实例） + PyMySQL 本地直连（日常/预发） |
| `skill` | Skill 安装/更新/状态/卸载 | 内置 |
| `version` | 版本与 CHANGELOG | 内置 |
| `errors` | 错误日志查看/清理 | 内置 |
| `doctor` | 配置体检(SLS 结构+实测存在性/活性) | 内置 + aliyun-log SDK |
| `config` | 统一配置管理(seek.json) | 内置 |

命令组、子命令与参数的实时清单以 `seek capabilities` 为准，本文不写死数量。

## 命令速查

### harness — Agent Harness 离线就绪检查

```bash
SEEK_HOME=/tmp/seek-case seek harness check
seek harness evaluate --scenarios ../harness/scenarios/v1.json
seek harness evaluate --scenarios scenarios.json --agent-command 'your-agent-runner'
```

检查隔离存储、内置配置、链路和模板、Skill/CLI 版本、可选外部命令与 HTTP host 风险；不发起网络请求。核心检查失败时返回 `HARNESS_NOT_READY`，可选依赖缺失只产生 warning。

`harness evaluate` 对版本化场景执行 protocol、trajectory、report 三层评测。省略 `--agent-command` 时使用场景中的 replay，适合离线 CI；指定命令时，每个脱敏场景通过 stdin 传给真实 Agent runner，并从 stdout 读取结构化结果。可重复传入 `--scenario <id>` 只运行子集。

`SEEK_HOME` 可覆盖 seek 自有配置、会话、日志、链路覆盖和版本标记根目录；未设置时保持 `~/.seek`。

### capabilities — 能力发现

```bash
# 输出所有命令的 JSON schema（agent 首次调用了解全部能力）
seek capabilities
```

### init — 必要集成初始化

```bash
seek init             # 仅检查本地安装/配置，不访问外部服务
seek init --verify    # 额外验证 A1 登录态和 DMS MCP tools/list；SLS 活性由 doctor 验证
```

输出字段包括 `ready`、`fully_ready`、逐项 `integrations`、`next_actions` 和安全提示。`fully_ready` 只表示 init 自己负责的检查完成，不代表 SLS 资源活性；SLS 具体 project/logstore 权限和活性继续使用 `seek doctor --liveness-window 24h` 验证。命令不会输出真实凭据。

### project — 项目管理

```bash
seek project list                    # 列出所有项目
seek project show <name>             # 查看项目详情
seek project add <name> [--desc ...] [--repo ...] [--a1-app ...] \
    [--sls-daily endpoint/project/logstore] [--sls-pre ...] [--sls-prod ...]
```

### deploy — 部署信息查询

```bash
seek deploy branch <project>                    # 查询应用部署信息
seek deploy info <project>                      # Aone 应用详情
seek deploy orders <project>                    # 部署单列表
seek deploy order <order_id>                    # 单个部署单详情
seek deploy changes <project>                   # 变更单列表
seek deploy env <project> [--env 日常]          # 指定环境部署信息(pipeline+分支+变更)
```

### sls — SLS 日志查询

```bash
# SQL 查询
seek sls query <project> --env <env> --query <sql> [--time 15m] [--max 100]  # --max 为每个查询目标 1-1000，--limit 为等价别名

# 快捷日志查询
seek sls logs <project> --env <env> [--level ERROR] [--keyword xxx] [--trace-id xxx] [--time 15m] [--max 100]  # 每个查询目标 1-1000

# 查看 SLS 配置
seek sls config <project> [--env <env>]
```

时间参数：`15m`/`1h`/`2d`（简写）或 `from,to`（unix 时间戳范围）。

环境别名：项目配置可声明 `envAliases`（如 `{"daily": "yanlian"}`），`--env daily` 会自动解析到真实环境；别名生效时输出带 `resolvedEnv` 标注，不会静默换环境。应急响应类项目（stability-locate/handle/agent-master）已预置 `daily → yanlian`。

### trace — 调用链路查询

```bash
seek trace call-chain <project>                          # 调用链路文档
seek trace query <project> --env <env> --trace-id <id>   # traceId 查询
seek trace topology                                       # 服务拓扑关系
```

### chain — 排查链路编排

```bash
seek chain list                              # 列出排查链路
seek chain show <name>                       # 查看链路详情
seek chain start <name> [--project ...] [--problem ...] [--context '{"flow_id":"FLOW-xxx"}']  # 开始排查会话
seek chain provide <session> --inputs '{...}'  # 向已建会话补注入首步输入
seek chain status <session>                  # 会话状态
seek chain step <session>                   # 当前步骤
seek chain complete <session> [--summary ...] [--outputs '{...}'] [--evidence '{...}'] [--token-usage '{...}']  # 完成步骤
seek chain validate <session> --step <N>    # 验证约束(防跳步)
seek chain amend <session> --step <N> [--summary ...] [--outputs '{...}'] [--evidence '{...}']  # 回填更正前序步骤
seek chain context <session>                # 累积上下文(含 evidence/amendments/token usage)
seek chain usage <session>                  # token 使用量汇总(仅统计，不参与评分)
seek chain report <session> --slug '<场景>-<ID片段>-<现象>'  # 生成报告文件名与模板头部(CLI 不落盘)
seek chain sessions [--limit 20]            # 最近会话
```

> **退出码约定**：`chain validate` 校验不通过（invalid）时返回非零退出码；`chain start` 首步输入缺键时报 `MISSING_CONTEXT`（非零退出码，不创建会话），所需键名见 `chain list` 的 `firstStepInputs`；`chain complete` 前引擎会自动重校验当前步骤约束，不通过则拒绝推进并返回非零退出码；`chain report` 对未完成会话返回 `SESSION_NOT_COMPLETED`，slug 非法返回 `BAD_SLUG`（须为小写 kebab-case、≤80 字符，且不得自带 `seek-report` 前缀、`YYYY-MM-DD` 日期前缀或 `.md` 后缀，CLI 会自动拼接）；`chain amend` 追加 correction 并保留该步原始 outputs。调用方可直接用 shell `&&` 串联。

内置链路（清单与步骤以 `seek chain list` / `seek chain show <name>` 为准，本文不写死数量）：
- `default` — 通用排查：定位服务→查询部署→查询日志→查询链路→异常/正常样本对比→分层归因
- `alert-enrichment` — 告警富化排查：来源路径→富化服务→管道检查→字段差异→根因
- `notification` — 通知未推送/内容错误：事件定位→上游拦截五件套→中断分叉→专项验证→根因/知识卡片
- `alert-ticket` — 告警工单排查（用户提供 flowId）：工单详情→分类校验→相似搜索→分支判断→相似分析→深入排查→定位人员→排查报告（含可直接沉淀到云网络工单的可复用排查路径、证据点与验证边界）
- `cron-task-health` — 定时任务健康巡检/回溯：定位任务→定位真实日志源→按天聚合触发→锁竞争与完成标记→失败收敛与结论
- `emergency-response` — 应急响应告警排查：判定业务类型→双级SLS入口→业务匹配→任务创建与推进→根因
- `emergency-stuck-task` — 应急卡单排障：判定卡单业务类型→定位卡住阶段→分支排查→跨系统对账→根因

> **报告模板**：链路完成后 `seek chain context` 输出 `report_template.path`，指向该链路的报告模板。`alert-ticket` 绑定工单专用模板（`ticket.md`，可通过链路定义 `reportTemplate` 字段显式指定），其余链路默认用通用模板（`generic.md`）。模板解析顺序为 `~/.seek/chains/templates/`（用户覆盖）→ `seek_cli/resources/chains/templates/`（运行时权威，`setup.py` 打包的副本）；仓库根的 `cli/chains/templates/` 是人类编辑镜像，必须与运行时副本一致（由 `tests/test_report_templates.py` 守护），只改镜像不会生效。

### dingtalk — 钉钉集成

```bash
seek dingtalk groups <query>                 # 搜索群聊
seek dingtalk messages --group <id> --time "yyyy-MM-dd HH:mm:ss" [--direction newer] [--limit 50]
seek dingtalk messages --user <userId> --time "..."
seek dingtalk search <query> [--group <id>] [--sender-ids <ids>] [--at-me]
seek dingtalk unread                         # 未读会话
seek dingtalk send --group <id> --text "..." [--title "..."]
seek dingtalk send --user <userId> --text "..."
seek dingtalk contact <query>                # 搜索联系人
seek dingtalk members --group <id>           # 群成员
seek dingtalk doc-read <url>                 # 读取钉钉文档
```

### ticket — 云网络工单查询

```bash
seek ticket search [--keyword xxx] [--status open] [--product QT] [--page 1]
seek ticket detail <flowId> [--user-id ...] [--dept ...]
seek ticket orders <flowId>                  # 关联工单
seek ticket lifecycle <flowId>              # 生命周期(处理记录)
seek ticket history <title>                 # 历史相似工单
seek ticket analyze <flowId> [--user-id ...] [--dept ...]  # AI聚合查询
```

`ticket analyze` 一条命令返回：详情 + 关联工单 + 生命周期 + 相似历史。

### notify — 通知触达查询

```bash
seek notify query <queryId>    # 按下游任务 ID 查投递状态(deliveryState 自动解读)
# 例: seek notify query ali-ivr-21d7aff3-3f8e-4572-83f9-3583cd659be2
```

注意：roar noti-query 仅保留**近 7 天**数据。输出含 `deliveryStateDesc`（内部状态码 1000~9000 与运营商回执码 200000~ 的中文解读）。

### 数据库查询 (DMS MCP + 本地直连)

双 backend 路由：**日常/预发优先本地直连，生产/受管实例走 DMS**。

```bash
# DMS 路径（生产/受管实例，database_id 寻址）
seek db tools                              # 列出 DMS 可用工具
seek db search "qt_monitor"               # 搜索数据库
seek db tables <database_id>              # 列出数据表
seek db schema <database_id> <table>      # 获取表结构
seek db query <database_id> --sql "SELECT ..."  # 执行只读 SQL（SELECT/WITH/EXPLAIN）

# 本地直连（日常/预发，profile 寻址，依赖 pymysql: pip install seek-cli[mysql]）
seek db conn add qt-stability-daily --type mysql --host 10.x.x.x --port 3306 \
    --database qt_stability --user qt_read --password 'env:QT_DB_PWD' \
    --project qt-stability --env daily    # 添加 profile（密码推荐 env:VAR 引用）
seek db conn list                          # 列出 profile（密码脱敏）
seek db conn test qt-stability-daily       # 连通性测试（SELECT 1）
seek db query --conn qt-stability-daily --sql "SELECT ..."
seek db query --project qt-stability --env daily --sql "SELECT ..."  # 按 bind 反查
seek db tables --conn qt-stability-daily
seek db schema --conn qt-stability-daily <table>
seek db conn remove qt-stability-daily
```

DMS 路径通过 `uvx alibabacloud-dms-mcp-server-inner` stdio JSON-RPC 通信，配置在 `~/.qoderwork/mcp.json`。
本地直连 profile 存储在 `~/.seek/config/db.json`（0600，`seek db conn` 管理）；两条路径均仅允许只读 SQL，绑定生产类环境的 profile 直连需显式 `--i-know-this-is-prod`，本地查询结果默认 500 行截断（`--max` 上限 5000）。

### Skill 管理

```bash
seek skill install                              # 安装到 ~/.qoder/skills/seek（符号链接）
seek skill install --dir ~/.qoderwork/skills   # 安装到 QoderWork
seek skill status                               # 检查安装状态
seek skill status --dir ~/.qoderwork/skills    # 仅检查指定目录
seek skill update                               # 修复/迁移所有安装点并核对版本声明
seek skill uninstall                            # 卸载（删符号链接，不删源码）
```

符号链接方式，源码更新后自动生效，无需重新安装。

`update`/`status` 输出契约：

- `data.version_consistency`：SKILL.md 的 `cli_version_ref` 与实际 `seek_cli.__version__` 交叉核对，`consistent` 三态（`true`/`false`/`null` 未声明）。漂移仅告警（message 追加说明、`up_to_date` note 标注），不改变 `status=ok` 与退出码。
- `data.source_dirty`：源码工作区是否有未提交改动，对齐标识据此可证伪。
- 单目录修复失败标 `status=error` 并继续处理其余目录；旧目录迁移备份成功但删除/建链失败标 `migration_failed` 并携带 `backup` 路径。

### 错误日志

```bash
seek errors list                                # 查看最近 20 条错误
seek errors list --limit 50 --command deploy   # 按命令过滤
seek errors clear                               # 清空错误日志
```

日志文件: `~/.seek/logs/errors.jsonl`（JSONL 格式，敏感键自动脱敏；嵌套上下文受深度、节点数和总大小预算限制，超限内容以截断标记记录）。

### 性能耗时日志

每次命令执行与集成 IO 自动记录耗时观测，用于定位排查链路慢在哪一步、慢在哪个环节：

- 日志文件：`~/.seek/logs/perf.jsonl`（JSONL 格式，敏感键打码、query/cmd/sql 截断 200 字符，写盘失败静默不影响命令）
- 字段：`timestamp`、`command`、`span`、`status`、`duration_ms`；设置环境变量 `SEEK_SESSION_ID` 时附带 `session_id`（链路会话内调用建议带上，用于命令→步骤归属）
- `span` 取值：`command`（单条 seek 命令端到端）、`sls_query`（SLS get_logs）、`a1_subprocess`（A1 子进程）、`dms_call`（DMS MCP 调用，含 server 冷启动）
- 归因：某步骤端到端耗时（session started_at/completed_at 差）− 该时间窗内 `span=command` 的 `duration_ms` 总和 ≈ LLM 与编排开销
- 开关：`seek config set options.perf_log false` 关闭；未配置时默认开启

聚合分析与清理：

```bash
seek perf report                                # 默认 24h 窗口聚合
seek perf report --time 7d                      # 支持与 SLS --time 同语法的时间窗
seek perf report --session <session_id>         # 按 chain 会话归属过滤
seek perf report --keyword sls                  # 按记录 command 字段子串过滤(大小写不敏感)
seek perf clear                                 # 清空耗时日志(返回清除条数)
```

report 输出：`commands`（命令级分组，按 totalMs 降序）、`ioSpans`（IO 级分组，按 span+目标组合键）、`sessions`（会话归属汇总，存在 session_id 记录时）、`totals.ioSharePct`（ΣIO/Σcommand 占比）与 `hint`（≥60% 建议 IO 并行/常驻复用，≤25% 建议命令批量化）。注意 IO span 嵌套于 command 区间内，占比为粗略近似，仅用于方向判断。

## 配置

### 项目配置

种子配置 `seek_cli/resources/config/projects.json`（运行时权威，`setup.py` 打包的副本；`cli/config/projects.json` 是人类编辑镜像，两者须一致）+ 用户覆盖 `~/.seek/config/projects.json`（按项目做字段级合并，`environments` 按环境名合并、同名环境整体替换）。

已预置项目清单与各项目的 SLS 环境以 `seek project list` / `seek project show <name>` 为准，本文不复制（会随配置漂移）。

### SLS 认证

按优先级自动读取：
1. 环境变量：`ALIBABA_CLOUD_ACCESS_KEY_ID` / `ALIBABA_CLOUD_ACCESS_KEY_SECRET`
2. `~/.seek/credentials.json`
3. `~/.aliyun/config.json`（阿里云 CLI 配置，自动读取）

### qt-expert 环境

默认连预发：`http://pre-qt-expert.aliyun-inc.com`，可通过环境变量 `QT_EXPERT_HOST` 切换。

### roar 环境

默认连：`http://roar.alibaba-inc.com`，可通过环境变量 `ROAR_HOST` 或 `~/.seek/config/roar.json`（`{"host": "..."}`）覆盖。noti-query 仅保留**近 7 天**数据。

### 统一配置（seek config）

所有配置推荐统一写到 `~/.seek/config/seek.json`，用 `seek config set/get` 管理：

```bash
seek config show                             # 全部配置项生效值与来源(secret脱敏)
seek config set sls.access_key_id LTAI...    # SLS 凭据
seek config set sls.access_key_secret xxx
seek config set hosts.expert http://...      # qt-expert host
seek config set hosts.roar http://...        # roar host
seek config set trace.topologyFile /path/to/service-topology.md
seek config set options.quiet_warnings true  # 抑制安全警告
seek config set options.perf_log false       # 关闭性能耗时日志
seek config unset hosts.roar                 # 删除(回退环境变量/旧文件/默认值)
seek config path                             # 配置目录与文件状态
```

读取优先级（各集成一致）：**环境变量 > seek.json > 旧文件（`credentials.json`/`expert.json`/`roar.json`/`trace.json`，继续兼容）> 默认值**。

## 初始化接入

首次安装、换机器或凭据变更后先运行：

```bash
seek init             # 仅检查本地安装和配置，不访问外部服务
seek init --verify    # 额外验证 A1 登录态和 DMS MCP tools/list
```

返回的 `integrations` 会分别给出 A1 CLI、DMS MCP、SLS 的 `status`、配置文档、操作步骤和验证命令；`next_actions` 只汇总当前缺失或尚未验证的动作。命令不会回显 AK/SK、Token 或 MCP 密钥。

- A1 CLI：按 <https://a1.io.alibaba-inc.com/docs/guide/> 安装，然后执行 `a1 auth login` 和 `a1 auth whoami --format json`。
- DMS MCP：按 <https://alidocs.dingtalk.com/i/nodes/EpGBa2Lm8aZxe5myCZYKkoYkWgN7R35y> 配置 `~/.qoderwork/mcp.json` 中的 `dms-mcp-server`，执行 `seek db tools` 验证。
- SLS：成对配置 `ALIBABA_CLOUD_ACCESS_KEY_ID` / `ALIBABA_CLOUD_ACCESS_KEY_SECRET`，或写入 `seek config set sls.access_key_id ...` 与 `sls.access_key_secret ...`；随后运行 `seek doctor --liveness-window 24h` 验证目标日志库。

## 集成依赖

| 集成 | 工具 | 认证 | 对应命令 |
|------|------|------|----------|
| A1 CLI | `a1`（PATH） | `a1 auth login`；[指南](https://a1.io.alibaba-inc.com/docs/guide/) | deploy |
| aliyun-log SDK | Python SDK | `~/.aliyun/config.json` | sls, trace query, doctor |
| dws CLI | `~/.qoderwork/bin/dws` | QoderWork 内置 | dingtalk |
| qt-expert API | HTTP | 无需认证(内网) | ticket |
| roar noti-query | HTTP | 无需认证(内网) | notify |
| DMS MCP | `uvx alibabacloud-dms-mcp-server-inner` | `~/.qoderwork/mcp.json`；[指南](https://alidocs.dingtalk.com/i/nodes/EpGBa2Lm8aZxe5myCZYKkoYkWgN7R35y) | db |

## 排查链路用法

### 典型排查流程

```bash
# 0. 首次使用或环境变化时检查必要接入
seek init

# 1. 查看可用链路
seek chain list

# 2. 开始排查会话
seek chain start default --project qt-monitor-ops --problem "告警通知未送达"

# 3. 查看当前步骤（含工具指引和 agentInstructions）
seek chain step <session_id>

# 4. 按步骤指引执行查询（deploy/sls/trace/ticket/dingtalk）

# 5. 完成步骤，提交输出到上下文，推进下一步
seek chain complete <session_id> \
  --summary "问题定位到qt-stability富化管道" \
  --outputs '{"target_project":"qt-stability"}' \
  --evidence '{"status":"FOUND","sources":[{"tool":"seek project list","reference":"project catalog"}],"boundary":"当前内置与用户项目配置"}' \
  --token-usage '{"input_tokens":120,"output_tokens":30}'

# 6. 验证是否可以跳到某步骤（约束检查）
seek chain validate <session_id> --step 3

# 7. 获取累积上下文
seek chain context <session_id>
```

### 证据与 Token 元数据

`chain step` 返回 `evidenceRequired=true` 时，`chain complete` 必须提供 `--evidence`。证据状态支持 `FOUND`、`NO_DATA`、`NOT_APPLICABLE`、`TOOL_ERROR`；所有状态必须填写 `boundary`，非 FOUND 必须填写 `reason`，FOUND/NO_DATA 必须提供至少一个包含 `tool` 与 `reference` 的 source。

`--token-usage` 可选记录 `input_tokens`、`output_tokens`、`cached_input_tokens`、`reasoning_tokens`；`chain usage` 汇总这些调用方上报值，当前仅统计、不参与评分。

### 链路约束

每条链路的步骤定义了约束：
- `must_be_first` — 必须是第一步
- `requires_step: N` — 必须先完成步骤 N
- `requires_all_previous` — 必须按顺序完成所有前置步骤
- `when` — 从 session context 读取字段并判断 equals/in/exists；不满足时自动 skipped
- `skipOutputs` — skipped 步骤写入下游所需的默认输出，不表示执行过查询

CLI 的 `chain validate` 命令会检查这些约束，防止 agent 跳步。

## Agent 接入

### 方式 1：Qoder Skill

安装 SKILL.md 到 Qoder skills 目录：

```bash
ln -s "$(pwd)/.." ~/.qoder/skills/seek
```

Agent 会通过 SKILL.md 了解触发条件、排查工作流和命令速查。

### 方式 2：动态发现

Agent 调用 `seek capabilities` 获取全部命令的 JSON schema，自行决定调用哪个命令。

### Agent 使用流程

```
用户: "qt-monitor-ops 日常环境告警通知未送达"
  ↓
Agent: seek capabilities           ← 发现能力
Agent: seek chain start notification --project qt-monitor-ops --problem "..."
  ↓
Agent: seek chain step <session>   ← 获取步骤指引
Agent: seek deploy env qt-monitor-ops --env 日常
Agent: seek sls logs qt-monitor-ops --env daily --level ERROR
Agent: seek dingtalk messages --group "cidxxx" --time "..."
  ↓
Agent: seek chain complete <session> --summary "..." --outputs '{...}' --evidence '{...}' [--token-usage '{...}']
  ↓
Agent: seek chain step <session>   ← 推进下一步
  ...（重复直到链路完成）
  ↓
Agent: seek chain context <session>  ← 获取上下文与 report_template.path，按模板输出排查报告
```

## 输出格式

```json
{
  "status": "ok",
  "data": { ... },
  "message": "人类可读摘要"
}
```

错误时：
```json
{
  "status": "error",
  "error": {
    "code": "NOT_FOUND",
    "message": "project 'xxx' not found"
  },
  "data": null
}
```
