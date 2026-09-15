# Proposal: fix-agent-evaluation-validation

## Why

Agent 场景评测器对用户提供的 expected 子结构缺少前置类型校验，部分畸形文件会以 AttributeError/TypeError 退出；live runner 还能看到评分标准，且一个指标名称与实际口径不一致。

## What Changes

- 在合并 defaults 与场景覆盖前校验 expected，并校验 protocol/trajectory/report 的容器与标量类型。
- live runner 输入改为执行字段白名单，不再传递 expected 和 replay。
- 新增语义准确的 `scenario_failure_rate` 与 `violations_per_scenario`，保留旧字段作为兼容别名并标记 deprecated。
- 独立 runner 对意外异常也输出结构化 JSON。
- 增加相关回归测试并升级 patch 版本。

## Capabilities

### New Capabilities

无。

### Modified Capabilities
- `agent-scenario-evaluation`: 加固场景输入错误、隔离评分标准并澄清指标契约。

## Impact

影响 Agent 评测器、live runner 输入协议、指标输出、测试及 Harness 文档；旧 `constraint_violation_rate` 字段暂时保留兼容。
