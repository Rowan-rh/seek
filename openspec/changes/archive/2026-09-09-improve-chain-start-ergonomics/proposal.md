# Proposal: improve-chain-start-ergonomics

## Why

一次真实排查中暴露了链路会话"入口"阶段的三个连贯痛点，导致 agent 废弃了一个会话并被迫重建：

1. **`chain start` 的首步 `requiredInputs` 靠猜**。链路首步若声明了无生产者的外部输入（如 `alert-ticket` 的 `flow_id`、`emergency-stuck-task` 的 `task_id_or_description`），调用方必须通过 `--context` 或 `--problem` 注入。但 `chain start` 不校验、不提示，缺键时会照常建会话，直到 `chain validate` 才报 `inputs not yet available`——此时会话已废弃，只能丢弃重建。
2. **缺键后没有补救手段**。即便只是漏注一个输入，也没有命令能向已存在的会话补注入，只能重建整个会话，丢失已累积的上下文。
3. **首步需要哪些输入键没有文档化**。SKILL.md 链路表只列了链路名/场景/步骤，没写每条链路首步需要什么 context 键名，agent 只能逐个试错。

## What Changes

- **`chain start` 前置校验首步外部输入**：会话创建前计算首步无生产者的 `requiredInputs`，若 `--context` + `--problem` 无法覆盖，返回 error 态（退出码非零），错误信息列出缺失键名与该链路全部所需输入，避免产生废弃会话。
- **新增 `chain provide <session> --inputs '{...}'`**：向已存在的会话补注入首步外部输入，注入后重新校验首步并返回 validate 结果。键名与步骤名冲突时拒绝。
- **`chain list` 暴露首步输入**：链路摘要增加 `firstStepInputs` 字段（首步无生产者的 requiredInputs），供 agent 在 start 前发现所需键名，配合 `capabilities` 能力清单输出。
- **SKILL.md 链路表补齐"首步输入"列**：为每条链路标注首步需要的 context 键名或 `--problem` 满足方式。
- **文档同步**：cli/README.md、references/command-reference.md 补 `chain provide` 用法与错误码。

## Capabilities

### New Capabilities
- `chain-session-inputs`: 链路会话首步外部输入的发现、前置校验与补注入规则——`firstStepInputs` 暴露、`chain start` 缺键阻断、`chain provide` 补注入语义。

### Modified Capabilities
（无——`chain-report-templates` 为既有唯一 spec，本变更不涉及）

## Impact

- **代码**：`cli/seek_cli/chain.py`（首步输入计算/校验/provide 引擎能力）、`cli/seek_cli/commands/chain.py`（start 前置校验 + provide 命令）、`cli/seek_cli/cli.py`（provide 子命令注册）、`cli/seek_cli/commands/capabilities.py`（provide 声明 + firstStepInputs）。
- **测试**：新增 `cli/tests/test_chain_start_inputs.py`；更新 `cli/tests/test_capabilities_contract.py`（新增 provide 子命令与 firstStepInputs 契约）。
- **文档**：`SKILL.md`、`cli/README.md`、`references/command-reference.md`。
- 无外部依赖变化；`chain start` 现有合法调用（键名齐全）行为不变，仅对缺键场景从"静默建会话"变为"前置报错"。
