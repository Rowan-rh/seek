# Design: add-conditional-chain-routing

## Context

链路依赖 current_step 顺序推进，branch-decision 目前只能指导 Agent 手工填空。证据门禁上线后，为不适用步骤伪造 NOT_APPLICABLE evidence 会进一步放大语义混淆。

## Goals / Non-Goals

**Goals:** 提供安全、有限、可审计的条件表达；自动跳过不适用步骤；保证下游输入可满足；兼容旧 session。

**Non-Goals:** 不提供任意表达式执行、循环、并行 DAG 或手工 goto。

## Decisions

- `when` 是对象，包含 `path` 和且仅一个操作符：`equals`、`in`、`exists`；未知字段、非法 path、非数组 `in` 和非布尔 `exists` 在加载链路时拒绝。
- path 以点号读取 session context，例如 `branch-decision.has_similar`，不执行表达式或脚本。
- 条件为 false 时，引擎校验 `skipOutputs` 完整覆盖该步 outputs，写入 step_outputs/context，并追加包含条件、观测值、原因和默认输出的 skipped_steps 审计记录。
- skipped step 可满足 requires_step；下游 requiredInputs 仍从 step_outputs 按声明生产者读取，validate 已跳过步骤本身时返回 skipped。
- 新 session 写入 `routing_contract_version: 1`，并在启动与每次完成步骤后连续应用条件路由；旧 session 不自动跳过。
- alert-ticket 的 branch-decision 原样回传 `has_similar`，作为 analyze-similar 的稳定条件输入。

## Risks / Trade-offs

- 条件语言能力有限 → 保持确定性和安全，复杂表达通过前置 branch-decision 计算成简单字段。
- skipOutputs 可能掩盖错误配置 → 加载链路时强校验字段集合，并通过测试守护。
