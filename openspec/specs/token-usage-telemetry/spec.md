# token-usage-telemetry Specification

## Purpose
记录 Agent 在链路步骤中的 token 使用量，为成本和性能分析提供数据，但不影响当前阶段的任务评分或流程判定。

## Requirements

### Requirement: 步骤可记录 token usage
`chain complete` SHALL 接受可选 token usage 对象，支持 `input_tokens`、`output_tokens`、`cached_input_tokens` 和 `reasoning_tokens`。字段值 MUST 为非负整数，未知字段或非法数值 MUST 被拒绝。

#### Scenario: 合法 token usage 被持久化
- **WHEN** 完成步骤时提交合法 token usage
- **THEN** completed step 中保存该数据
- **AND** 步骤的成功与否不因 token 数量改变

#### Scenario: 非法 token usage 被拒绝
- **WHEN** token usage 包含负数、布尔值、非整数或未知字段
- **THEN** 返回 BAD_TOKEN_USAGE 且步骤不推进

### Requirement: 会话 token 汇总只用于统计
系统 SHALL 提供 `chain usage <session>`，返回每个字段总量和按步骤明细。token usage MUST NOT 参与 validate、报告生成资格、Harness ready 或质量评分；未上报步骤按 0 统计并标记统计不完整。

#### Scenario: 部分步骤上报 token
- **WHEN** 一个会话仅部分 completed steps 包含 token usage
- **THEN** usage 返回已上报字段总量和逐步骤明细
- **AND** `complete=false`
- **AND** 不改变 session 状态及任何评分结果
