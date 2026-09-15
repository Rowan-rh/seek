# 应急响应排查模式

本页按应急平台运行链和故障场景按需加载。它提供排查路径和已知故障模式，不替代 `seek chain` 的步骤约束。

## 应急平台四条运行链

应急平台不是单一链路，而是四条可识别运行链共存：

| 运行链 | 入口标识 | 运行主对象 | 执行链 |
|---|---|---|---|
| 1.0 legacy | `FaultModelChannel`、`emergency_event` | legacy 事件与定位任务 | locate → master/AG → `stability-handle` → 旧变更 |
| 原始 2.0 | `TriggerChannel`、`EmergencyScene` | fresh `EmergencyTask` | locate → master/AG → 决策/流控 → 变更 |
| 根因型 2.5 | `SceneModelChannel`、预警项/场景模型/响应预案 | 复用 fresh `EmergencyTask` | 新入口匹配 → 复用 2.0 后半链 |
| 指令型 standard | `QuickRecoveryTemplate` | `QuickRecoveryTask` | locate → 新变更 → PostCheck |

三个责任仓：`stability-locate`（核心控制面）、`stability-agent-master`（任务调度）、`stability-handle`（1.0 legacy 逃逸与旧变更适配）。

**判定规则**：
- 1.0：命中 legacy `emergency_event`/`exception_calculate_task`，或页面入口为 `emergency_response_system`(POP)
- 原始 2.0：`emergency_task.emergency_scene_uuid` 命中 `emergency_scene.uuid`
- 根因型：`emergency_task.emergency_scene_uuid` 命中 `emergency_response_plan.uuid`
- 指令型：命中 `quick_recovery_template`/`quick_recovery_task`/`outer_executable_task`

**2.0 direct/manual 分支**：人工从方案市场直接启动时，可能跳过 SLS、窗口、场景匹配和 `EmergencyTask`，从 fresh `EscapeTask` 或批次对象进入聚合与新变更。排查时应明确写成"2.0 direct/manual"，不与告警自动链混为一谈。关联键：`escape_task / escape_batch_uuid → change_compile_task.escape_task_uuid → change_compile_task.aggregate_uuid → escape_aggregate_task.uuid`，可以没有 `emergency_task_uuid` 和 `window_uuid`。

## 自动触发链的双级 SLS 入口

1.0、2.0、根因型的自动触发不是"监控事件直接进入业务匹配"，而是经过同一应用内的两个 Worker 角色：

```text
上游监控事件源
  → Transit Worker（按 trigger key 过滤）
  → 应急中间 Logstore
  → 主 Consumer Worker（转 EventFastLog）
  → SpecialPcapChannel → TriggerChannel → SceneModelChannel → FaultModelChannel
```

| 角色 | 做什么 | 运行开关 |
|---|---|---|
| Transit | 合并启用的 1.0 trigger、2.0 scene、根因型 early-warning item 和 PCAP 特殊告警，按事件 key 过滤并转写 | hostname alias 命中 `monitor.sls.transit` |
| 主 Consumer | 把中间流转为 `EventFastLog`，进入四段业务责任链 | hostname alias 命中 `monitor.sls.consumer` |

**当前运行实证**：
- `daily`/`pre` 不启动这两个 Worker
- `yanlian` 单实例已有双 Worker 启动实证
- 生产三实例配置为双角色

**排障断点**：
- 原始源有、中间流无：停在 Transit 角色、trigger key 过滤、第一段 checkpoint 或转写
- 中间流有、首个业务对象无：停在主 Consumer 角色、第二段 checkpoint、解析或责任链
- 两段 ConsumerGroup 即使同名也因 Project/Logstore 不同而独立，checkpoint 不共享

**ConsumerGroup 名称**：
- yanlian：`stability_locate_daily`（两段各一个独立 ConsumerGroup）
- 生产：`stability_locate_prod`（两段各一个独立 ConsumerGroup）

### SLS 事件流 Project/Logstore 映射

下表的条目已全部录入 `projects.json` 并经 `seek doctor` 实测存在，优先用配置模式查（`seek sls query <project> --env <env>`），不要手写 `--endpoint/--sls-project/--logstore` 直查。

| 阶段 | 环境 | Project | Logstore | seek 入口 |
|---|---|---|---|---|
| 上游监控事件源 | 生产 | `qt-stability-cn-hangzhou` | `stability-monitor-event` | `qt-stability --env prod` |
| 上游监控事件源 | 日常/演练 | `qt-monitor-cn-beijing` | `yanlian_qt_stability_event_source` | `qt-stability --env daily` |
| 应急中间 Logstore | 生产 | `qt-nfv-recovering-center` | `stability-locate-event` | `stability-locate --env prod` |
| 应急中间 Logstore | 日常/演练 | `qt-nfv-recovering-center` | `stability-locate-event-test` | `stability-locate --env yanlian` |
| qt-stability 标准事件 | 预发/生产 | `qt-monitor-cn-shanghai` | `qt-stability-event` | `qt-stability --env prod` |
| qt-stability 标准事件 | 日常 | `qt-monitor-cn-shanghai` | `qt-stability-event-daily` | `qt-stability --env daily` |
| qt-stability 处理过程 | 预发/生产 | `qt-monitor-cn-shanghai` | `qt-stability-event-process` | `qt-stability --env prod` |
| qt-stability 处理过程 | 日常 | `qt-monitor-cn-shanghai` | `qt-stability-event-process-daily` | `qt-stability --env daily` |
| 监控推送 | 生产 | `qt-monitor-cn-shanghai` | `amr-pushgateway` | 未入配置，直查 |
| 监控推送 | 日常 | `qt-monitor-cn-shanghai` | `amr-pushgateway-daily` | 未入配置，直查 |

注意：`qt-stability --env prod` / `--env daily` 会一次扇出多个 logstore（跨 region），结果按 `byLogstore` 分源返回；判断"某级没有"时必须看对应源的条数，不能看总数。

### 老应急应用运行日志

| 应用 | 日常/演练 | 预发 | 生产 |
|---|---|---|---|
| locate 事件 | `qt-monitor-cn-beijing/qt_stability_locate_event_yanlian` | `qt-monitor-cn-beijing/qt_stability_locate_event_pre` | `qt-monitor-cn-beijing/qt_stability_locate_event_prod` |
| handle 事件 | `qt-monitor-cn-beijing/qt_stability_handle_event_yanlian` | `qt-monitor-cn-beijing/qt_stability_handle_event_pre` | `qt-monitor-cn-beijing/qt_stability_handle_event_prod` |
| master 任务 | `qt-monitor-cn-beijing/stability_agent_master_yanlian` | 与生产共享 `stability_agent_master_prod` | `qt-monitor-cn-beijing/stability_agent_master_prod` |
| handle 重试 | `qt-monitor-cn-shanghai/qt_stability_handle_retry_log_yanlian`（**已 stale**） | 与生产共享 | `qt-monitor-cn-shanghai/qt_stability_handle_retry_log_prod` |
| handle 逃逸 | `qt-monitor-cn-shanghai/qt_handle_escape_sls_yanlian` | 与生产共享 | `qt-monitor-cn-shanghai/qt_handle_escape_sls_prod` |

注意：
- master 预发与生产共享同一个 SLS logstore (`stability_agent_master_prod`)，命中日志不能直接当生产证据
- `qt_stability_handle_retry_log_yanlian` 于 2026-08-21 实测近 30d 零日志，logstore 存在但已停写；在此查不到不能写成"演练未重试"
- handle 预发只有独立的事件 logstore，重试与逃逸需到 `--env prod` 查

### ZooRoute / qt-scheduler-center

| 环境 | Project | Logstore | seek 入口 |
|---|---|---|---|
| 预发 | `qt-nfv-recovering-center` | `qt-schedule-center-pre` | `qt-scheduler-center --env pre` |
| 生产 | `qt-nfv-recovering-center` | `qt-schedule-center-prod` | `qt-scheduler-center --env prod` |

仓库 `qt-scheduler-center` 不在本地 workspace，代码级取证需先拉取仓库。它与应急中间 Logstore 同处一个 SLS project，不要把两者混为一条链路。

## 根因型专用排查路径

根因型配置主线：

```text
stability-monitor 告警项
→ EarlyWarningItem（用 identifier&category 匹配告警 type&component）
→ EmergencySceneModel
→ EmergencyResponsePlan（ONLINE 状态）
→ EscapeMatchPolicy（scene_uuid=plan.uuid 反向关联）
→ EscapeSolution（固定绑定）
```

**关键检查点**：
1. 告警 `type&component` 是否精确等于预警项 `identifier&category`
2. 预警项是否关联 ONLINE 预案
3. 根因来源：告警内嵌 `diagnoseResult.code` 还是 `diagnosticFlag` 指向的 QtDiagnose 任务
4. `rootCauseCode=certain_alarm` 可直接进入默认分支；具体 Code 必须来自诊断结果
5. 存在具体根因策略但两种输入都缺失时，代码可能因根因 Map 为空异常

**决策模式**：
- `ALWAYS`：总是等待人工
- `NEVER`：不等待人工
- `AMBIGUOUS`：仅在根因分组数 > 1 时等待人工
- 为空或非法时回退 `ALWAYS`

**通知差异**：
- 原始 2.0 Scene：变更失败/人工决策发送钉钉 + Qt 事件
- 根因型 Plan：当前仅发送钉钉，不创建 Qt 事件

### 预警项字段消歧

预警项表单有两组都叫“组件”的字段，语义完全不同：

| 页面字段 | 运行语义 | 排障要点 |
|---|---|---|
| 告警项 `identifier` | 匹配 key 第一段，对应原始告警 `type` | 先在上游监控确认现役名称 |
| 告警组件 `category` | 匹配 key 第二段，对应原始告警 `component` | 改名或枚举漂移会导致整条链不触发 |
| 产品线 `product_line` | 归属元数据，不参与告警匹配 | 枚举缺失先查代理与新变更枚举 |
| 归属组件 `component` | 团队/配置归属，不是原始告警 `component` | 与“告警组件”分开记录，不能互换 |
| 告警等级 `grade` | 生成 `filter_rule`，key 命中后再过滤 | key 已命中但无任务时检查该规则 |

`EarlyWarningItemServiceImpl` 每两分钟刷新缓存；配置刚变更后的短暂不一致需同时对照 DB、缓存刷新日志和任务时间。

### 响应预案隐藏字段

以下字段前端编辑页无入口，但后端 CRUD 和运行代码均使用：

| 字段 | 运维含义 |
|---|---|
| `decision_mode` | 只支持 `NEVER/AMBIGUOUS/ALWAYS`，空值回退 `ALWAYS`；不要把 `execute_pattern=AUTO` 误读为无需人工 |
| `dingtalk_token` | 空值会跳过 Plan 钉钉通知，但不阻断主流程 |
| `execute_pattern` | `AUTO/HUMAN_DO`，与 `decision_mode` 不是同一维度 |
| `status` | 只有 ONLINE 预案进入运行缓存；配置存在不等于会被匹配 |

### Agent/PostCheck 接入契约

Agent 配置拆成 NAP 业务空间、Agent ID 和输入转换。输入转换是每次会话的第一条 user message，运行时支持以下占位符：

| 占位符 | 语义 | 排障要点 |
|---|---|---|
| `$${alarm}` | 完整告警信息 | 先确认是本次任务告警，不是相邻窗口或重试样本 |
| `$${alarm.<path>}` | 告警中的指定路径/字段 | 路径不存在或源事件未标准化会导致输入缺失 |
| `$${solution.name}` | 已绑定快恢模板名称 | 仅用于上下文，不能证明运行时已选中或提交 |
| `$${solution.uuid}` | 已绑定快恢模板 UUID | 与任务、编排策略和下游计划 ID 继续对账 |
| `$${solution.params}` | 快恢模板入参描述 | 不是最终变更请求体；参数富化、映射和渲染后仍可能变化 |

**输出质量保护**：
- 根因型 Agent 定界会根据已绑定快恢模板生成 JSON Schema，平台对最终输出做提取/尽力修复
- 校验失败时携带上下文和失败信息重试一次
- standard PostCheck 最终业务结果必须归一为 JSON 对象：`pass`(Boolean) 表示是否恢复，`details` 提供判断依据
- AI 回调从 `final-report.parts[].text` 提取后清洗，SCRIPT 回调从 `inputParams` 取结果，二者进入同一 `PostCheckResultDTO`
- JSON Schema/自动提取/修复/一次重试是输出质量保护，不等于失败后会自动降级到脚本或人工

### NOC 同步辅助输入

`EarlyWarningFromNocScheduler` 每 5 分钟同步 NOC 风险/故障、每小时同步 Expert 服务单，在运行配置启用时写入 `early_warning` 表。该证据只证明事件管理/展示侧有外部预警输入，**未证明它会自动触发 `SceneModelChannel` 或创建根因型 `EmergencyTask`**。排障时不能把"预警已入库"直接等同于"响应任务已创建"。

## 统一容灾：独立业务编排复用 fresh 底座

统一容灾拥有站点切换、机器任务和切换报告对象，`OverviewSwitchService` 复用 `stability_locate_new.emergency_task`、`stability_locate_new.escape_task` 与变更编排底座。控制流：

```text
预览水位 → 确认切换范围与顺序 → 启动
→ 创建 EmergencyTask（ESCAPE_DECIDED）并保存快照
→ 创建 SiteSwitchTask 明细 → 单项/批量执行
→ EscapeTask → 变更或 Agent 执行 → 回调推进 → 生成报告
```

统一容灾是独立的容灾业务能力，不是应急 3.0，也不是另一套执行引擎。排查卡点应沿 `EmergencyTask → SiteSwitchTask → EscapeTask → 外部执行 ID → 回调/报告` 追踪。

**观测能力边界**：
- `observe.need.enable`（是否需要切换）：当前默认 `false`，`COMMON_NETWORK` 固定返回"能力建设中"
- `observe.can.enable`（是否允许切换）：当前默认 `false`，到达 `COMMON_NETWORK` 即异常
- `observe.satisfied.enable`（切换是否满意）：当前开启，前序通过后到达 `COMMON_NETWORK` 仍固定异常
- 水位观测只支持 `ALILB_LVS/CLB_LVS`，总流量与业务流量支持 `ALILB_LVS/CLB_LVS/XGW/CGW`

## 关联键与跨系统 ID 桥接

| 业务链 | 稳定关联键 | 外部系统桥接 |
|---|---|---|
| 1.0 | `emergency_event.uuid` → `exception_calculate_task.alert_uuid` → `task_uuid` → `master.agent_task.uuid` → `handle.escape_task.trigger_uuid` | handle `escape_task.execute_result.executeUuid` 是旧变更 UUID |
| 2.0/根因型 | `emergency_task.uuid` → `escape_match_task.emergency_task_uuid` → `agent_script_task.relative_process_uuid` → `escape_task.emergency_task_uuid` → `change_compile_task` → `escape_aggregate_task.uuid` | `escape_aggregate_task.solution_execute_uuid` 是新变更计划记录 UUID（≠ scheduler 执行单 UUID） |
| 指令型 | `quick_recovery_task.recovery_template_uuid` → `outer_executable_task.relative_process_uuid` | `quick_recovery_task.under_execute_uuid` 是新变更计划记录 UUID |
| AI 定界 | `agent_script_task.agent_info.taskUuid` | NAP `task_id`，本地任务 UUID 不能直接当 NAP task_id |

**新变更平台日志**：
- manager：`qt-change-manager-daily`/`qt-change-manager-pre`/`qt-change-manager-pub`
- planning：`qt-change-planning-daily`/`qt-change-planning-pre`/`qt-change-planning-production`
- scheduler：`qt-change-scheduler-daily`/`qt-change-scheduler-pre`/`qt-change-scheduler-prod`

**NAP 日志**：
- 预发：`qt-sop-agent/qt-sop-agent-log-pre`
- 生产：`qt-sop-agent/qt-sop-agent-log`
- 查询键：`task_id = agent_info.taskUuid`

### 按运行链选择数据库

| 运行链 | 首选 DB/schema | 关键表 |
|---|---|---|
| 1.0 | legacy 逻辑域 | `emergency_event`、`exception_model`、定位模板/任务 |
| 2.0 | `stability_locate_new` | `emergency_scene`、`emergency_task`、`escape_*`、决策/流控表 |
| 根因型 | `stability_locate_new` | `early_warning_item`、`emergency_scene_model`、`emergency_response_plan`，运行态复用 fresh 表 |
| 指令型 | `stability_standard_emergency` | `quick_recovery_template`、`quick_recovery_task`、`outer_executable_task` |

### 根因型配置链 SQL

按预案 UUID 查询配置链（不读取敏感字段）：

```sql
SELECT
    ewi.uuid AS warning_item_uuid,
    esm.uuid AS scene_model_uuid,
    erp.uuid AS plan_uuid,
    erp.status AS plan_status,
    emp.uuid AS locate_policy_uuid,
    emp.root_cause_code,
    els.uuid AS locate_executor_uuid,
    els.mode AS locate_mode,
    es.uuid AS escape_solution_uuid,
    ccp.uuid AS compile_policy_uuid,
    ccp.solution_uuid AS downstream_solution_uuid
FROM emergency_scene_model esm
LEFT JOIN early_warning_item ewi
  ON FIND_IN_SET(ewi.uuid, REPLACE(esm.early_warning_item, ' ', '')) > 0
LEFT JOIN emergency_response_plan erp
  ON erp.uuid = esm.response_plan_uuid AND erp.is_deleted = 0
LEFT JOIN escape_match_policy emp
  ON emp.scene_uuid = erp.uuid AND emp.is_deleted = 0
LEFT JOIN entity_locate_script els
  ON els.match_policy_uuid = emp.uuid AND els.is_deleted = 0
LEFT JOIN escape_solution es
  ON es.uuid = emp.escape_solution_uuid AND es.is_deleted = 0
LEFT JOIN change_compile_policy ccp
  ON ccp.escape_solution_uuid = es.uuid AND ccp.is_deleted = 0
WHERE esm.is_deleted = 0
  AND erp.uuid = '<plan_uuid>';
```

注意：`scene_uuid` 是跨代兼容字段，`scene-...` 关联原始 2.0，`plan-...` 关联根因型预案。联查时每张表都要加 `is_deleted=0`。

### 变更平台只读 API (change-read)

新变更平台 Project 是 `qt-changeplatform`，region 是 `cn-hangzhou`。

| 查询 | 命令 | 说明 |
|---|---|---|
| 方案配置/当前版本 | `change-read solution <env> <solution-uuid>` | manager 精确 UUID 查询 |
| 当前启用模板 | `change-read action-template <env> <template-uuid>` | 核对 EXECUTE/ROLLBACK/ESCAPE 类型 |
| 计划记录 | `change-read workflows <env> <solution-uuid>` | planning 按方案查询 |
| scheduler 执行单 | `change-read scheduler-order ...` | 只有 planning 已生成下游任务后才查 |

计划记录 UUID ≠ scheduler 执行单 UUID，必须从 planning 日志提取实际 scheduler ID。

## 代码入口与 Controller 路径

### Channel 责任链（EventSlsProcessor 内）

代码顺序：`SpecialPcapChannel → TriggerChannel → SceneModelChannel → FaultModelChannel`

| Channel | 类 | 匹配逻辑 | 独占 |
|---|---|---|---|
| PCAP | `SpecialPcapChannel` | 匹配特殊抓包告警组件 | 是（命中后不再进入后续 Channel） |
| 原始 2.0 | `TriggerChannel` | 匹配活跃场景告警触发器 | 否 |
| 根因型 | `SceneModelChannel` | 匹配早期预警项 trigger key | 否 |
| 1.0 | `FaultModelChannel` | 兜底，永远返回 true | 否 |

所有 Channel 位于 `com.aliyun.qitian.strategy.impl` 包，继承 `AlarmTriggerChannel`。

### 核心 Controller 路径

| 业务域 | 类 | 基础路径 | 关键接口 |
|---|---|---|---|
| 根因型预案 | `EmergencyResponsePlanController` | `/emergency/response/plan` | `GET /detail`、`POST /add`、`POST /online`、`POST /online/do`、`POST /offline` |
| 根因型预案复制 | 同上 | 同上 | `POST /add/copy` |
| 预警项 | `EarlyWarningController` | `/early/warning` | `GET /item/list/page`、`POST /item/add`、`POST /item/update`、`POST /bind` |
| 2.0/根因型手动执行 | `EscapeTaskController` | `/escape/task` | `POST /human/do`、`POST /human/do/no/decision`、`POST /stop`、`GET /list/page` |
| 指令型任务 | `QuickRecoveryTaskController` | `/quick/recovery/task` | `POST /start`、`POST /change/callback/{taskUuid}`、`GET /detail` |
| 事件响应中心 | `EmergencySceneModelController` | `/emergency/scene/model` | 场景模型 CRUD |
| 应急任务 | `EmergencyTaskController` | `/emergency/task` | 任务查询/详情 |
| 定位策略 | `EmergencyLocateController` | `/emergency/locate` | 定界策略查询/详情 |
| 新变更提交 | `ChangePlatformController` | `/changePlatform` | `POST /start`（变更提交入口） |
| NAP AI | `NapAiController` | `/nap/ai` | AI 定界提交/回调 |

### 状态枚举精确值

**EmergencyTaskStatus**（2.0/根因型任务，按 order 递增）：

```
AGGREGATED(0) → ESCAPE_MATCHED(1) → ENTITY_LOCATED(2) → ESCAPE_DECIDED(3)
→ FLOW_CONTROL_PASSED(4) → ESCAPE_AGGREGATED(5) → PARAM_ENRICHED(6)
→ SOLUTION_SUBMITTED(7) → SUCCESS(9) / FAILED(8)
```

**EscapeTaskStatus**（逃逸任务）：

```
INIT(0) → IDEMPOTENT_DROPPED(1) / IDEMPOTENT_PASSED(2)
→ POLICY_DROPPED(3) / POLICY_PASSED(4) → PLATFORM_PASSED(5)
→ AGGREGATED(6) → SUCCESS(8) / FAILED(7)
```

**QuickRecoveryTask**（指令型任务，双字段组合）：
- `stage`: `INIT → EXECUTE → POST_CHECK → COMPLETED`（枚举类 `QuickRecoveryTaskStage`）
- `status`: `DOING / SUCCESS / FAILED`

### system_config 关键配置键

| 配置键 | 用途 | 排障时怎么用 |
|---|---|---|
| `monitor.sls.config` | SLS 消费配置 | 检查 endpoint/project/logStore/consumerGroup |
| `monitor.sls.consumer` | SLS 消费者机器列表 | 确认当前 hostname 是否在列表中 |
| `transit.sls.config` | Transit 消费配置 | 检查上游源配置 |
| `transit.sls.send.config` | Transit 转写目标 | 检查中间 Logstore 目标 |
| `monitor.sls.transit` | Transit 机器列表 | 确认当前 hostname 是否在列表中 |
| `flow.control.sys` | 系统级流控 | 检查全局流控阈值 |
| `flow.control.device.button` | 设备级流控开关 | 检查是否启用设备级流控 |
| `flow.control.region` | 地域流控 | 检查地域维度阈值 |
| `flow.control.component` | 组件流控 | 检查组件维度阈值 |
| `flow.control.device` | 设备流控 | 检查设备维度阈值 |
| `idempotent.expire.time` | 幂等过期时间 | 检查重复任务窗口 |
| `flow.control.expire.time` | 流控过期时间 | 检查流控令牌释放时间 |
| `observe.need.enable` | 是否需要切换 | 统一容灾观测开关 |
| `observe.can.enable` | 是否允许切换 | 统一容灾控制开关 |
| `observe.satisfied.enable` | 切换是否满意 | 统一容灾满意度开关 |
| `sys.auth.admin` | 系统管理员列表 | 检查手动执行授权 |
| `noc.sync.config` | NOC 同步配置 | 检查 NOC 预警同步是否启用 |
| `pcap.special.alarm` | 特殊抓包告警列表 | PCAP Channel 匹配源 |

### Master 后处理策略

Master 脚本任务完成后按类型进入不同后处理策略：

| 后处理类 | 触发场景 | 回调 Locate 路径 |
|---|---|---|
| `EntityLocatePostProcess` | 对象定界 (ENTITY_LOCATE) | `/decision/start/batch` |
| `ParamEnrichPostProcess` | 参数富化 (PARAM_ENRICH) | `/changePlatform/start` |
| `OuterExecutableTaskPostProcess` | 指令型 SCRIPT PostCheck | PostCheck 回调接口 |

所有后处理统一读取 `stability.locate.url` 作为回调地址，这是共享 Master 跨环境接管的根因。

## 已知故障模式快速匹配

| 案例 | 故障指纹 | 核心结论 |
|---|---|---|
| CASE-001 | `objectList=[]`、`primaryKeys=[]`、无 `solution_execute_uuid` | 新变更参数映射遗漏逃逸方案主键 |
| CASE-002 | 提示审批发起成功、跳转 `/null`、方案仍 `OFFLINE` | 未完成审批锁被误报为新审批成功 |
| CASE-003 | 页面卡"平台性能流控"、旧任务长期 `SUBMITTED/AGGREGATED` | 变更侧制造非终态，应急侧流控维度阻塞后续增量。追加提示：令牌持有方可能是手动测试执行而非系统自动逃逸，须从日志确认发起方式；止血可调 `POST /decision/recovery` 传持有方 estask uuid 释放令牌 |
| CASE-004 | "当前环境对象不存在"、定位脚本返回监控聚合对象 | 定位脚本选错对象字段，输出不符合变更对象契约。成因变体：用户手动填错 `objectService`（如 `cgw` vs `cgw-service#sna`）指纹相同，先逐字段 diff 成功/失败请求体区分成因再定归属 |
| CASE-005 | 短地域搜不到、`regionNo`/`regionNoAlias`/`standardddRegionNo` | 页面输入字段混用长短地域语义 |
| CASE-006 | 生产任务显示 `Timeout`、预发 Handle 无创建执行日志 | 预发超时扫描未按环境过滤，跨环境改写共享任务状态 |
| CASE-007 | 方案负责人可执行、其他人返回 `authorization failed` | 手动执行按逃逸方案 `manager_group` 做对象级授权 |
| CASE-008 | 预发任务回调只在生产 Locate 命中、PostCheck 中断 | 共享 Master 使用单一 Locate 回调地址，SCRIPT 任务被生产接管 |
| CASE-009 | 刚配完逃逸方案/刚改完脚本就执行，立即报错找不到配置 | 配置走本地缓存，不是故障；等 5 分钟或手动刷新缓存后重试 |
| CASE-010 | 脚本已提交很久，执行的仍是旧版本内容 | 提交方用了 force push，执行机自动 merge 失败卡住，需逐台处理 |
| CASE-011 | API 500 且 errorMsg 含 `Request to query change execute record fail!`，内层 `Template action is deleted` | 老变更引用的模板 action 被下游变更平台删除，详情查询恒定失败；本机 `pullSolutionNameByUuid` 取展示字段零容错放大为 500 |
| CASE-012 | autofix/逃逸单失败但变更单"待发布"、设备"等待中/已初始化"，回调序列 `WAIT_TRIGGER→FAIL` | 天基 start 遇 POP 瞬时 503（深层：OAM 后端 Dubbo 线程池耗尽），VNET 与 stability-handle 双层无重试，瞬时抖动放大为终局失败 |
| CASE-013 | 手动执行页弹窗"获取当前逃逸方案参数接口失败"、`/escape/solution/detail/param` 对特定 solutionId 恒返 `{msg:null,code:"500"}` | 方案 `input_params` 缺 `primary` 字段 → `loadDefaultSelectorsForParams` Boolean 拆箱 NPE；切面对 null message 二次 NPE 吞掉错误信息 |

### 新增案例详情（2026-08）

以下条目按「指纹 / 根因 / 处置 / 检索入口」四要素记录，详情全文见报告文件名（`stability-locate/doc/` 目录，不在本仓库）。报告文件名以产出日期为前缀：单案例 `seek-report-YYYY-MM-DD-{场景}-{业务ID?}-{现象}.md`，多篇汇总 `seek-reports-digest-YYYY-MM-DD-to-YYYY-MM-DD.md`。

**CASE-011 — 下游模板 action 被删，详情查询恒定 500**

- 指纹：stability-locate API 500，errorMsg 含 `Request to query change execute record fail!`，内层 `Template action is deleted! Action uuid: <uuid>`；仅老变更（solutionUuid 非 `s-` 前缀）触发；错误当天突发、此前多天为 0。
- 根因：老变更引用的模板 action 在变更平台侧被删除，`changeplatform.getChangeSolutionDetail` 恒返 success=false；`SolutionUtil.queryForDetails` 无容错，仅为取 name 展示字段的调用把整接口打成 500（`getStdOutByExecuteUuid` 同款）。
- 处置：联系变更平台确认删除人/时间（误删可恢复）；本机两个调用点加 try-catch 降级返回；长期推动老变更迁移新变更体系。
- 检索入口：`Template action is deleted`、`Request to query change execute record fail`、`pullSolutionNameByUuid`。报告：`seek-report-2026-08-27-template-action-deleted.md`。

**CASE-012 — autofix 变更单创建后从未启动（待发布）**

- 指纹：1.0 autofix/逃逸单失败但变更单"待发布"、设备"等待中/已初始化"；回调序列 `PRECHECK_PASS→APPROVE_PASS→WAIT_TRIGGER→FAIL`；solution stageStatus=FAIL 而天基单未启动。
- 根因：start 操作遇天基/OAM POP 瞬时 503（用 `aliyunpop dx` 深挖证实深层为 OAM 后端节点 Dubbo 线程池耗尽）；VNET 对瞬时 5xx 不重试 + stability-handle FAIL 回调不消费策略 retryCnt，双层无重试放大为终局失败。
- 处置：页面手动【开始发布】补发 start；VNET start 加有界退避重试；FAIL 回调路径评估消费 retryCnt；对"solution FAIL + 天基单待发布"组合加告警。
- 检索入口：`TianjiQueryFailException`、`ServiceUnavailable`、`startCommandLineTask`、`WAIT_TRIGGER`。报告：`seek-report-2026-08-31-alert-91e78443-autofix-not-started.md`。

**CASE-013 — 方案参数缺 `primary`，detail/param Boolean 拆箱 NPE**

- 指纹：齐天手动执行页弹窗"获取当前逃逸方案参数接口失败"；`/escape/solution/detail/param` 对特定 solutionId 恒返 `{msg:null,code:"500"}`、其他方案正常；每次打开必现、多天重复。
- 根因：方案 `input_params` JSON 中某参数缺 `primary` 键 → `Boolean primary=null` 拆箱 NPE；`ApiJsonResponseAspect.throwing()` 对 null message 二次 NPE，前端只拿到 `msg:null`。
- 处置：短期编辑方案补 `primary:false`（缓存约 2 分钟刷新）；长期 `Boolean.TRUE.equals(primary)` 判空 + 保存链路字段完整性校验 + 切面 null-message 防御（取异常类名兜底）。
- 检索入口：`获取当前逃逸方案参数接口失败`、`loadDefaultSelectorsForParams`、`msg:null code:500`。报告：`seek-report-2026-08-31-manually-execute-param-frontend-side.md`、`seek-report-2026-08-31-detail-param-b45118686b-primary-npe.md`。

### 案例排查方法论

四步定位归属法：

1. **响应形态定层级**：前端弹窗先找失败接口；`{msg:...,code:"500"}` 有文案直接看；`{msg:null,code:"500"}` 是切面自身崩溃（二次 NPE），必须去 SLS 找堆栈。
2. **对照实验区分数据特异性**：问题 uuid 失败 + 假/其他 uuid 正常 → 数据触发型；全量失败 → 平台/系统性故障。
3. **部署时间线排除法**：`seek deploy env` 取部署时间与首次报错比对，不吻合或早于部署即报错 → 排除发布引入。
4. **横向统计排除系统性**：按方案/参数/时间聚合成败分布，个案参数错误与系统性故障的升级路径不同。

requestId 串联三日志（无 trace 接入时的调用链闭环替代）：同一 requestId 串联 ①访问日志（`ApiJsonResponseAspect.before`，URL+ARGS）②下游调用日志（action+uuid+endpoint）③ERROR 堆栈。NPE 类 `errorMsg:{}` 无信息，堆栈必须取 `log` 字段。

下游错误三分法：

| 下游表现 | 判断 | 归属动作 |
|---|---|---|
| HTTP 正常应答 + success=false + 重复请求错误恒定 | 确定性业务错误（下游数据状态） | 归下游数据，本机补容错（CASE-011） |
| 5xx/瞬时错误码 + 无重试即终态 | 瞬时故障被放大 | 归下游瞬时故障 + 追责中间层无重试（CASE-012） |
| 同步拒绝且历史成功参数不同 | 入参错误 | 逐字段 diff 成功/失败请求体，差异字段即根因候选（CASE-004 变体） |

POP 5xx 深挖：对 RequestId 执行 `aliyunpop dx <RequestId>` 区分网关与后端——看 `Ext5.stage`/`flowCtrlRet`（是否限流）与 `exceptionInfo`（后端异常细节），追责时提供 RequestId + 后端节点 IP，不笼统报"POP 故障"。

### 取证陷阱

- **误导性日志文案**：`Call change request, network fail`（`taskFailed`）把下游业务错误统一标为网络失败；`{msg:null,code:"500"}` 的真实异常在 SLS `log` 字段；页面"待发布"≠"未提交"，可能是创建成功但 start 从未成功。
- **环境路由以实际流量为准**：页面所在域名不决定后端环境，以访问日志 VIP 为准；"生产不受影响"要用 prod 全扫描 0 条证明。
- **"谁发起"定性须有直证**：涉及任务/令牌占用方的发起方式（系统自动 vs 手动测试），必须有日志中操作人/调用来源的直证，否则标注 {待确认}。
- **连字符 uuid 关键词检索漏检**：通用规则见 `references/evidence-and-boundaries.md` 的「关键词搜索静默返 0」，凡查含连字符/驼峰的 uuid 必须 SQL `like` 全扫描兜底，关键词返 0 不得作为"未发生"的证据。

## 运维操作手册（交接文档实操）

以下条目来自《交接文档》的常见问题处理手册，是高频误判来源，排查时优先排除。

### 控制台入口

写排查报告时用来附现场链接；页面截图不能代替日志/DB 证据。

| 用途 | 入口 |
|---|---|
| 应急 2.0 配置页 | `https://qt.aliyun-inc.com/selfhealing/monitor/emergencyTwo/manage` |
| 应急 2.0 事件页 | `https://qt.aliyun-inc.com/selfhealing/monitor/emergencyTwo/market` |
| 指令型工单大盘 | `https://qt.aliyun-inc.com/selfhealing/monitor/emergency/directiveRecordList` |
| 快恢模板配置 | `https://qt.aliyun-inc.com/selfhealing/monitor/emergency/RecoverTempalte` |
| 脚本执行机集群 | `https://qtgateway.aliyun-inc.com/swirl/swarm/services`（`emergency` 开头） |

齐天导航栏颜色区分：红色 = 应急 1.0，绿色 = 事件响应中心，其余 = 应急 2.0。判定用户在哪条运行链上报问题时可以先问入口颜色。

### 配置缓存：改完不立即生效

应急配置（逃逸方案、脚本内容、预警项等）运行时走本地缓存，**保存成功 ≠ 立即可执行**。

- 正常生效窗口：5 分钟内重试即可，不必按故障处理
- 手动刷新：`curl -X POST http://qt-stability-locate-vip.aliyun-inc.com/manage/refresh`
- VIP 域名前面有负载均衡，只会刷到其中一台。**要确保全环境生效，必须逐台登录执行** `curl -X POST http://localhost:7001/manage/refresh`
- 排障含义：只在部分机器上复现的"配置不生效"，优先怀疑刷新只命中了部分实例，而不是配置本身有问题

预警项另有独立刷新节奏（`EarlyWarningItemServiceImpl` 每两分钟），配置刚变更后对照 DB、缓存刷新日志和任务时间三者判断。

### 脚本长期不更新：force push 导致 merge 卡死

脚本更新提交很久后执行的仍是旧内容，根因基本都是**提交方用了 force push 等操作导致执行机上的自动 merge 失败**，不是平台分发故障。

- 处理方式：登录执行机逐台解决 merge 冲突，没有远程一键修复手段
- 集群入口：`https://qtgateway.aliyun-inc.com/swirl/swarm/services`
- 服务命名：`emergency` 开头，`daily` / `beta` / `develop` / `master` 分别对应日常通道、生产的 beta / develop / master 通道
- 排障含义：先确认执行机上的脚本工作区状态，再看任务日志；任务日志显示"执行成功"但行为是旧逻辑，属于此模式

### 事件执行失败的定位顺序

系统性故障少见，绝大多数失败来自用户配置错误或变更被拦截（任务参数不对等）。

1. 打开事件详情页，找标红的块，展开看具体报错
2. 报错在变更提交/执行阶段 → 转变更侧排查
3. 报错在脚本执行阶段 → 看脚本本身哪里写错

### 日常测试：主动投递告警

日常告警源与生产隔离。日常环境选不到告警项时，可在日常系统录入，或直接用 API 投递测试告警：

```text
POST http://qt-stability.alibaba.net/alert/event/add
Content-Type: application/x-www-form-urlencoded
```

关键表单字段：`productName`、`component`、`type`、`grade`(P1~P4)、`source`、`entityType`、`entity`、`region`、`description`、`detailMsg`、`beginTime`(毫秒时间戳)。

其中 `type` + `component` 就是根因型匹配 key 的两段（对应预警项的 `identifier` + `category`），构造测试告警时这两个字段必须与目标预警项完全一致，否则不会触发 `SceneModelChannel`。

### 表名勘误：SLA 限流

《交接文档》写的是 `stability_locate_new.sla_qpm_limit`，**代码实际使用的表是 `sla_qpm_rate_limit`**（已对照 `SLAQpmRateLimitMapper.xml` 核实）。查限流配置时用后者，用前者会查到表不存在。

### 配置勘误：qt-expert 无 SLS 日志源

《交接文档》SLS 章节的控制台链接里带有 `vnet-cn-hangzhou-2/qt-cmdb-log` 字样，那是 RAM 子账号登录跳转（`RelayState`）的残留参数，**不是 qt-expert 的日志源**。实测该 SLS project 在当前账号下不存在，seek 已移除该配置。qt-expert 取证走 `seek ticket` 命令或本地仓库代码。

## 环境隔离与共享风险

| 共享资源 | 当前风险 | 排障要点 |
|---|---|---|
| DB | pre/prod 共享 legacy DB；fresh 任务库共享 | 检查任务来源环境，不能仅凭 DB 记录判断来源 |
| Redis | 预发/生产共用流控等待队列，key 无环境前缀 | 生产 JVM 可唤醒预发任务，反之亦然 |
| Master | 共享 Agent Master，`stability.locate.url` 固定回调生产 | SCRIPT 参数富化/定界和 standard SCRIPT PostCheck 可进入生产 |
| NAP AI | 发起 Locate 把自身 URL 作为逐任务回调地址 | 回调路由隔离，但任务库和 Redis 仍共享 |

**环境判定**：
- `daily`/`yanlian` 的 `app.env` 都可能是 `DAILY`，必须用部署单元 + 数据源 endpoint 联合区分
- `pre` 与生产共享 DB，但 `pre` 不启动自动 SLS Worker
- 环境不明时不得混查

## 卡单排障树

自动触发且尚未生成本地任务时，先执行双级入口断点：

```text
原始监控源
  → [Transit Worker / 第一段 ConsumerGroup]
应急中间 Logstore
  → [主 Consumer Worker / 第二段 ConsumerGroup]
首个 EmergencyEvent / EmergencyTask
```

然后按业务类型进入分支：

```text
1.0 → EmergencyEvent/模型/定位任务 → 旧 AgentTask、Redis、AG → handle 主库 escape_task
2.0/根因型 → fresh EmergencyTask → AgentScriptTask/NAP、决策、流控 → ChangeCompileTask、回调
指令型 → QuickRecoveryTask → 新变更 execute id → OuterExecutableTask PostCheck
```

**典型卡点**：
- 1.0：模型未命中、Redis 队列积压、AG 无心跳、定位回调丢失、旧变更回调未推进
- 2.0/根因型：SLS 消费停滞、场景/预案未命中、脚本/NAP 超时、等待人工决策、流控阻断、参数富化失败、变更回调丢失
- 指令型：模板/权限不可用、变更创建失败、变更回调缺失、PostCheck 任务未创建

## 根因归属最低证据

| 归属 | 最低证据组合 | 常见反例 |
|---|---|---|
| 上游监控/事件 | 原始告警、标准事件、推送日志三者至少两层可对账，并证明应急消费者之前已缺失/畸形 | 应急无任务不等于上游没发，可能被窗口、SLA 或匹配策略丢弃 |
| 应急匹配/控制面 | 上游事件已到达，代码与 DB 证明在场景、预案、定界、决策、流控或聚合中的首个失败点 | 页面显示"未匹配"可能只是异步状态尚未刷新 |
| AG/NAP | 本地任务已创建，DB 中 AG/NAP 关联键可取，执行日志证明未领取、脚本/Skill 失败、超时或输出不合约 | NAP 本地 UUID 与 NAP task_id 不是同一个值 |
| 下游变更 | manager 已受理请求，planning/scheduler 首次失败日志与当时方案/模板版本一致 | 页面通用校验告警不能单独证明根因 |
| 回调/状态同步 | 外部系统已有终态，回调请求/响应可证，而应急本地状态未按代码条件推进 | 外部计划记录 UUID 不一定是 scheduler 执行 UUID |
