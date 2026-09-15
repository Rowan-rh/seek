# Design: fix-agent-evaluation-validation

## Context

场景文件是用户可控输入，不能假定 expected 及其子字段始终符合内置 fixture。live runner 也不应获得用于评分的答案和约束。

## Decisions

- 在 `_deep_merge` 前分别校验 defaults.expected 和 scenario.expected 为对象，再对三层期望字段执行类型校验。
- live payload 采用 `id/category/prompt/fixtures/metadata` 白名单，而非逐项删除敏感字段。
- `scenario_failure_rate` 成为规范名称；`constraint_violation_rate` 作为兼容别名保留一个版本，并在输出中通过 deprecated_metrics 标注。
- 新增 `violations_per_scenario` 表达违规条数与场景数的关系。
- 独立 runner 在最外层捕获意外异常，保持 stdout JSON 契约。

## Risks / Trade-offs

- 更严格校验会拒绝以前被宽松接受的畸形文件，这是预期的错误前移。
- live runner 不再读取 expected；依赖该字段自校验的 runner 需要改为只消费执行输入和 fixtures。
