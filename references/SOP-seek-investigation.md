# SOP — seek 排查作业标准流程

| 项 | 内容 |
|---|---|
| **适用症状** | 告警未送达、告警未生成应急任务、应急任务卡单、告警富化字段缺失、云网络工单排查、定时任务健康巡检、接口报错/服务异常等一切需要跨系统取证的排查作业 |
| **适用角色** | 值班同学、接手排查的开发/SRE、代跑排查的 AI agent（`/seek`） |
| **前置输入** | 现象描述（必填）；工单类需 `flowId`；富化类需 `alert_uuid_or_endpoint` |
| **证据来源** | `seek deploy` / `sls` / `trace` / `db` / `ticket` / `notify` / `dingtalk`，以及链路会话文件 `~/.seek/sessions/<session_id>.json` |
| **结论边界** | 本 SOP 只规范"怎么作业"，不替代场景知识；具体取证口径见 [`evidence-and-boundaries.md`](evidence-and-boundaries.md) 与 [`investigation-patterns.md`](investigation-patterns.md) |
| **校验时间 / 版本** | 2026-09-15 回归校验；seek CLI `0.11.0`、SKILL.md `0.12.0`、链路定义 `cli/seek_cli/resources/chains/default.json` |
| **关联文档** | [`../SKILL.md`](../SKILL.md)（契约原文）、[`command-reference.md`](command-reference.md)（命令参数）、[`../cli/TROUBLESHOOTING.md`](../cli/TROUBLESHOOTING.md)（按症状排错） |

---

## 0. 适用范围与豁免

### 0.1 必须走本 SOP

只要满足任一条，就必须建链路会话逐步执行，**不得直接敲排查命令**：

- 需要两个以上系统/数据源交叉取证（日志 + DB、日志 + 部署、工单 + 生命周期……）
- 需要给出根因结论、责任归属或修复建议
- 结论会进入工单、知识库、复盘或对外沟通
- 用户通过 `/seek <排查描述>` 显式发起

### 0.2 可豁免（只读单点查询）

用户明确只需要一个数据点、不涉及分析时，可直接调命令，无需建会话：

```bash
seek deploy branch qt-monitor-ops          # 只看部署分支
seek sls config qt-stability               # 只看 SLS 配置
seek ticket detail FLOW-xxx                # 只看工单详情
seek notify query <queryId>                # 只看投递状态
```

**豁免边界**：一旦从单点查询衍生出"为什么"，立即回到 0.1，补建会话；不得用一串豁免查询拼出根因结论。

### 0.3 硬约束优先级

本 SOP 与 [`../SKILL.md`](../SKILL.md) 冲突时，**以 SKILL.md 与 `cli/seek_cli/resources/chains/default.json` 为准**；命令参数与响应 schema 的实时权威来源是 `seek capabilities`，不是任何文档。

---

## 1. 作业前准备（Pre-flight）

### 1.1 环境与依赖自检

| # | 检查项 | 命令 | 通过标准 | 失败处置 |
|---|--------|------|----------|----------|
| 1 | 必要集成初始化 | `seek init` | A1 CLI、DMS MCP、SLS 均无缺失项 | 按 `next_actions` 和文档链接逐项配置 |
| 2 | 接入验证 | `seek init --verify` | A1 登录态、DMS MCP 工具发现通过 | 按返回的登录/授权步骤修复 |
| 3 | CLI 可启动 | `seek version` | 返回 `version` 与 CHANGELOG | 见 TROUBLESHOOTING §1.1/§1.2 |
| 4 | 命令 schema | `seek capabilities` | JSON 含全部命令与链路定义 | 文档与 CLI 不一致时以此为准 |
| 5 | 配置结构 | `seek doctor --no-live` | 无结构性报错 | 补齐缺失 environments/logstore |
| 6 | 配置实测 | `seek doctor --liveness-window 30d` | 无 `not_found` / `stale` | `not_found`=幻影配置，`stale`=已停写，两者都会造成"静默返 0" |
| 7 | 生效配置 | `seek config show` | secret 脱敏展示，来源清晰 | `seek config path` 查文件状态 |

> 排查中 SLS 查不到日志、或怀疑配置失效时，**随时重跑第 6 项**。配置文件的声明不能当证据——配置指向的 project/logstore 组合可能已失效。

### 1.2 依赖认证

| 集成 | 认证方式 | 支撑命令 |
|------|----------|----------|
| A1 CLI | `a1 auth login`；指南：<https://a1.io.alibaba-inc.com/docs/guide/> | `deploy` |
| aliyun-log SDK | `~/.aliyun/config.json`，或 `seek config set sls.access_key_id ...` | `sls`、`trace` |
| dws CLI | QoderWork 内置 | `dingtalk` |
| qt-expert API | 无需（内网） | `ticket` |
| DMS MCP | 按[集团版 DMS MCP 使用指南](https://alidocs.dingtalk.com/i/nodes/EpGBa2Lm8aZxe5myCZYKkoYkWgN7R35y)配置 `~/.qoderwork/mcp.json` | `db`（生产/受管实例） |
| PyMySQL 本地直连 | `~/.seek/config/db.json` + `env:VAR` 密码，需 `pip install seek-cli[mysql]` | `db`（日常/预发） |

配置读取优先级：**环境变量 > `~/.seek/config/seek.json` > 各自旧文件（credentials/expert/roar/trace.json）> 默认值**。

### 1.3 `seek` 不在 PATH 时的等价调用

未执行 `pip3 install -e .` 时，在仓库 `cli/` 目录下用模块方式等价调用，参数完全一致：

```bash
cd cli && python3 -m seek_cli chain list --format text
```

---

## 2. 链路选择

### 2.1 链路清单（与链路定义绑定校验）

| 链路 | 场景 | 首步输入键 | 输入来源 | 步骤数 | 报告模板 |
|------|------|-----------|----------|--------|----------|
| `default` | 通用排查（接口报错、服务异常） | `alert_or_error_description` | `--problem` | 6 | generic.md |
| `alert-enrichment` | 告警富化字段缺失/错误 | `alert_uuid_or_endpoint` | **必须 `--context`** | 5 | generic.md |
| `notification` | 通知未送达/内容错误 | `notification_description` | `--problem` | 5 | generic.md |
| `alert-ticket` | 云网络工单排查 | `flow_id` | **必须 `--context`** | 8 | ticket.md |
| `cron-task-health` | 定时任务健康巡检/回溯 | `cron_task_description` | `--problem` | 5 | generic.md |
| `emergency-response` | 告警未生成应急任务 | `alert_or_emergency_description` | `--problem` | 5 | generic.md |
| `emergency-stuck-task` | 应急任务卡单不推进 | `task_id_or_description` | `--problem` | 5 | generic.md |

**输入来源规则**：`_PROBLEM_DESCRIPTION_INPUTS` 集合内的 5 个描述型键（`alert_or_error_description`、`notification_description`、`cron_task_description`、`alert_or_emergency_description`、`task_id_or_description`）可由非空 `--problem` 满足；其余标识型键（`flow_id`、`alert_uuid_or_endpoint`）**只能由 `--context` 显式注入**，防止业务标识被描述文本冒充。

### 2.2 选择决策表

| 用户描述 | 链路 | 启动参数要点 |
|----------|------|-------------|
| 提供工单 flowId（FLOW-xxx）、"排查这个工单" | `alert-ticket` | `--context '{"flow_id":"FLOW-xxx"}'` |
| "告警没有生成应急任务"、"告警未触发应急响应" | `emergency-response` | `--problem` 写清告警来源与时间 |
| "应急任务卡住"、"任务不推进"、"卡单" | `emergency-stuck-task` | 有 task_id 时额外 `--context '{"task_id_or_description":"..."}'` |
| "配置改了不生效"、"脚本更新了还是旧的" | 先读 [`emergency-response-patterns.md`](emergency-response-patterns.md) 的「运维操作手册」排除缓存/merge 卡死 | 仍不能解释再走 `emergency-stuck-task` |
| "通知没收到"、"钉钉群没消息"、"电话没打通" | `notification` | `--problem` 含渠道、接收人、时间窗 |
| "告警字段缺失"、"富化字段不对"、"tag 为空" | `alert-enrichment` | `--context '{"alert_uuid_or_endpoint":"..."}'` |
| "定时任务有没有跑"、"任务执行了几次" | `cron-task-health` | `--problem` 含任务类名或关键词 |
| "接口报错"、"服务异常"、不确定 | `default` | `--problem` 贴原始报错 |

### 2.3 故障根因的对照归因门禁

故障调查必须回答两个不同问题：**哪里报错**，以及**为什么只有这个业务对象报错**。代码堆栈只能直接证明前者，不能自动证明代码是首要根因。

1. 固定异常样本：记录业务主键、发生时间、环境、部署版本和失败结果。
2. 选正常对照：优先取 1~3 个同环境、同版本、同业务类型、时间邻近的成功实例；只能跨环境/版本取样时必须写明干扰因素。
3. 横向比较：至少检查输入/DB 源数据、配置、关键中间状态、执行路径和结果，从第一处分叉点识别区分变量。
4. 检查反证：主动寻找能推翻当前解释的样本，例如“同样脏数据却成功”或“正常数据也失败”。
5. 分层归因：分别记录直接报错点、首要触发根因、次生容错/放大问题。

| 对照结果 | 归因类型 | 结论要求 |
|----------|----------|----------|
| 同代码/配置下，仅异常样本存在违反约束的数据差异，且修正后成功或可等价复现 | `DATA_SOURCE_PRIMARY` | 数据源为首要根因；代码若报错不清晰，另记容错缺口 |
| 输入合法且与正常样本等价，仍由特定代码路径稳定失败 | `CODE_PRIMARY` | 代码为首要根因 |
| 异常数据触发，同时代码按契约本应拒绝/降级却放大成二次故障 | `DATA_CODE_INTERACTION` | 同时给出数据治理和代码加固措施 |
| 外部系统状态/返回差异是唯一稳定变量 | `EXTERNAL_DEPENDENCY_PRIMARY` | 明确外部依赖及本系统防护责任 |
| 无正常样本、无异常时刻快照，且无直接复现/修正前后验证 | `INSUFFICIENT_EVIDENCE` | 只能确认直接报错点和候选原因，禁止确定性归因 |

用户口述“某条 DB 数据写错”属于高优先级线索；必须通过只读查询、审计记录、正常样本对照或修正前后结果验证后，才能升级为报告中的已证实根因。

### 2.4 选错链路的处置

链路走到中途发现选错：**不要弃会话重开**（会丢失已取证上下文）。

1. `seek chain status <session>` 确认当前进度
2. 若已完成步骤的输出对新链路无用 → 新建正确链路会话，并在报告「未决事项」注明前一会话 ID 与放弃原因
3. 若只是某步结论错 → 用 `seek chain amend`（见第 6 节）回填更正，继续沿原链路走完

---

## 3. 标准作业流程（Step 0–10）

```text
Step 0: seek init                                → 首次使用/环境变化时检查 A1、DMS MCP、SLS 接入
Step 1: seek chain list                          → 选择链路
Step 2: seek chain start <name> --project <p> --problem "..." [--context '{...}']
Step 3: seek chain step <session>                → 读当前步骤指引（含 agentInstructions）
Step 4: seek chain validate <session> --step <N> → 验证约束（必须 valid）
Step 5: 按指引执行取证命令（deploy/sls/trace/db/ticket/notify/dingtalk）
Step 6: seek chain complete <session> --summary "..." --outputs '{...}'
Step 7: 重复 Step 3~6 直到链路 completed
Step 8: seek chain context <session>             → 取完整上下文（含 amendments）
Step 9: seek chain report <session> --slug '<场景>-<ID片段>-<现象>'
Step 10: 按返回模板结构写报告全文，用返回的 filename 落盘
```

### 3.1 Step 0–2：初始化并建会话

```bash
seek init
# 按 next_actions 完成缺失配置；需要主动验证时：
seek init --verify

seek chain start alert-ticket --project qt-expert \
  --problem "VPC 路由表查询接口报错，工单 FLOW-xxx" \
  --context '{"flow_id":"FLOW-xxx"}'
```

- **前置校验**：首步输入缺键时直接返回 `status=error`、`code=MISSING_CONTEXT`，data 含 `missing_inputs` / `required_inputs` / `hint`，且**不创建会话**。此时补 `--context` 重试，不要先建会话再补。
- **键名冲突**：`--context` 的键不得与步骤名冲突，否则报 `BAD_CONTEXT`。
- 会话已建但需要补注入时用 `seek chain provide <session> --inputs '{...}'`，**禁止重建会话**。

### 3.2 Step 3–6：单步循环（每步必做四件事）

| 动作 | 命令 | 判读要点 |
|------|------|----------|
| ① 读指引 | `seek chain step <session>` | 看 `name`、`requiredInputs`、`outputs`、`agentInstructions`；**不要提前加载其他场景知识** |
| ② 验约束 | `seek chain validate <session> --step <N>` | 必须 `valid`；返回 invalid 时**进程退出码非零**（`code=VALIDATION_FAILED`，data 含 `valid` 字段），不得执行该步骤 |
| ③ 取证 | 按指引执行 seek 命令 | 记录命令、查询条件、时间窗、关键字段——这些是报告的证据编号来源 |
| ④ 提交 | `seek chain complete <session> --summary "..." --outputs '{...}'` | `chain complete` 前引擎会自动重校验当前步骤约束、outputs 声明与 requiredInputs 的声明生产者，不通过则拒绝推进 |

### 3.3 `--outputs` 提交规范

引擎强校验，以下任一条不满足都会被拒绝推进：

1. 必须是 **JSON 对象**（否则 `BAD_JSON`）
2. 字段必须**属于当前步骤声明的 outputs**，不得夹带未声明字段
3. 声明的字段**必须全部提交**，一个都不能少
4. 没有结果或分支不适用时，**显式提交空值** `""` / `[]` / `{}`，不得省略键
5. `requiredInputs` 只能由其**声明生产步骤**实际提交的 outputs 提供，不能用其他步骤的同名字段或初始 `--context` 冒充

**已知易错点**：

- `default` 链路 step 2 (`query-deploy`) 的 outputs 含 `environment`，complete 时必须输出（daily/pre/prod），否则 step 3 (`query-logs`) 的 complete 被阻断。
- `alert-ticket` step 5（无相似工单时）与 step 6（监控类路径下无 `app_owner`/`interface_owner` 时）必须显式输出 `[]`/`""`，否则 step 7 的 requiredInputs 校验阻断。
- `alert-ticket` step 5 的"常处理人"只能统计已搜到的相似工单 lifecycle 中处理人的重合度——`seek ticket search --keyword` 仅支持**标题**搜索，无法按处理人反查其名下工单。

### 3.4 Step 7–10：收尾与出报告

- **全部步骤完成后才能出报告**。`seek chain status <session>` 的 `completed` 字段是判据；未完成即声明排查完成属违规。
- `seek chain context <session>` 返回累积上下文（含 `amendments`）与 `report_template.path`。
- 读取模板：`alert-ticket` 用 `cli/chains/templates/ticket.md`，其余链路用 `generic.md`；可用 `~/.seek/chains/templates/` 同名文件覆盖。
- `seek chain report <session> --slug '...'` 生成文件名与头部，**CLI 不落盘**，落盘由作业方完成。

---

## 4. 硬约束与引擎阻断信号

| # | 约束 | 操作化动作 | 违反时的表现 | 处置 |
|---|------|-----------|-------------|------|
| 1 | 必须先建会话 | 任何 deploy/sls/trace/ticket/dingtalk 排查命令前先 `chain start` | 无引擎拦截，属作业违规 | 补建会话并重走取证，报告注明 |
| 2 | 必须逐步执行 | 每步 `chain step` → 执行 → `chain complete` | `step N requires step M to be completed first` | 回到 `chain step` 确认当前步 |
| 3 | 必须验证约束 | 执行前 `chain validate --step N` | 退出码非零 + `VALIDATION_FAILED` | 按 `reason` 补齐前置，禁止跳过 |
| 4 | 必须累积上下文 | 每步 `--outputs` 提交全部声明字段 | complete 被拒 | 补交空值或回到生产步骤 amend |
| 5 | 走完才能出报告 | `chain status` 确认 completed → `chain context` → `chain report` | `chain report` 返回 `SESSION_NOT_COMPLETED` | 继续完成剩余步骤 |
| 6 | 跨 region 铁律 | 查不到 ≠ 不存在：`sls config` 看全部 environments/logstore + `env_aliases` → 至少扫杭州/上海两个 region → 仍无果才记为限制 | 无引擎拦截，属结论违规 | 结论必须写"杭州 region 下未发现"而非"未接入" |
| 7 | 故障根因必须横向对照 | 比较异常样本与同环境/版本/业务类型的正常样本，检查数据、配置、状态和路径差异 | default 链路 evidence 步骤阻断；其他链路属结论违规 | 无对照/复现时归因 `INSUFFICIENT_EVIDENCE` |
| 8 | 错误结论必须全链路更正 | `chain amend <session> --step N` 回填 | 无引擎拦截 | 报告「更正记录」写清何时/因何/更正了什么，相关记忆同步更正 |

**约束 6 补充**：别名生效时结果带 `resolvedEnv` 标注（如应急响应项目 `daily → yanlian`），据此确认真实查询环境；口语环境与配置错位时先看 `sls config <project>` 全量输出的 `env_aliases`。

---

## 5. 报告产出规范

### 5.1 文件名与 slug

| 类型 | 文件名格式 |
|------|-----------|
| 单案例 | `seek-report-{YYYY-MM-DD}-{场景}-{业务ID片段}-{现象}.md`（无唯一业务标识时省略 ID 段） |
| 多篇汇总 | `seek-reports-digest-{起始YYYY-MM-DD}-to-{结束YYYY-MM-DD}.md` |

slug 校验规则（违反返回 `BAD_SLUG`）：

- 必须匹配 `^[a-z0-9]+(-[a-z0-9]+)*$`，即小写 kebab-case 段以 `-` 连接
- 长度 ≤ 80 字符
- **不得**自带 `seek-report` 前缀、`YYYY-MM-DD` 日期前缀、`.md` 后缀——CLI 自动拼接，自带会造成双重前缀

```bash
seek chain report <session> --slug 'batch-560d6f3c-objectlist-empty'
# 返回 {session_id, chain_name, report_date, slug, filename, template, header_markdown}
```

**落盘文件名与报告头部机器字段必须直接使用返回值，禁止手写日期前缀与头部。**

### 5.2 落盘与归档

同目录平铺存放，**不按日期建子目录**。报告落盘到本次排查的归档目录（与既有 `seek-report-*.md` 同级）。

### 5.3 必含章节

按模板结构输出，其中「**可复用排查路径与证据点**」为强制章节，用于沉淀可直接录入工单/知识库的排查逻辑，须覆盖：

| 要素 | 要求 |
|------|------|
| 适用问题特征 | 现象/错误码/API/模块关键词，以及后续复用搜索关键词 |
| 前置条件 | project、env、时间范围、traceId/uuid/任务ID、权限与依赖 |
| 步骤与命令 | 每步：排查目标、命令/系统、输入条件、必采证据、判断与下一步 |
| 关键证据 | 编号（E1/E2…）+ 来源命令 + 查询条件与时间范围 + 关键字段值 + 支撑的判断 |
| 分支判断 | 证据条件 → 判断 → 后续动作/结论 → 证据编号 |
| 结论映射与验证边界 | region、环境、时间窗、数据留存范围；哪些可直接复用、哪些需重新验证 |

**红线**：该章节只记录本次实际执行且证据闭环的路径；未经验证的推测只能进入「未决事项」。

**「未决事项」边界**：仅限因权限/外部依赖无法获取的信息。**应在本次排查完成但遗漏的排查项不得放入未决事项，必须回头补查。**

### 5.4 固定证据铁律（按问题类型）

- **通知类**：`deliveryState` 是 Roar 返回的平台投递状态；运营商状态码从 `output` 字段提取（如 `output="fail:200005"`，`200005` 才是运营商回执码）。两者分别记录，不得混为同一证据。
- **日志查询类**：关键词返 0 条时必须记录 warnings/indexCheck 与 logstore 活性验证结果，禁止直接下"未执行/无数据"结论。
- **跨 region 类**：单 region/单 logstore 扫描不得下"未接入"结论，必须写明验证边界。

---

## 6. 更正与回填（amend）

排查后期发现前序步骤结论有误时：

```bash
seek chain amend <session> --step 3 --summary "更正：..." --outputs '{...}'
```

- amend **追加 correction，保留原始 outputs**，`chain context` 的 `amendments` 可见完整轨迹
- 报告「更正记录」章节必须写清三要素：**何时发现、因何更正、更正了什么**，并列出更正依据与影响范围
- 相关记忆/知识库条目同步更正并标注验证边界
- 无更正时「更正记录」写"无"，不得删除该章节

---

## 7. 会话续作与交接

| 场景 | 命令 | 说明 |
|------|------|------|
| 找最近会话 | `seek chain sessions --limit 20` | 返回会话列表与 problem 摘要（前 100 字） |
| 看进度 | `seek chain status <session>` | `completed` 字段判断是否走完 |
| 恢复到当前步 | `seek chain step <session>` | 会话已 completed 时返回 `SESSION_COMPLETED` |
| 取全部上下文 | `seek chain context <session>` | 含每步 outputs 与 amendments |

会话文件存储在 `~/.seek/sessions/<session_id>.json`。交接时提供 **session_id + `chain context` 输出**，不要只给口头结论。

---

## 8. 错误码速查与处置

管道契约：**stdout 恒为可解析 JSON、退出码非零即错**。参数解析失败也会向 stdout 输出 `code=ARGPARSE_ERROR` 的 JSON（usage 走 stderr）并返回退出码 2。

| code | 触发场景 | 处置 |
|------|----------|------|
| `MISSING_CONTEXT` | `chain start` 首步输入缺键 | 按 data 的 `missing_inputs`/`hint` 补 `--context` 重试；会话未创建 |
| `BAD_CONTEXT` | `--context` 键与步骤名冲突 | 改名或改用其他注入键 |
| `BAD_JSON` | `--context`/`--inputs`/`--outputs` 非合法 JSON 或非对象 | 校验 JSON；注意 shell 引号转义 |
| `VALIDATION_FAILED` | `chain validate` 不通过（退出码非零） | 按 `reason` 补齐前置步骤/输入，禁止跳过 |
| `SESSION_NOT_COMPLETED` | 对未完成会话调 `chain report` | 先完成剩余步骤 |
| `SESSION_COMPLETED` | 对已完成会话调 `chain step` | 用 `chain context` 取结果，或新建会话 |
| `SESSION_ERROR` | 会话状态/推进异常 | `chain status` 查进度，必要时看会话 JSON |
| `NOT_FOUND` | 链路/会话不存在 | `chain list` / `chain sessions` 核对名称 |
| `CHAIN_NOT_FOUND` | `chain start` 链路名错 | `chain list` 取准确链路名 |
| `CHAIN_CONFIG_ERROR` | 链路定义/模板配置错 | 检查 `cli/seek_cli/resources/chains/default.json` 与模板文件 |
| `BAD_SLUG` | slug 非法 | 按 §5.1 规则改小写 kebab-case，去掉日期/前缀/`.md` |
| `CONFIG_ERROR` | 配置读写失败 | `seek config path` / `seek config show` |
| `ARGPARSE_ERROR` | 参数解析失败（退出码 2） | 看 stderr usage；`seek capabilities` 核对参数 |
| `INTERNAL_ERROR` | 未预期异常 | `python3 -m seek_cli <command> 2>&1` 看原始错误；`seek errors list` 查最近报错 |

本表只覆盖**链路与会话层**错误码。命令层专属码按症状查 [`../cli/TROUBLESHOOTING.md`](../cli/TROUBLESHOOTING.md) 对应小节：依赖与认证（`a1 CLI not found`、`No SLS credentials found`、`mcp.json not found`、`dws CLI not found`、`ticket API 5xx`）见 §1~§6；db 本地直连的 `DB_ERROR`/`DB_STORE_ERROR`/`PROD_DIRECT_CONNECT_FORBIDDEN`/`READ_ONLY_SQL_REQUIRED` 见 §4.5~§4.8；notify 的 `ROAR_API_ERROR` 与 7 天留存边界见 §8；config/doctor/skill 的 `BAD_CONFIG_KEY`/`DOCTOR_ISSUES`/`DOCTOR_INCOMPLETE` 见 §9。

---

## 9. 常见误判清单（取证红线）

| # | 误判 | 正确做法 |
|---|------|----------|
| 1 | SLS 单 region 查不到就写"未接入 SLS" | 跨 region 铁律：`sls config` 看全部 environments/logstore → 至少扫杭州/上海 → 结论标注验证边界 |
| 2 | 关键词检索返 0 条 = 事件未发生 | 含连字符/驼峰的 uuid 必须 SQL `like` 全扫描兜底；查 warnings/indexCheck 与 logstore 活性 |
| 3 | 接口返回 `Success` = 通知已送达 | `Success` 只表示请求被受理；必须查 `seek notify query <queryId>` 的 `deliveryStateDesc` |
| 4 | `notify` 查不到 = 没投递 | 仅能查近 **7 天**；超期属数据留存边界，不能反推 |
| 5 | `dingtalk messages` 返 0 条 = 命令有 bug | `--time` 语义是"从该时间点往现在拉"，不是"最近 N 条"；用宽时间窗（如 `"2024-01-01 00:00:00"`） |
| 6 | 配置文件里写了 project/logstore = 存在 | 配置声明不是证据，用 `seek doctor` 实测 |
| 7 | 只看 SLS 顶层 `count` | 多 logstore 环境必须检查 `byLogstore`、`truncatedLogstores`、`errors` |
| 8 | `--env daily` 一定查日常 | 存在 `envAliases`（如 `daily → yanlian`）；看结果的 `resolvedEnv` 字段确认真实环境 |
| 9 | 本地直连能查生产 | 双 backend 路由：日常/预发本地直连（`--conn`），生产/受管实例走 DMS（`database_id`）；生产直连需显式 `--i-know-this-is-prod` |
| 10 | DB 结果就是全量 | 仅允许只读 SQL（SELECT/WITH/EXPLAIN）；本地直连默认 500 行截断（`--max` 上限 5000），看 `truncated` 字段 |
| 11 | 页面显示"未匹配"/"未处理" | 可能只是异步状态未刷新；必须有代码或 DB 证据才能定根因 |
| 12 | 环境不明时混查 | `daily`/`yanlian` 的 `app.env` 都可能是 `DAILY`，必须用部署单元 + 数据源 endpoint 联合区分 |

---

## 10. 禁止事项

| 禁止 | 原因 |
|------|------|
| 未建会话直接执行排查命令 | 违反 seek 核心设计理念，上下文无法累积与追溯 |
| 跳过 `chain validate` 或忽略其非零退出码 | 约束不满足时取证结果不可信 |
| 省略 `--outputs` 声明字段或用 null 代替空值 | 引擎阻断推进；空值必须显式 `""`/`[]`/`{}` |
| 用初始 `--context` 冒充后续步骤的 requiredInputs | 破坏声明生产者链，结论无法追溯 |
| 未完成全部步骤即声明排查完成 | 违反硬约束 5 |
| 手写报告文件名日期前缀或头部机器字段 | 必须用 `chain report` 返回值，避免双重前缀与格式漂移 |
| 把未验证推测写进「可复用排查路径」 | 污染知识库，误导后续复用 |
| 把遗漏的排查项写进「未决事项」 | 未决事项仅限权限/外部依赖导致无法获取的信息 |
| 发现前序结论有误却不 amend | 违反硬约束 7，错误结论会随上下文扩散 |
| 在文档中复制具体群 ID、历史查询结果、未经验证的命令参数 | 知识腐化；这类内容属于单次报告，不属于 SOP |

---

## 11. 附录：`notification` 链路完整作业示例

以"qt-monitor-ops 日常环境告警通知未送达钉钉群"为例，命令序列与每步必交 outputs：

```bash
# Step 0-1：选链路 + 建会话
seek chain list
seek chain start notification --project qt-monitor-ops \
  --problem "日常环境 P2 告警未推送到齐天告警群，2026-09-08 10:00~11:00"

# Step 2-5：step 1 locate-notification-event
seek chain step <session>
seek chain validate <session> --step 1
seek sls logs qt-monitor-ops --env daily --level ERROR --time 1h
seek chain complete <session> --summary "定位为钉钉群渠道，事件键 xxx" \
  --outputs '{"channel_type":"dingtalk_group","target_recipient":"齐天告警群","environment":"daily","event_time_range":"2026-09-08 10:00:00,2026-09-08 11:00:00","notification_event_key":"<uuid>"}'

# step 2 check-interception-five-signals（上游拦截五件套）
seek chain validate <session> --step 2
seek chain complete <session> --summary "..." \
  --outputs '{"notification_group_evidence":"...","manual_silence_evidence":"...","auto_silence_evidence":"...","drop_evidence":"...","interception_type":"...","interception_rule_owner":"..."}'

# step 3 branch-notification-path
seek chain validate <session> --step 3
seek chain complete <session> --summary "..." \
  --outputs '{"delivery_branch":"...","branch_rationale":"..."}'

# step 4 verify-notification-branch
seek chain validate <session> --step 4
seek notify query <queryId>          # 仅近 7 天
seek chain complete <session> --summary "..." \
  --outputs '{"upstream_rule_evidence":"...","notice_service_evidence":"...","downstream_delivery_evidence":"...","recipient_schedule_evidence":"...","template_evidence":"..."}'

# step 5 conclude-notification-root-cause
seek chain validate <session> --step 5
seek chain complete <session> --summary "..." \
  --outputs '{"root_cause":"...","fix_suggestion":"...","evidence_boundary":"...","notification_knowledge_card":"..."}'

# Step 7-9：出报告
seek chain status <session>          # 确认 completed
seek chain context <session>
seek chain report <session> --slug 'notify-qtmonitorops-dingtalk-not-delivered'
# 用返回的 filename 落盘，如 seek-report-2026-09-08-notify-qtmonitorops-dingtalk-not-delivered.md
```

无结果的证据字段（如未命中人工静默）提交 `""`，不得省略键。

---

## 12. 文档维护

- 本 SOP 描述作业流程，**不承载命令参数表与场景案例**：参数变更改 [`command-reference.md`](command-reference.md) 与 `commands/capabilities.py`；场景经验改 [`investigation-patterns.md`](investigation-patterns.md) / [`emergency-response-patterns.md`](emergency-response-patterns.md)；按症状排错改 [`../cli/TROUBLESHOOTING.md`](../cli/TROUBLESHOOTING.md)。
- 链路步骤、`requiredInputs`、`outputs`、`constraints` 的机器定义以 `cli/seek_cli/resources/chains/default.json` 为运行时权威（`cli/chains/default.json` 是人类编辑镜像，两者须一致，只改镜像不生效）。本 SOP §2.1 链路清单表由 `cli/tests/test_doc_consistency.py` 与该定义绑定校验：链路名集合、步骤数、首步输入键、输入来源（`--problem` 还是 `--context`）与报告模板任一项不符即测试失败，按失败信息改表即可。
- 本文不得写死链路条数、项目数、命令组/子命令数等会漂移的数量，一律指向 `seek chain list` / `seek project list` / `seek capabilities`；同一测试会拦截硬编码计数。
- 契约原文（触发规则、硬约束、链路选择）以 [`../SKILL.md`](../SKILL.md) 为准；本 SOP 是其人可执行的操作化展开，二者冲突时以 SKILL.md 为准。
- 修改本文件后：更新头部「校验时间 / 版本」，并跑 `cd cli && python3 -m unittest tests.test_doc_consistency tests.test_documentation`（守护相对链接可解析与引用一致）。
