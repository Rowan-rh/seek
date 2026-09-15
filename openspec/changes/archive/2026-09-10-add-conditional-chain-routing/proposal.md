# Proposal: add-conditional-chain-routing

## Why

现有链路虽然包含 branch-decision 步骤，但引擎仍线性执行所有后续步骤，导致不适用步骤也必须执行并提交空值，增加工具调用、token 和延迟，也模糊了“未执行”与“执行无结果”的区别。

## What Changes

- 链路步骤新增声明式 `when` 条件，支持 `equals`、`in`、`exists`。
- 条件不满足时引擎自动记录 skipped step，并通过 `skipOutputs` 提供下游需要的默认输出。
- validate 将 skipped 视为已解析前置步骤，但 requiredInputs 仍只能来自引擎生成的 step_outputs。
- status/context 暴露 skipped_steps，complete 响应说明本次自动跳过的步骤。
- 首先改造 alert-ticket：branch-decision 显式输出 has_similar；无相似工单时自动跳过 analyze-similar。

## Capabilities

### New Capabilities
- `conditional-chain-routing`: 声明式步骤条件、自动跳过、默认输出和审计记录。

### Modified Capabilities
- `chain-evidence-schema`: 被自动跳过的证据型步骤无需提交 evidence，并明确记录为 skipped 而非 NO_DATA。

## Impact

影响 chain 引擎、chain 命令、alert-ticket 定义、Skill/capabilities/文档和测试。新 session 启用路由契约，旧 session 保持线性行为。
