# Proposal: add-chain-evidence-and-token-telemetry

## Why

当前 `chain complete` 只验证 outputs 字段存在，无法区分真实查询无结果、步骤不适用、工具失败和未执行即填空；同时 Harness 只能统计命令耗时，无法观察 Agent 每步 token 消耗。需要为证据型步骤增加结构化证据门禁，并补充仅用于观测、不参与评分的 token 使用量记录。

## What Changes

- 为链路步骤增加可选 `evidenceRequired` 声明；内置链路中涉及外部查询或代码取证的步骤启用该声明。
- `chain complete` 新增 `--evidence`，校验 `FOUND/NO_DATA/NOT_APPLICABLE/TOOL_ERROR`、证据来源、边界和空结果原因。
- 证据随 completed step 持久化，并在 session context 中集中暴露；缺失或非法证据时拒绝推进。
- `chain complete` 新增可选 `--token-usage`，记录 input/output/cached/reasoning token；数值必须为非负整数。
- 新增 `chain usage <session>`，按步骤和会话汇总 token；该数据只用于统计，不参与链路校验、成功判定或 Harness 评分。
- 更新 Skill、capabilities、命令文档、链路定义、测试和离线 Harness 场景。

## Capabilities

### New Capabilities

- `chain-evidence-schema`: 定义证据型步骤的结构化 evidence 格式、校验、持久化和空结果语义。
- `token-usage-telemetry`: 定义可选 token 使用量记录与会话聚合，明确不参与评分和流程判定。

### Modified Capabilities

无。

## Impact

- **CLI**：`chain complete/amend` 新增 `--evidence`，`chain complete` 新增 `--token-usage`，新增 `chain usage`。
- **链路引擎**：session 增加 `step_evidence`，completed step 可包含 `evidence` 和 `token_usage`。
- **链路配置**：两份 `default.json` 同步增加 `evidenceRequired`。
- **兼容性**：未声明 `evidenceRequired` 的用户自定义链路保持原行为；token usage 始终可选且不影响评分。
