# Delta: perf-telemetry

## Purpose

定义 seek CLI 的耗时观测规范：命令级（L1）与集成 IO 级（L2）耗时记录的写入时机、字段、开关与故障隔离规则，使排查会话的耗时可以归因到「LLM 编排 / 集成 IO」并细分到具体环境与目标，为后续批量化/并行化优化提供数据依据。

## ADDED Requirements

### Requirement: 命令级耗时记录
每次 CLI 命令执行 SHALL 记录一条耗时日志：命令名、span=command、status、duration_ms（单调钟计时，区间只覆盖命令函数本身，不含参数解析与结果打印）。成功与失败均 MUST 记录。

#### Scenario: 成功命令记录耗时
- **WHEN** 执行 `seek sls query ...` 成功返回
- **THEN** perf.jsonl 追加一条 `{command: "sls query", span: "command", status: "success", duration_ms: <毫秒>}` 记录

#### Scenario: 失败命令同样记录
- **WHEN** 命令返回 error status 或抛出异常
- **THEN** 追加 `status: "error"` 的记录，且原有错误处理（退出码、错误日志）不受影响

### Requirement: 集成 IO 耗时记录
SLS 查询、a1 subprocess、DMS MCP 调用 SHALL 分别记录耗时（span=sls_query / a1_subprocess / dms_call），detail MUST 包含可区分环境与目标的字段（endpoint/project/logstore/count 或子命令摘要）。

#### Scenario: SLS 单 logstore 耗时
- **WHEN** `query_by_config` 对同环境多 logstore 依次查询
- **THEN** 每个 logstore 各产生一条 sls_query 记录，detail 含该 logstore 的 endpoint/project/logstore 与结果条数

#### Scenario: DMS 调用含冷启动
- **WHEN** dms_client 执行一次查询（含 MCP server 进程冷启动）
- **THEN** 产生一条 dms_call 记录，duration_ms 覆盖冷启动在内的完整调用耗时

### Requirement: 开关与故障隔离
耗时记录 SHALL 受 `options.perf_log` 统一配置控制，未设置时默认开启（`as_bool` 归一化）。写盘失败（目录不可写、磁盘满等）MUST 静默吞掉，不得影响命令的 stdout 输出、退出码与执行结果。stdout 契约 MUST 保持零变化。

#### Scenario: 开关关闭
- **WHEN** `seek config set options.perf_log false` 后执行任意命令
- **THEN** perf.jsonl 不追加任何记录，命令行为与之前完全一致

#### Scenario: 写盘失败不阻断
- **WHEN** perf.jsonl 所在目录不可写
- **THEN** 命令正常执行并输出结果，无异常抛出

### Requirement: 会话关联
记录 SHALL 在环境变量 `SEEK_SESSION_ID` 存在时将其附带为 `session_id` 字段，用于把命令级耗时归属到 chain 会话的步骤；SKILL 文档 MUST 指引 agent 在 chain 会话内调用查询命令时携带该前缀。

#### Scenario: 带 session 前缀调用
- **WHEN** agent 以 `SEEK_SESSION_ID=abc123 seek sls query ...` 执行查询
- **THEN** 该条 command 记录含 `session_id: "abc123"`

#### Scenario: 无前缀调用
- **WHEN** 未设置 SEEK_SESSION_ID 执行命令
- **THEN** 记录不含 session_id 字段，其余行为不变

### Requirement: 敏感信息脱敏
写入的 detail MUST NOT 包含凭据；敏感键（ACCESS_KEY_ID/ACCESS_KEY_SECRET/PASSWORD/TOKEN）MUST 打码，查询语句与子命令摘要 MUST 截断（200 字符）。

#### Scenario: 长查询截断
- **WHEN** 一条超过 200 字符的 SLS SQL 查询被执行
- **THEN** 记录 detail.query 为截断到 200 字符的摘要
