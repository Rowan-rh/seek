# conditional-chain-routing Specification

## Purpose
定义链路步骤按已产生上下文自动执行或跳过的确定性路由能力，以减少不适用的工具调用、执行耗时和 token 消耗，并通过默认输出与跳过记录保留可验证的完整审计轨迹。

## Requirements

### Requirement: 声明式条件
步骤 MAY 声明 `when`，包含合法的非空点号 `path` 以及 `equals`、`in`、`exists` 中且仅一个操作符。`in` MUST 为数组，`exists` MUST 为布尔值，未知字段 MUST 被拒绝。引擎 MUST 只读取 session context，不执行任意表达式。

#### Scenario: 条件命中
- **WHEN** path 解析值满足条件
- **THEN** 该步骤成为当前可执行步骤

#### Scenario: 条件未命中
- **WHEN** path 解析值不满足条件
- **THEN** 引擎自动跳过该步骤，不要求 evidence 或 token usage

#### Scenario: 非法条件配置
- **WHEN** when 含多个操作符、未知字段、非法 path、非数组 in 或非布尔 exists
- **THEN** 链路加载失败并返回可定位到具体步骤的配置错误

### Requirement: 跳过步骤可审计且提供默认输出
条件步骤 MUST 声明完整覆盖 outputs 的 `skipOutputs`。自动跳过时系统 SHALL 写入包含条件、观测值、原因和默认输出的 skipped_steps，并把 skipOutputs 写入该步骤的 step_outputs/context，使后续 requiredInputs 可由声明生产者满足。对已 skipped 步骤执行 validate MUST 明确返回 skipped，而不能把它重新标记为可执行。

#### Scenario: 无相似工单跳过分析
- **WHEN** alert-ticket 的 branch-decision 原样输出 `has_similar=false`
- **THEN** analyze-similar 自动标记 skipped
- **AND** resolver、resolution_summary、resolution_analysis、related_people 使用声明的空默认值
- **AND** 当前步骤推进到 deep-investigate

### Requirement: 旧会话保持兼容
只有包含 `routing_contract_version: 1` 的新 session SHALL 自动执行条件路由；升级前已持久化 session 不因新增 when 条件改变既有线性执行方式。

#### Scenario: 升级前会话继续线性执行
- **WHEN** 持久化 session 不含 `routing_contract_version`
- **THEN** 引擎不自动应用新增的 when 条件
- **AND** 当前步骤保持原有线性语义
